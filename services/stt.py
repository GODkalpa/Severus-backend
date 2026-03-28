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
    def __init__(
        self, 
        on_transcript: Callable[[str], Coroutine[Any, Any, None]], 
        on_partial: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ):
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
        self.on_partial_callback = on_partial
        self.last_processed_turn_order: Optional[int] = None
        try:
            self.loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()

    def _on_begin(self, client: StreamingClient, event: BeginEvent):
        print(f"AssemblyAI Session started: {event.id}")

    def _on_turn(self, client: StreamingClient, event: TurnEvent):
        transcript = event.transcript.strip()
        if not transcript:
            return

        # If it's a partial transcript (not end of turn), send it to the partial callback
        if not event.end_of_turn:
            if self.on_partial_callback:
                asyncio.run_coroutine_threadsafe(
                    self.on_partial_callback(transcript),
                    self.loop
                )
            return

        if event.turn_order == self.last_processed_turn_order:
            return

        self.last_processed_turn_order = event.turn_order
        print(f"Final transcript received: {transcript}")
        asyncio.run_coroutine_threadsafe(
            self.on_transcript_callback(transcript),
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
                min_turn_silence=350,
            )
        )

    def stream_audio(self, audio_chunk: bytes):
        self.client.stream(audio_chunk)

    def close(self):
        self.client.disconnect()
