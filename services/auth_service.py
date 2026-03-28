import os
import base64
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
from fido2.server import Fido2Server
from fido2.webauthn import (
    UserVerificationRequirement,
    AuthenticatorAttachment,
    PublicKeyCredentialRpEntity,
)
from fido2.utils import websafe_decode, websafe_encode
from services.brain import supabase

# WebAuthn Configuration
RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
RP_NAME = "SEVERUS_HUD"
ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost:3000")

RP = PublicKeyCredentialRpEntity(id=RP_ID, name=RP_NAME)
server = Fido2Server(RP)

# In-memory challenge store (Session based or DB based)
# For simplicity, we'll store challenges in a small global dict for now, 
# but in production, this should be in Redis or DB with an expiry.
challenges = {}

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

async def generate_registration_options(user_id: str, master_secret: str = None):
    # If no credentials exist yet, require master secret
    existing = supabase.table("auth_credentials").select("id").limit(1).execute()
    if not existing.data and master_secret != get_master_secret():
        raise Exception("MASTER_SECRET_REQUIRED")

    user = {"id": websafe_decode(websafe_encode(user_id.encode())), "name": "SeverusOwner", "displayName": "Severus Owner"}
    
    # Check if user already has registered credentials
    credentials = []
    reg_response = supabase.table("auth_credentials").select("credential_id").execute()
    for row in reg_response.data:
        credentials.append(websafe_decode(row["credential_id"]))

    options, state = server.register_begin(
        user,
        credentials,
        authenticator_attachment=AuthenticatorAttachment.PLATFORM,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    
    challenge_id = str(uuid.uuid4())
    challenges[challenge_id] = state
    
    # Serialize for frontend - HUD expects options.publicKey
    return {
        "options": {"publicKey": fido2_options_to_dict(options)}, 
        "challengeId": challenge_id
    }

async def verify_registration(challenge_id: str, challenge_response: dict):
    state = challenges.pop(challenge_id, None)
    if not state:
        raise Exception("CHALLENGE_EXPIRED")

    auth_data = server.register_complete(state, challenge_response)
    
    # Store in Supabase
    credential_data = {
        "credential_id": websafe_encode(auth_data.credential_data.credential_id),
        "public_key": websafe_encode(auth_data.credential_data.public_key),
        "sign_count": auth_data.credential_data.counter,
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
        credentials.append(websafe_decode(row["credential_id"]))

    options, state = server.authenticate_begin(credentials)
    
    challenge_id = str(uuid.uuid4())
    challenges[challenge_id] = state
    
    return {
        "options": {"publicKey": fido2_options_to_dict(options)}, 
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

    # fido2 expects the credential to be passed back for verification
    # This is a bit complex with manual storage, usually you use a CredentialSource
    # but we can verify manually or use a helper.
    
    # Verify the signature using the registered credential
    from fido2.webauthn import AttestedCredentialData
    
    credential = AttestedCredentialData(websafe_decode(db_cred.data["public_key"]))
    # (AttestedCredentialData expects a public key, we use the stored one)
    # Actually, authenticate_complete in 2.x is simpler if we have the CredentialSource
    # We'll use the low-level verification if authenticate_complete is tricky without a full CredentialSource
    
    auth_data = server.authenticate_complete(
        state,
        [credential],
        auth_response
    )
    
    # Store the sign count update
    supabase.table("auth_credentials").update({"sign_count": auth_data.counter}).eq("credential_id", cred_id_encoded).execute()

    # Create session
    session_token = base64.b64encode(os.urandom(32)).decode()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    
    supabase.table("auth_sessions").insert({
        "session_token": session_token,
        "credential_id": cred_id_encoded,
        "expires_at": expires_at
    }).execute()
    
    return {"status": "success", "sessionToken": session_token}

async def validate_session(token: str):
    res = supabase.table("auth_sessions").select("*").eq("session_token", token).single().execute()
    if not res.data:
        return False
    
    expires = datetime.fromisoformat(res.data["expires_at"].replace("Z", "+00:00"))
    if expires < datetime.now(timezone.utc):
        return False
        
    return True
