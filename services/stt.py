import assemblyai as aai
import os
import asyncio
from dotenv import load_dotenv
from typing import Callable, Coroutine, Optional, Any
from assemblyai.streaming.v3 import (
    StreamingClient,
    StreamingClientOptions,
    StreamingParameters,
    StreamingEvents,
    Encoding,
    SpeechModel,
    StreamingError,
    BeginEvent,
    TurnEvent,
    TerminationEvent,
)

load_dotenv(".env.local")
load_dotenv()

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

class RealTimeSTT:
    def __init__(self, on_transcript: Callable[[str], Coroutine[Any, Any, None]], loop: Optional[asyncio.AbstractEventLoop] = None):
        # Configure the Streaming Client (v3)
        self.client = StreamingClient(
            StreamingClientOptions(
                api_key=os.getenv("ASSEMBLYAI_API_KEY"),
            )
        )
        
        # Register events
        self.client.on(StreamingEvents.Begin, self._on_begin)
        self.client.on(StreamingEvents.Turn, self._on_turn)
        self.client.on(StreamingEvents.Error, self._on_error)
        self.client.on(StreamingEvents.Termination, self._on_close)
        
        self.on_transcript_callback = on_transcript
        try:
            self.loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()

    def _on_begin(self, client: StreamingClient, event: BeginEvent):
        print(f"AssemblyAI Session started: {event.id}")

    def _on_turn(self, client: StreamingClient, event: TurnEvent):
        if not event.transcript:
            return

        print(f"Transcript received: {event.transcript}")
        asyncio.run_coroutine_threadsafe(
            self.on_transcript_callback(event.transcript), 
            self.loop
        )

    def _on_error(self, client: StreamingClient, error: StreamingError):
        print(f"AssemblyAI Error: {error}")

    def _on_close(self, client: StreamingClient, event: TerminationEvent):
        print("AssemblyAI Session closed")

    def connect(self):
        # v3 connect takes parameters
        self.client.connect(
            StreamingParameters(
                speech_model=SpeechModel.universal_streaming_english,
                sample_rate=16_000,
                encoding=Encoding.pcm_s16le,
                min_end_of_turn_silence_when_confident=700,
            )
        )

    def stream_audio(self, audio_chunk: bytes):
        self.client.stream(audio_chunk)

    def close(self):
        self.client.disconnect()
