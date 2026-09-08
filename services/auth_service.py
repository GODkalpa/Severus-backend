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
    ResidentKeyRequirement,
)
from fido2.utils import websafe_decode, websafe_encode
from services.db import supabase

class MasterSecretRequiredError(Exception):
    """Raised when master secret is missing or invalid during enrollment."""
    pass

RP_NAME = "SEVERUS_HUD"
DEFAULT_RP_ID = "localhost"
DEFAULT_ORIGIN = "http://localhost:3000"

# In-memory challenge store (Session based or DB based)
challenges = {}


def get_webauthn_rp_id() -> str:
    return os.getenv("WEBAUTHN_RP_ID", DEFAULT_RP_ID)


def get_webauthn_origin() -> str:
    return os.getenv("WEBAUTHN_ORIGIN", DEFAULT_ORIGIN).rstrip("/")


def get_fido_server() -> Fido2Server:
    rp_id = get_webauthn_rp_id()
    rp = PublicKeyCredentialRpEntity(id=rp_id, name=RP_NAME)
    expected_origin = get_webauthn_origin()

    def verify_origin(origin: str) -> bool:
        clean = origin.rstrip("/")
        if clean == expected_origin:
            return True
        if rp_id and clean in (f"https://{rp_id}", f"https://www.{rp_id}", f"http://{rp_id}"):
            return True
        return False

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
    expected_secret = get_master_secret()
    if not expected_secret or master_secret != expected_secret:
        raise MasterSecretRequiredError("MASTER_SECRET_REQUIRED")

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
        resident_key_requirement=ResidentKeyRequirement.PREFERRED,
    )
    
    challenge_id = str(uuid.uuid4())
    challenges[challenge_id] = state
    
    # Serialize for frontend - HUD expects options.publicKey
    return {
        "options": fido2_options_to_dict(options),
        "challengeId": challenge_id
    }

def _normalize_webauthn_payload(data: dict) -> dict:
    """
    Decodes base64url-encoded string fields sent by the browser into raw bytes
    as required by the fido2 library dataclasses, and ensures compatibility across
    fido2 v1.x (which looks for 'clientData') and v2.x (which looks for 'clientDataJSON').
    """
    d = dict(data)
    raw_raw = d.get("rawId") or d.get("raw_id")
    if raw_raw:
        raw_bytes = websafe_decode(raw_raw) if isinstance(raw_raw, str) else raw_raw
        d["rawId"] = raw_bytes
        d["raw_id"] = raw_bytes
        d["id"] = raw_bytes

    if "response" in d and isinstance(d["response"], dict):
        resp = dict(d["response"])

        # 1. client_data: map across all possible key aliases
        client_data_raw = resp.get("clientDataJSON") or resp.get("clientData") or resp.get("client_data")
        if client_data_raw:
            c_bytes = websafe_decode(client_data_raw) if isinstance(client_data_raw, str) else client_data_raw
            resp["clientDataJSON"] = c_bytes
            resp["clientData"] = c_bytes
            resp["client_data"] = c_bytes

        # 2. attestation_object: map across key aliases
        att_raw = resp.get("attestationObject") or resp.get("attestation_object")
        if att_raw:
            att_bytes = websafe_decode(att_raw) if isinstance(att_raw, str) else att_raw
            resp["attestationObject"] = att_bytes
            resp["attestation_object"] = att_bytes

        # 3. authenticator_data: map across key aliases
        auth_raw = resp.get("authenticatorData") or resp.get("authenticator_data") or resp.get("authData")
        if auth_raw:
            auth_bytes = websafe_decode(auth_raw) if isinstance(auth_raw, str) else auth_raw
            resp["authenticatorData"] = auth_bytes
            resp["authenticator_data"] = auth_bytes
            resp["authData"] = auth_bytes

        # 4. signature
        sig_raw = resp.get("signature")
        if sig_raw:
            resp["signature"] = websafe_decode(sig_raw) if isinstance(sig_raw, str) else sig_raw

        # 5. user_handle
        uh_raw = resp.get("userHandle") or resp.get("user_handle")
        if uh_raw and isinstance(uh_raw, str):
            resp["userHandle"] = websafe_decode(uh_raw)
            resp["user_handle"] = resp["userHandle"]
        else:
            resp["userHandle"] = None
            resp["user_handle"] = None

        d["response"] = resp
    return d


async def verify_registration(challenge_id: str, challenge_response: dict):
    state = challenges.pop(challenge_id, None)
    if not state:
        raise Exception("CHALLENGE_EXPIRED")

    normalized_response = _normalize_webauthn_payload(challenge_response)
    auth_data = get_fido_server().register_complete(state, RegistrationResponse.from_dict(normalized_response))
    
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
    normalized_response = _normalize_webauthn_payload(auth_response)
    parsed_response = AuthenticationResponse.from_dict(normalized_response)

    get_fido_server().authenticate_complete(
        state,
        [credential],
        parsed_response
    )

    new_sign_count = parsed_response.response.authenticator_data.counter
    
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
