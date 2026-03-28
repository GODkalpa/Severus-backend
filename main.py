import os
import asyncio
import re
import json
from datetime import datetime, timezone
from urllib.parse import urlparse
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv()

from services.stt import RealTimeSTT
from services.brain import process_query_stream, supabase, clean_spoken_text
from services.tts import generate_tts_stream
from services.auth_service import (
    generate_registration_options, 
    verify_registration, 
    generate_authentication_options, 
    verify_authentication,
    validate_session
)
from services.push_service import save_subscription
from worker import run_context_engine
import json

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle application lifecycle events.
    """
    print("🚀 [REVELIO] Launching 24/7 Context Engine...")
    task = asyncio.create_task(run_context_engine())
    yield
    # Shutdown logic
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("🛑 Context Engine stopped.")

app = FastAPI(title="Severus Voice AI Backend", lifespan=lifespan)


def parse_allowed_origins() -> list[str]:
    raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    origins = [get_http_origin(origin.strip()) for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["*"]


def get_http_origin(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return value.rstrip("/")


def build_dashboard_snapshot() -> dict[str, list[dict]]:
    if not supabase:
        raise RuntimeError("Supabase client is not configured.")

    today = datetime.now(timezone.utc).date().isoformat()

    biometrics = (
        supabase.table("biometrics")
        .select("*")
        .gte("logged_at", today)
        .order("logged_at", desc=True)
        .execute()
    )
    action_items = (
        supabase.table("action_items")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    financial_ledger = (
        supabase.table("financial_ledger")
        .select("*")
        .gte("logged_at", today)
        .order("logged_at", desc=True)
        .execute()
    )

    return {
        "biometrics": biometrics.data or [],
        "action_items": action_items.data or [],
        "financial_ledger": financial_ledger.data or [],
    }

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Severus Voice AI Backend is running"}

# --- AUTH ROUTES ---

@app.post("/api/auth/register/begin")
async def register_begin(payload: dict):
    user_id = payload.get("user_id")
    master_secret = payload.get("master_secret")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        return await generate_registration_options(user_id, master_secret)
    except Exception as e:
        if str(e) == "MASTER_SECRET_REQUIRED":
            raise HTTPException(status_code=401, detail="MASTER_SECRET_REQUIRED")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/auth/register/begin")
async def register_begin_legacy(user_id: str, master_secret: str = None):
    try:
        return await generate_registration_options(user_id, master_secret)
    except Exception as e:
        if str(e) == "MASTER_SECRET_REQUIRED":
            raise HTTPException(status_code=401, detail="MASTER_SECRET_REQUIRED")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/register/complete")
async def register_complete(challenge_id: str, response: dict):
    try:
        return await verify_registration(challenge_id, response)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/auth/login/begin")
async def login_begin():
    try:
        return await generate_authentication_options()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/login/complete")
async def login_complete(challenge_id: str, response: dict):
    try:
        return await verify_authentication(challenge_id, response)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- PROTECTED ROUTES ---

@app.post("/api/push/subscribe")
async def subscribe_push(subscription: dict, token: str = None):
    """
    Registers a new device subscription for 24/7 background alerts.
    """
    if not await validate_session(token):
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")
    
    result = await save_subscription(subscription)
    if result:
        return {"status": "success", "message": "REVELIO_UPLINK_ESTABLISHED"}
    else:
        raise HTTPException(status_code=500, detail="VAULT_WRITE_ERROR")

@app.get("/api/dashboard")
async def dashboard(token: str = None):
    if not await validate_session(token):
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")
    try:
        return await asyncio.to_thread(build_dashboard_snapshot)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to load dashboard data.") from exc

@app.websocket("/ws/severus")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # 0. Wait for authentication token
    try:
        # Use a timeout for initial auth to prevent hanging connections
        auth_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        auth_data = json.loads(auth_msg)
        if auth_data.get("type") != "AUTH" or not await validate_session(auth_data.get("token")):
            await websocket.send_text(json.dumps({
                "type": "ERROR", 
                "message": "UNAUTHORIZED",
                "detail": "Invalid or expired session token."
            }))
            await websocket.close(code=4003)
            return
    except asyncio.TimeoutError:
        await websocket.close(code=4008) # Policy Violation / Timeout
        return
    except Exception as e:
        print(f"Auth error: {e}")
        await websocket.close()
        return

    print("Client authenticated for /ws/severus")
    
    # Maintain message history for the duration of the session
    message_history = []

    # 1. Send initial system metrics
    from services.brain import MODEL
    await websocket.send_text(json.dumps({
        "type": "SYSMETRICS",
        "model": MODEL,
        "frequency": 74.2, # Base frequency
        "status": "connected"
    }))

    async def handle_partial_transcript(partial_text: str):
        """
        Callback for partial (ghost) transcripts.
        """
        await websocket.send_text(f"PARTIAL:{partial_text}")

    async def handle_transcript(transcript_text: str):
        """
        Callback called when a final transcript is received from STT.
        Streams sentence-by-sentence LLM responses and TTS.
        """
        print(f"Processing transcript: {transcript_text}")
        await websocket.send_text("THINKING")
        await websocket.send_text(f"TRANSCRIPT:{transcript_text}")
        
        async def stream_sentence_audio(sentence: str):
            print(f"Aggregating TTS for sentence: {sentence}")
            try:
                # Accumulate all chunks for a single sentence to avoid choppiness in the frontend
                full_audio = b""
                async for audio_chunk in generate_tts_stream(sentence):
                    full_audio += audio_chunk
                
                if full_audio:
                    await websocket.send_bytes(full_audio)
                    print(f"Sent full audio blob for sentence ({len(full_audio)} bytes)")
            except Exception as e:
                print(f"Error in TTS generation: {e}")

        # Accumulate chunks and split by sentences
        sentence_buffer = ""
        try:
            async for chunk in process_query_stream(transcript_text, message_history):
                sentence_buffer += chunk
                
                # Check for sentence endpoints (simple regex for . ! ? or newline)
                # Matches punctuation followed by whitespace or end of string
                parts = re.split(r'(?<=[.!?])\s+|\n', sentence_buffer)
                
                if len(parts) > 1:
                    # All parts except the last one are guaranteed to be complete
                    for sentence in parts[:-1]:
                        s_cleaned = clean_spoken_text(sentence)
                        if s_cleaned:
                            await stream_sentence_audio(s_cleaned)
                    sentence_buffer = parts[-1]
            
            # Final portion of the response
            s_final = clean_spoken_text(sentence_buffer)
            if s_final:
                await stream_sentence_audio(s_final)
            
            # Signal the client that the current response sequence is complete
            # This helps the frontend know when to resume recording
            await websocket.send_text("EOS") # End Of Stream signal
            print("Response sequence completed (EOS sent)")
            
        except Exception as e:
            print(f"Error in handle_transcript: {e}")
            await websocket.send_text("EOS")

    # Initialize STT with the callback and current event loop
    loop = asyncio.get_running_loop()
    stt_handler = RealTimeSTT(
        on_transcript=handle_transcript, 
        on_partial=handle_partial_transcript,
        loop=loop
    )
    
    # Start STT connection as a background task so we can start receiving data immediately
    # This prevents the initial handshake from timing out on the client side.
    stt_task = asyncio.create_task(asyncio.to_thread(stt_handler.connect))
    
    try:
        while True:
            # Receive binary audio from the frontend
            data = await websocket.receive_bytes()
            
            # Pipe to AssemblyAI (only if connected, otherwise queue or wait)
            # stt_handler.stream_audio is non-blocking
            stt_handler.stream_audio(data)
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        stt_handler.close()
        stt_task.cancel()
        print("STT session closed on websocket exit")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
