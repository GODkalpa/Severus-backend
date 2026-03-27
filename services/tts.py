import edge_tts
import io

async def generate_tts(text: str, voice: str = "en-GB-ThomasNeural") -> bytes:
    """
    Generates TTS audio using edge-tts and returns it as binary data.
    """
    communicate = edge_tts.Communicate(text, voice)
    audio_data = io.BytesIO()
    
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.write(chunk["data"])
            
    return audio_data.getvalue()
