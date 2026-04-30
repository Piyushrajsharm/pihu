"""
Pihu — TTS Engine (Indic-TTS / AI4Bharat)

Replaces the old RealtimeTTS + Kokoro pipeline with:
  FastPitch (spectrogram generator) → HiFi-GAN (vocoder)
  via TTS.utils.synthesizer.Synthesizer

CPU-only execution. Sentences are buffered and synthesized
one at a time for pseudo-streaming playback via an internal queue.
"""

import sys
import os
import io
import re
import time
import threading
import queue
import numpy as np
from typing import Optional

from logger import get_logger

log = get_logger("TTS")

# Prioritize local patched TTS fork
LOCAL_TTS_PATH = os.path.join(os.path.dirname(__file__), "third_party", "TTS")
if os.path.exists(LOCAL_TTS_PATH) and LOCAL_TTS_PATH not in sys.path:
    sys.path.insert(0, LOCAL_TTS_PATH)
    log.info("📍 Prioritizing local TTS fork from: %s", LOCAL_TTS_PATH)

# Sentence boundary regex — handles English + Hindi (Devanagari purna viram)
_SENTENCE_RE = re.compile(r'(?<=[.!?।])\s+')


class TTSEngine:
    """Text-to-Speech with a clear local backend and an internal worker queue.

    Architecture:
        1. `feed()` buffers incoming text chunks.
        2. `play()` flushes the current buffer into the synthesis queue.
        3. A background `_worker` thread pulls sentences from the queue,
           synthesizes them with SAPI or Indic-TTS, and plays/speaks them.
    """

    def __init__(self):
        from config import (
            TTS_BACKEND,
            TTS_DEVICE,
            TTS_SAMPLE_RATE,
            TTS_LATENCY_TARGET_MS,
            SAPI_RATE,
            SAPI_VOLUME,
            SAPI_VOICE_HINT,
            INDIC_TTS_FASTPITCH_DIR,
            INDIC_TTS_HIFIGAN_DIR,
        )

        self.requested_backend = TTS_BACKEND.lower().strip()
        self.backend: Optional[str] = None
        self.device = TTS_DEVICE
        self.sample_rate = TTS_SAMPLE_RATE
        self.latency_target_ms = TTS_LATENCY_TARGET_MS
        self.sapi_rate = SAPI_RATE
        self.sapi_volume = SAPI_VOLUME
        self.sapi_voice_hint = SAPI_VOICE_HINT
        self.fastpitch_dir = INDIC_TTS_FASTPITCH_DIR
        self.hifigan_dir = INDIC_TTS_HIFIGAN_DIR

        self._synthesizer = None
        self._sapi_available = False
        
        # Buffering & Queuing
        self._buffer: list[str] = []
        self._buffer_lock = threading.Lock()
        
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        log.info(
            "TTS Engine config: backend=%s, device=%s, sample_rate=%d, latency_target=%dms",
            self.requested_backend, self.device, self.sample_rate, self.latency_target_ms,
        )

    def load(self):
        """Pre-load the configured TTS backend and start the worker thread."""
        requested = self.requested_backend

        if requested in ("auto", "sapi"):
            if self._load_sapi():
                self.backend = "sapi"
                self._start_worker()
                return
            if requested == "sapi":
                log.error("SAPI voice backend requested but unavailable")
                return

        if requested in ("auto", "indic"):
            if self._load_indic():
                self.backend = "indic"
                self._start_worker()
                return

        log.error("No TTS backend could be loaded")

    def _start_worker(self):
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def _load_sapi(self) -> bool:
        """Use Windows SAPI for clearer local speech on Roman Hinglish/English."""
        if sys.platform != "win32":
            return False

        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            voice = None
            selected = None
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                selected = self._select_sapi_voice(voice)
                preview = selected.GetDescription() if selected else "default voice"
                log.info("✅ Windows SAPI voice loaded: %s", preview)
                self._sapi_available = True
                return True
            finally:
                selected = None
                voice = None
                pythoncom.CoUninitialize()
        except Exception as e:
            log.warning("Windows SAPI voice unavailable: %s", e)
            self._sapi_available = False
            return False

    def _select_sapi_voice(self, voice):
        voices = voice.GetVoices()
        hints = [h.strip().lower() for h in self.sapi_voice_hint.split(";") if h.strip()]

        fallback = None
        for i in range(voices.Count):
            candidate = voices.Item(i)
            desc = candidate.GetDescription()
            desc_lower = desc.lower()
            if fallback is None:
                fallback = candidate
            if any(hint in desc_lower for hint in hints):
                voice.Voice = candidate
                return candidate

        if fallback is not None:
            voice.Voice = fallback
        return fallback

    def _load_indic(self) -> bool:
        """Pre-load the Indic-TTS synthesizer."""
        import os

        t0 = time.time()
        log.info("Loading Indic-TTS (FastPitch + HiFi-GAN)...")

        fastpitch_ckpt = os.path.join(self.fastpitch_dir, "best_model.pth")
        fastpitch_cfg = os.path.join(self.fastpitch_dir, "config.json")
        hifigan_ckpt = os.path.join(self.hifigan_dir, "best_model.pth")
        hifigan_cfg = os.path.join(self.hifigan_dir, "config.json")

        if not all(os.path.isfile(f) for f in [fastpitch_ckpt, fastpitch_cfg, hifigan_ckpt, hifigan_cfg]):
            log.error("Missing model files — run `python scripts/setup_indic_tts.py` first")
            return False

        try:
            from TTS.utils.synthesizer import Synthesizer

            self._synthesizer = Synthesizer(
                tts_checkpoint=fastpitch_ckpt,
                tts_config_path=fastpitch_cfg,
                vocoder_checkpoint=hifigan_ckpt,
                vocoder_config=hifigan_cfg,
                use_cuda=(self.device == "cuda"),
            )

            elapsed = time.time() - t0
            log.info("✅ Indic-TTS engine loaded in %.1fs", elapsed)
            return True

        except Exception as e:
            log.error("Failed to load Indic-TTS: %s", e)
            self._synthesizer = None
            return False

    @property
    def is_loaded(self) -> bool:
        return self.backend == "sapi" or self._synthesizer is not None

    def feed(self, text: str):
        """Feed a text chunk into the buffer."""
        if not text:
            return
        with self._buffer_lock:
            self._buffer.append(text)

    def play(self, async_mode: bool = True):
        """Flush the buffer into the synthesis queue."""
        with self._buffer_lock:
            full_text = "".join(self._buffer)
            self._buffer.clear()

        if not full_text.strip():
            return

        sentences = self._split_sentences(full_text)
        if not async_mode:
            for s in sentences:
                self._synthesize_and_play_one(s)
            return

        for s in sentences:
            self._queue.put(s)

    def stop(self):
        """Immediately halt audio output and clear the queue.
        Properly waits for worker thread to finish current operation.
        """
        self._stop_event.set()

        # Clear queue immediately
        cleared_count = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                cleared_count += 1
            except queue.Empty:
                break

        with self._buffer_lock:
            self._buffer.clear()

        # Wait for worker thread to finish (with timeout)
        if self._worker_thread and self._worker_thread.is_alive():
            try:
                self._worker_thread.join(timeout=2.0)
            except Exception as e:
                log.warning("TTS worker thread join timeout: %s", e)

        # Reset stop event for next use
        self._stop_event.clear()

    def synthesize(self, text: str):
        """Blocking synthesis for one-off calls."""
        if not self.is_loaded:
            return
        sentences = self._split_sentences(text)
        for s in sentences:
            self._synthesize_and_play_one(s)

    def _split_sentences(self, text: str) -> list[str]:
        text = text.replace("।", ".")
        sentences = _SENTENCE_RE.split(text)
        return [s.strip() for s in sentences if s.strip()]

    def _worker(self):
        """Background worker that processes the synthesis queue."""
        while True:
            try:
                sentence = self._queue.get(timeout=1.0)
                if self._stop_event.is_set():
                    self._queue.task_done()
                    continue
                
                self._synthesize_and_play_one(sentence)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                log.error("TTS Worker error: %s", e)

    def _synthesize_and_play_one(self, sentence: str):
        """Synthesize and play exactly one sentence."""
        if self.backend == "sapi":
            self._speak_sapi(sentence)
            return

        import sounddevice as sd
        t0 = time.time()
        
        # Guard against zero-length or near-zero length strings that crash vocoders
        cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', sentence).strip()
        if len(cleaned) < 3:
            log.debug("TTS: Sentence '%s' too short/invalid, skipping synthesis", sentence)
            return

        try:
            from logger import suppress_stdout_stderr
            # multi-speaker model, usually "female" is available
            with suppress_stdout_stderr():
                wav = self._synthesizer.tts(sentence, speaker_name="female")
                
            if not wav:
                return

            audio_np = np.array(wav, dtype=np.float32)
            peak = np.abs(audio_np).max()
            if peak > 0:
                audio_np = audio_np / peak * 0.95

            if self._stop_event.is_set():
                return

            elapsed_ms = (time.time() - t0) * 1000
            duration_ms = len(audio_np) / self.sample_rate * 1000
            log.debug("TTS: '%s' (RTF: %.2f)", sentence[:30], elapsed_ms / max(duration_ms, 1))

            sd.play(audio_np, samplerate=self.sample_rate)
            sd.wait()
        except Exception as e:
            log.error("TTS Synthesis error for '%s': %s", sentence[:30], e)

    def _speak_sapi(self, sentence: str):
        """Speak one sentence with Windows SAPI in the worker thread."""
        cleaned = re.sub(r"\s+", " ", sentence).strip()
        if len(cleaned) < 2:
            return

        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            voice = None
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                self._select_sapi_voice(voice)
                voice.Rate = self.sapi_rate
                voice.Volume = self.sapi_volume

                # 1 = async, 2 = purge. Polling lets stop()/interrupt() cut off speech.
                voice.Speak(cleaned, 1)
                while not self._stop_event.is_set():
                    if voice.WaitUntilDone(50):
                        break
                if self._stop_event.is_set():
                    voice.Speak("", 3)
            finally:
                voice = None
                pythoncom.CoUninitialize()
        except Exception as e:
            log.error("SAPI synthesis error for '%s': %s", sentence[:30], e)
