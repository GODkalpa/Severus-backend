import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from services.stt import RealTimeSTT
from services.brain import process_query
from services.tts import generate_tts

load_dotenv(".env.local")
load_dotenv()

app = FastAPI(title="Severus Voice AI Backend")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Severus Voice AI Backend is running"}

@app.websocket("/ws/severus")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected to /ws/severus")

    # Maintain message history for the duration of the session
    message_history = []

    async def handle_transcript(transcript_text: str):
        """
        Callback called when a final transcript is received from STT.
        """
        print(f"Processing transcript: {transcript_text}")
        
        # 1. Query the Brain with message history
        brain_response = await process_query(transcript_text, message_history)
        print(f"Brain response: {brain_response}")
        
        # 2. Generate TTS
        try:
            audio_response = await generate_tts(brain_response)
            
            # 3. Stream binary audio back to client
            await websocket.send_bytes(audio_response)
            print("Audio response sent to client")
        except Exception as e:
            print(f"Error in TTS or WebSocket send: {e}")

    # Initialize STT with the callback and current event loop
    loop = asyncio.get_running_loop()
    stt_handler = RealTimeSTT(on_transcript=handle_transcript, loop=loop)
    
    try:
        # Start the connection to AssemblyAI in a separate thread to avoid blocking the loop
        print("Connecting to AssemblyAI...")
        await asyncio.to_thread(stt_handler.connect)
        print("AssemblyAI connected successfully")
        
        while True:
            # Receive binary audio from the frontend
            data = await websocket.receive_bytes()
            
            # Pipe to AssemblyAI (this is non-blocking as it just queues the data)
            stt_handler.stream_audio(data)
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        stt_handler.close()
        print("STT session closed on websocket exit")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
