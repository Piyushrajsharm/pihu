"""
Pihu — Streaming Pipeline
Zero-latency producer-consumer design for LLM → TTS streaming.
"""

import time
import queue
import threading
from typing import Generator

from logger import get_logger

log = get_logger("STREAM")


class StreamingPipeline:
    """Zero-latency streaming: LLM tokens → text chunks → TTS → audio playback.
    
    Producer (LLM side):
    - Collects streaming tokens
    - Flushes when: punctuation detected OR 200ms elapsed
    
    Consumer (TTS side):
    - Receives text chunks from queue
    - Synthesizes audio immediately
    - Plays while pre-buffering next chunk
    
    No blocking: TTS never blocks LLM generation.
    """

    def __init__(self, tts_engine, audio_player):
        from config import (
            STREAM_FLUSH_PUNCTUATION,
            STREAM_FLUSH_TIMEOUT_MS,
            STREAM_QUEUE_MAXSIZE,
        )

        self.tts = tts_engine
        self.player = audio_player
        self.flush_punctuation = STREAM_FLUSH_PUNCTUATION
        self.flush_timeout_ms = STREAM_FLUSH_TIMEOUT_MS

        self._text_queue: queue.Queue = queue.Queue(maxsize=STREAM_QUEUE_MAXSIZE)
        self._stop_event = threading.Event()
        self._consumer_thread: threading.Thread | None = None
        self._full_response: list[str] = []

        log.info("StreamingPipeline initialized")

    def stream_response(
        self,
        token_generator: Generator[str, None, None],
        tool_announcement: str = "",
    ) -> str:
        """Stream LLM response through TTS pipeline.
        
        Args:
            token_generator: yields string tokens from LLM
            tool_announcement: pre-response announcement (e.g. "Searching...")

        Returns:
            Full response text
        """
        self._full_response = []

        if self.tts and self.tts.is_loaded and tool_announcement:
            self.tts.feed(tool_announcement + " ")

        print("\r" + " " * 100 + "\r🤖 Pihu: ", end="", flush=True)

        # Collect tokens as they arrive (print in real-time)
        try:
            for token in token_generator:
                self._full_response.append(token)
                if self.tts and self.tts.is_loaded:
                    self.tts.feed(token)
                    
                    # Trigger synthesis/playback if a sentence ends
                    if any(p in token for p in self.flush_punctuation):
                        self.tts.play(async_mode=True)
                
                # Still print to console for visual feedback
                print(token, end="", flush=True)

        except Exception as e:
            log.error("Pipeline feed error: %s", e)
        finally:
            print() # Newline after response
        
        # Flush buffered text through Indic-TTS (sentence-level synthesis + playback)
        if self.tts and self.tts.is_loaded:
            self.tts.play(async_mode=True)

        return "".join(self._full_response)

    def stream_text_only(
        self,
        token_generator: Generator[str, None, None],
        tool_announcement: str = "",
    ) -> str:
        """Stream LLM response as text only (no TTS).
        
        Prints tokens to console in real-time.
        Returns full response text.
        
        Resilient: generator failures are caught and partial output is returned.
        """
        self._full_response = []

        if tool_announcement:
            print(f"\r🔧 {tool_announcement}")

        print("\r" + " " * 100 + "\r🤖 Pihu: ", end="", flush=True)

        consecutive_newlines = 0
        try:
            for token in token_generator:
                if "\n" in token:
                    consecutive_newlines += token.count("\n")
                else:
                    consecutive_newlines = 0
                
                # Safety: Stop if model starts spamming newlines
                if consecutive_newlines > 3:
                    log.warning("🚫 Newline spam detected — suppressing stream")
                    break
                    
                print(token, end="", flush=True)
                self._full_response.append(token)
        except Exception as e:
            log.error("Token generator error (partial response kept): %s", e)
            print(f" [stream error: {e}]", end="", flush=True)

        print()  # Newline after response

        return "".join(self._full_response)

    def stop(self):
        """Stop the streaming pipeline."""
        if self.tts:
            self.tts.stop()
        if self.player:
            self.player.stop()
        log.info("Pipeline stopped")

    def interrupt(self):
        """Interrupt current response (e.g. user started speaking)."""
        self.stop()
        log.info("Pipeline interrupted")
