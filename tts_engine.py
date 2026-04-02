import time

from logger import get_logger
from RealtimeTTS import TextToAudioStream, KokoroEngine

log = get_logger("TTS")


class TTSEngine:
    """Text-to-Speech using RealtimeTTS + Kokoro.
    
    - CPU execution only
    - Preloaded at startup for <1.5s first-audio latency
    - Supports chunk-based synthesis for streaming pipeline
    """

    def __init__(self):
        from config import TTS_VOICE, TTS_SPEED

        self.voice = TTS_VOICE
        self.speed = TTS_SPEED
        self.engine = None
        self.stream = None

        log.info("TTS Engine config: voice=%s, speed=%.1f", self.voice, self.speed)

    def load(self):
        """Preload the RealtimeTTS + Kokoro engine. Call once at startup."""
        t0 = time.time()
        log.info("Loading RealtimeTTS Kokoro engine...")

        try:
            # 1. Initialize the Kokoro Backend
            self.engine = KokoroEngine(
                voice=self.voice
            )
            # Try to set speed if attribute exists
            if hasattr(self.engine, "speed"):
                self.engine.speed = self.speed
            
            # 2. Initialize the Streaming Wrapper
            self.stream = TextToAudioStream(self.engine)
            
            elapsed = time.time() - t0
            log.info("✅ RealtimeTTS engine loaded in %.1fs", elapsed)
        except Exception as e:
            log.error("Failed to load RealtimeTTS: %s", e)
            log.warning("TTS will be unavailable — responses will be text-only")

    @property
    def is_loaded(self) -> bool:
        return self.engine is not None and self.stream is not None

    def feed(self, text: str):
        """Feed a text chunk into the real-time buffer."""
        if self.stream:
            self.stream.feed(text)

    def play(self, async_mode: bool = True):
        """Start playback of the buffered stream."""
        if self.stream:
            if async_mode:
                self.stream.play_async()
            else:
                self.stream.play()

    def stop(self):
        """Immediately halt audio output."""
        if self.stream:
            self.stream.stop()

    def synthesize(self, text: str):
        """Feed text and play synchronously (compatibility method)."""
        if not self.is_loaded or not text or not text.strip():
            return None
        try:
            self.stream.feed(text)
            self.stream.play()
        except Exception as e:
            log.error("TTS synthesize failed: %s", e)
        return None
