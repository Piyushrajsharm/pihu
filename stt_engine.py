"""
Pihu — STT Engine
Speech-to-Text using faster-whisper. CPU-first with optional GPU acceleration.
"""

import time
import numpy as np

from logger import get_logger

log = get_logger("STT")


class STTEngine:
    """Speech-to-Text using faster-whisper.
    
    Default: CPU (int8) for low resource usage.
    Optional: GPU acceleration if scheduler approves.
    Target latency: < 800ms.
    """

    def __init__(self, scheduler=None):
        from config import (
            STT_MODEL, STT_DEVICE, STT_COMPUTE_TYPE,
            STT_BEAM_SIZE, STT_LANGUAGE,
        )

        self.model_size = STT_MODEL
        self.beam_size = STT_BEAM_SIZE
        self.language = STT_LANGUAGE
        self.scheduler = scheduler

        # Determine device
        device = STT_DEVICE
        compute_type = STT_COMPUTE_TYPE
        if scheduler and scheduler.get_device("stt") == "gpu":
            device = "cuda"
            compute_type = "float16"

        self._model = None
        self._device = device
        self._compute_type = compute_type

        log.info(
            "STT Engine config: model=%s, device=%s, compute=%s",
            self.model_size, device, compute_type,
        )

    def load(self):
        """Load the Whisper model. Call once at startup."""
        from faster_whisper import WhisperModel

        t0 = time.time()
        log.info("Loading faster-whisper model '%s'...", self.model_size)

        try:
            self._model = WhisperModel(
                self.model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            elapsed = time.time() - t0
            log.info("✅ STT model loaded in %.1fs", elapsed)
        except Exception as e:
            log.error("Failed to load STT model on %s: %s", self._device, e)
            if self._device != "cpu":
                log.info("Falling back to CPU...")
                self._device = "cpu"
                self._compute_type = "int8"
                self._model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8",
                )
                log.info("✅ STT model loaded on CPU (fallback)")
                if self.scheduler:
                    self.scheduler.on_gpu_crash()

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to text.
        
        Args:
            audio: numpy array of audio samples (int16 or float32, 16kHz mono)

        Returns:
            Transcribed text string.
        """
        if self._model is None:
            self.load()

        # Normalize audio to float32 [-1, 1]
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        t0 = time.time()

        segments, info = self._model.transcribe(
            audio,
            beam_size=self.beam_size,
            language=self.language,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
        )

        # Collect all segment texts
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        text = " ".join(text_parts).strip()
        elapsed_ms = (time.time() - t0) * 1000

        log.info(
            "📝 Transcribed in %.0fms | lang=%s | text='%s'",
            elapsed_ms, info.language, text[:80],
        )

        if elapsed_ms > 800:
            log.warning("⚠️ STT latency %.0fms exceeds 800ms target", elapsed_ms)

        return text

    def transcribe_with_language(self, audio: np.ndarray) -> tuple[str, str]:
        """Transcribe and return (text, detected_language)."""
        if self._model is None:
            self.load()

        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        segments, info = self._model.transcribe(
            audio,
            beam_size=self.beam_size,
            vad_filter=True,
        )

        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text, info.language
