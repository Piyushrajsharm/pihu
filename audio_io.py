"""
Pihu — Audio I/O
Microphone capture with VAD (Voice Activity Detection) and speaker playback.
"""

import queue
import threading
import numpy as np

from logger import get_logger

log = get_logger("AUDIO")


class MicrophoneStream:
    """Real-time microphone capture with Voice Activity Detection.
    
    Uses energy-based VAD + optional webrtcvad for robust speech detection.
    Returns audio chunks when speech is detected, silence triggers end-of-utterance.
    """

    def __init__(self):
        import sounddevice as sd
        from config import (
            AUDIO_SAMPLE_RATE, AUDIO_CHANNELS,
            AUDIO_CHUNK_DURATION_MS, AUDIO_SILENCE_THRESHOLD_MS,
        )

        self.sample_rate = AUDIO_SAMPLE_RATE
        self.channels = AUDIO_CHANNELS
        self.chunk_ms = AUDIO_CHUNK_DURATION_MS
        self.silence_threshold_ms = AUDIO_SILENCE_THRESHOLD_MS
        self.chunk_size = int(self.sample_rate * self.chunk_ms / 1000)

        # VAD setup
        self._vad = None
        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(3)  # Aggressiveness 0-3 (3 is most aggressive)
            log.info("WebRTC VAD initialized (aggressiveness=3)")
        except ImportError:
            log.warning("webrtcvad not available, using energy-based VAD")

        self._audio_queue: queue.Queue = queue.Queue()
        self._is_recording = False
        self._stream = None

        # Energy threshold for simple VAD
        self._energy_threshold = 0.05  # Increased to prevent background noise triggers

        log.info(
            "MicrophoneStream ready | rate=%dHz, chunk=%dms",
            self.sample_rate, self.chunk_ms,
        )

    def _audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice for each audio chunk."""
        if status:
            log.warning("Audio input status: %s", status)
        self._audio_queue.put(indata.copy())

    def start(self):
        """Start recording from microphone."""
        import sounddevice as sd

        if self._is_recording:
            return

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.chunk_size,
            dtype="int16",
            callback=self._audio_callback,
        )
        self._stream.start()
        self._is_recording = True
        log.info("🎤 Microphone started")

    def stop(self):
        """Stop recording."""
        self._is_recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        log.info("🎤 Microphone stopped")

    def listen_for_utterance(self, max_duration_s: float = 15.0) -> np.ndarray | None:
        """Block until a complete utterance is captured.
        
        Returns numpy array of audio (int16) or None if timeout.
        Detects speech start → waits for silence → returns the utterance.
        """
        frames = []
        speech_started = False
        silence_frames = 0
        silence_frames_needed = int(self.silence_threshold_ms / self.chunk_ms)
        max_frames = int(max_duration_s * 1000 / self.chunk_ms)
        frame_count = 0

        while self._is_recording and frame_count < max_frames:
            try:
                chunk = self._audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            frame_count += 1
            is_speech = self._is_speech(chunk)

            if is_speech:
                speech_started = True
                silence_frames = 0
                frames.append(chunk)
            elif speech_started:
                silence_frames += 1
                frames.append(chunk)
                if silence_frames >= silence_frames_needed:
                    # End of utterance detected
                    break
            # else: still waiting for speech to start

        if not frames:
            return None

        audio = np.concatenate(frames, axis=0).flatten()
        duration_ms = len(audio) / self.sample_rate * 1000
        log.info("🎤 Captured utterance: %.0fms", duration_ms)
        return audio

    def _is_speech(self, chunk: np.ndarray) -> bool:
        """Detect if audio chunk contains speech."""
        # Try webrtcvad first
        if self._vad is not None:
            try:
                pcm = chunk.flatten().astype(np.int16).tobytes()
                return self._vad.is_speech(pcm, self.sample_rate)
            except Exception as e:
                log.debug("webrtcvad exception (likely chunk size mismatch), falling back to energy VAD: %s", e)

        # Fallback: energy-based detection
        energy = np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) / 32768.0
        return energy > self._energy_threshold


class AudioPlayer:
    """Non-blocking audio playback with queue support."""

    def __init__(self):
        from config import TTS_SAMPLE_RATE

        self.sample_rate = TTS_SAMPLE_RATE
        self._play_queue: queue.Queue = queue.Queue()
        self._is_playing = False
        self._stop_event = threading.Event()
        self._play_thread: threading.Thread | None = None

        log.info("AudioPlayer ready | rate=%dHz", self.sample_rate)

    def play(self, audio: np.ndarray, blocking: bool = False):
        """Play audio array.
        
        Args:
            audio: numpy array of audio samples (float32 or int16)
            blocking: if True, wait for playback to finish
        """
        import sounddevice as sd

        if blocking:
            self._play_direct(audio)
        else:
            self._play_queue.put(audio)
            if not self._is_playing:
                self._start_player_thread()

    def _play_direct(self, audio: np.ndarray):
        """Play audio synchronously."""
        import sounddevice as sd

        try:
            # Normalize to float32 if needed
            if audio.dtype == np.int16:
                audio = audio.astype(np.float32) / 32768.0

            sd.play(audio, self.sample_rate)
            sd.wait()
        except Exception as e:
            log.error("Playback error: %s", e)

    def _start_player_thread(self):
        """Start background playback thread."""
        self._is_playing = True
        self._stop_event.clear()
        self._play_thread = threading.Thread(
            target=self._player_loop, daemon=True
        )
        self._play_thread.start()

    def _player_loop(self):
        """Background loop that processes the play queue."""
        while not self._stop_event.is_set():
            try:
                audio = self._play_queue.get(timeout=0.5)
                self._play_direct(audio)
            except queue.Empty:
                break
        self._is_playing = False

    def stop(self):
        """Stop all playback immediately."""
        import sounddevice as sd

        self._stop_event.set()
        sd.stop()
        # Clear queue
        while not self._play_queue.empty():
            try:
                self._play_queue.get_nowait()
            except queue.Empty:
                break
        self._is_playing = False
        log.info("🔇 Playback stopped")

    def interrupt(self):
        """Interrupt current playback (e.g. user started speaking)."""
        self.stop()
        log.info("🔇 Playback interrupted")
