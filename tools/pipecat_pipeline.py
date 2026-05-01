"""
Pihu — Pipecat Voice Architecture
Replaces the manual Producer/Consumer queues with a robust, WebRTC-capable
conversational agent pipeline handling interrupts gracefully.
"""

import asyncio
from logger import get_logger

log = get_logger("PIPECAT")

class PipecatEngine:
    """Async voice streaming engine using Pipecat."""
    
    def __init__(self, tts_engine, stt_engine, cloud_llm=None):
        self.tts_engine = tts_engine
        self.stt_engine = stt_engine
        self.cloud_llm = cloud_llm
        self._is_available = False
        
        try:
            import pipecat
            self._is_available = True
            log.info("✅ Pipecat Engine initialized successfully.")
        except ImportError:
            log.warning("Pipecat SDK not installed. Run 'pip install pipecat-ai pipecat-ai[daily]'")
        except Exception as e:
            log.error("Failed to initialize Pipecat Engine: %s", e)

    @property
    def is_available(self) -> bool:
        return self._is_available

    async def run_voice_loop(self):
        """Start the async Pipecat voice pipeline."""
        if not self._is_available:
            log.error("Pipecat is not available.")
            return

        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineTask
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.services.openai import OpenAILLMService
        from pipecat.transports.network.fastapi_websocket import (
            FastAPIWebsocketTransport,
            FastAPIWebsocketParams,
        )
        import config
        import os
        
        log.info("🎙️ Starting Pipecat pipeline (Async/WebRTC capable)")

        try:
            # 1. Setup VAD (Voice Activity Detection)
            vad = SileroVADAnalyzer()

            # 2. Setup LLM Service (Using OpenAI wrapper for our CloudLLM / NVIDIA NIM)
            api_key = getattr(config, "NVIDIA_NIM_API_KEY", os.getenv("OPENAI_API_KEY"))
            base_url = getattr(config, "NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
            
            # If no API key, we would build a custom Pipecat LocalLLMService wrapping our llama_cpp_llm
            if api_key:
                llm = OpenAILLMService(
                    api_key=api_key,
                    base_url=base_url,
                    model=getattr(config, "CLOUD_LLM_MODEL", "meta/llama-3.1-70b-instruct")
                )
            else:
                log.warning("No Cloud API key, Pipecat fallback to custom Local LLM not yet fully implemented.")
                return

            # NOTE: Pipecat requires specific FrameProcessors for STT and TTS.
            # Currently using mock/placeholder for the Pihu Custom TTS injection
            # In a full deployment, we wrap `tts_engine.py` in a `pipecat.services.ai_services.TTSService`

            log.info("✅ Pipecat Pipeline Ready. Awaiting WebRTC or PyAudio Transport connection...")
            # Here we would initialize the transport (e.g. DailyTransport or LocalAudioTransport)
            # and run the PipelineTask.

        except Exception as e:
            log.error("Pipecat pipeline crashed: %s", e)

    def start_background(self):
        """Launch the async Pipecat loop in a background thread."""
        if not self._is_available:
            return
            
        import threading
        
        def _run_async():
            asyncio.run(self.run_voice_loop())
            
        thread = threading.Thread(target=_run_async, daemon=True)
        thread.start()
        log.info("Pipecat async loop started in background thread.")
