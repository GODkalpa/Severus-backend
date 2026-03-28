import os
import base64
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
from fido2.server import Fido2Server
from fido2.webauthn import (
    AuthenticationResponse,
    RegistrationResponse,
    UserVerificationRequirement,
    AuthenticatorAttachment,
    AttestedCredentialData,
    PublicKeyCredentialRpEntity,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
)
from fido2.utils import websafe_decode, websafe_encode
from services.brain import supabase

RP_NAME = "SEVERUS_HUD"
DEFAULT_RP_ID = "localhost"
DEFAULT_ORIGIN = "http://localhost:3000"

# In-memory challenge store (Session based or DB based)
# For simplicity, we'll store challenges in a small global dict for now, 
# but in production, this should be in Redis or DB with an expiry.
challenges = {}


def get_webauthn_rp_id() -> str:
    return os.getenv("WEBAUTHN_RP_ID", DEFAULT_RP_ID)


def get_webauthn_origin() -> str:
    return os.getenv("WEBAUTHN_ORIGIN", DEFAULT_ORIGIN).rstrip("/")


def get_fido_server() -> Fido2Server:
    rp = PublicKeyCredentialRpEntity(id=get_webauthn_rp_id(), name=RP_NAME)
    expected_origin = get_webauthn_origin()

    def verify_origin(origin: str) -> bool:
        return origin.rstrip("/") == expected_origin

    return Fido2Server(rp, verify_origin=verify_origin)

def fido2_options_to_dict(options):
    """
    Recursively converts FIDO2 options objects to JSON-serializable dicts.
    Handles bytes by encoding to websafe_base64.
    """
    if isinstance(options, bytes):
        return websafe_encode(options)

    if isinstance(options, Enum):
        return options.value

    if isinstance(options, Mapping):
        return {key: fido2_options_to_dict(value) for key, value in dict(options).items()}

    if isinstance(options, (list, tuple)):
        return [fido2_options_to_dict(value) for value in options]

    return options

def get_master_secret():
    return os.getenv("SEVERUS_MASTER_SECRET")

async def generate_registration_options(user_id: str | None = None, master_secret: str | None = None):
    # Registration always requires the master secret for security
    if master_secret != get_master_secret():
        raise Exception("MASTER_SECRET_INVALID_OR_REQUIRED")

    # Use a fixed ID for the owner so multiple devices share the same logical "user"
    user = {
        "id": b"severus-owner-fixed", 
        "name": "SeverusOwner", 
        "displayName": "Severus Owner"
    }
    
    # Check if user already has registered credentials
    credentials = []
    reg_response = supabase.table("auth_credentials").select("credential_id").execute()
    for row in reg_response.data:
        credentials.append(
            PublicKeyCredentialDescriptor(
                type=PublicKeyCredentialType.PUBLIC_KEY,
                id=websafe_decode(row["credential_id"]),
            )
        )

    options, state = get_fido_server().register_begin(
        user,
        credentials,
        authenticator_attachment=AuthenticatorAttachment.PLATFORM,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    
    challenge_id = str(uuid.uuid4())
    challenges[challenge_id] = state
    
    # Serialize for frontend - HUD expects options.publicKey
    return {
        "options": fido2_options_to_dict(options),
        "challengeId": challenge_id
    }

async def verify_registration(challenge_id: str, challenge_response: dict):
    state = challenges.pop(challenge_id, None)
    if not state:
        raise Exception("CHALLENGE_EXPIRED")

    auth_data = get_fido_server().register_complete(state, RegistrationResponse.from_dict(challenge_response))
    
    # Store in Supabase
    credential_data = {
        "credential_id": websafe_encode(auth_data.credential_data.credential_id),
        # Persist the full credential data so it can be reconstructed for assertion verification.
        "public_key": websafe_encode(bytes(auth_data.credential_data)),
        "sign_count": auth_data.counter,
        "transports": challenge_response.get("response", {}).get("transports", [])
    }
    
    supabase.table("auth_credentials").insert(credential_data).execute()
    return {"status": "success"}

async def generate_authentication_options():
    reg_response = supabase.table("auth_credentials").select("credential_id").execute()
    if not reg_response.data:
        raise Exception("NO_CREDENTIALS_REGISTERED")

    credentials = []
    for row in reg_response.data:
        credentials.append(
            PublicKeyCredentialDescriptor(
                type=PublicKeyCredentialType.PUBLIC_KEY,
                id=websafe_decode(row["credential_id"]),
            )
        )

    options, state = get_fido_server().authenticate_begin(credentials)
    
    challenge_id = str(uuid.uuid4())
    challenges[challenge_id] = state
    
    return {
        "options": fido2_options_to_dict(options),
        "challengeId": challenge_id
    }

async def verify_authentication(challenge_id: str, auth_response: dict):
    state = challenges.pop(challenge_id, None)
    if not state:
        raise Exception("CHALLENGE_EXPIRED")

    # Fetch the public key from DB
    cred_id_encoded = auth_response.get("id")
    db_cred = supabase.table("auth_credentials").select("*").eq("credential_id", cred_id_encoded).single().execute()
    if not db_cred.data:
        raise Exception("CREDENTIAL_NOT_FOUND")

    credential = AttestedCredentialData(websafe_decode(db_cred.data["public_key"]))
    parsed_response = AuthenticationResponse.from_dict(auth_response)

    get_fido_server().authenticate_complete(
        state,
        [credential],
        parsed_response
    )

    assertion = AuthenticationResponse.from_dict(auth_response)
    new_sign_count = assertion.response.authenticator_data.counter
    
    # Store the sign count update
    supabase.table("auth_credentials").update({
        "sign_count": new_sign_count,
        "last_used_at": datetime.now(timezone.utc).isoformat(),
    }).eq("credential_id", cred_id_encoded).execute()

    # Create session
    session_token = base64.urlsafe_b64encode(os.urandom(32)).decode()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    
    supabase.table("auth_sessions").insert({
        "session_token": session_token,
        "credential_id": cred_id_encoded,
        "expires_at": expires_at
    }).execute()
    
    return {"status": "success", "sessionToken": session_token}

async def validate_session(token: str | None) -> bool:
    if not token:
        return False
    # Use maybe_single() so 0-row results return None instead of raising PGRST116
    res = supabase.table("auth_sessions").select("*").eq("session_token", token).maybe_single().execute()
    if not res or not res.data:
        return False

    expires = datetime.fromisoformat(res.data["expires_at"].replace("Z", "+00:00"))
    if expires < datetime.now(timezone.utc):
        return False

    return True
