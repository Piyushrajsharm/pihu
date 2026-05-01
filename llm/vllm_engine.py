"""
Pihu — vLLM Inference Engine
Direct local inference via vLLM for high-throughput, low-latency generation.
Requires Linux/WSL and a compatible GPU.
"""

import time
import json
from typing import Generator, Optional, Any

from logger import get_logger
from llm.base_provider import BaseProvider

log = get_logger("vLLM")

class VllmEngine(BaseProvider):
    """High-throughput inference engine using vLLM."""

    def __init__(self, scheduler=None):
        import config
        from pathlib import Path
        
        self.model_path = str(Path(config.LOCAL_MODEL_PATH))
        self.temperature = config.LOCAL_LLM_TEMPERATURE
        self.max_tokens = config.LOCAL_LLM_MAX_TOKENS
        self.scheduler = scheduler
        self._is_available = False
        self.llm = None
        
        try:
            # vLLM is heavy and strictly requires specific platforms (CUDA/ROCm)
            # If it fails to import or initialize, we degrade gracefully to llama_cpp_llm
            from vllm import LLM
            
            p = Path(config.LOCAL_MODEL_PATH)
            if not p.exists():
                log.info("🏠 vLLM check: Local GGUF/Safetensors not found")
                return

            log.info("🚀 Loading vLLM engine: %s...", p.name)
            t0 = time.time()
            
            # vLLM Initialization
            # Note: vLLM usually expects HuggingFace format or specific GGUFs. 
            # We configure basic params here, but in production, `tensor_parallel_size`
            # and `gpu_memory_utilization` should be tuned based on HW.
            self.llm = LLM(
                model=self.model_path,
                gpu_memory_utilization=0.5, # Play it safe with VRAM
                max_model_len=4096,
                enforce_eager=False,
                trust_remote_code=True
            )
            
            log.info("✅ vLLM engine loaded in %.1fs", time.time() - t0)
            self._is_available = True
            
        except ImportError:
            log.warning("vLLM not installed or not supported on this OS (Windows). Skipping.")
        except Exception as e:
            log.warning("vLLM failed to initialize (likely no CUDA or VRAM limit): %s", e)

    @property
    def is_available(self) -> bool:
        return getattr(self, "_is_available", False)

    def health_check(self) -> dict[str, Any]:
        if not self.is_available:
            return {"available": False, "latency_ms": 0, "model_name": self.model_path, "error": "vLLM not initialized"}
        return {"available": True, "latency_ms": 0, "model_name": self.model_path}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return 0.0

    def _format_prompt(self, prompt: str, system_prompt: str, context: Optional[list[str]], conversation_history: Optional[list[dict]]) -> str:
        # Standard chatml-ish formatting matching the llama_cpp_llm implementation
        system_text = system_prompt
        if context:
            system_text += "\nContext:\n" + "\n".join(f"- {c}" for c in context)
            
        formatted = f"<|system|>\n{system_text}<|end|>\n"
        
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                formatted += f"<|{role}|>\n{content}<|end|>\n"
                
        formatted += f"<|user|>\n{prompt}<|end|>\n<|assistant|>\n"
        return formatted

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = True,
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> Generator[str, None, None] | str | None:
        
        if not self.is_available:
            return None

        if stream:
            return self.generate_stream(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override, stop_sequences)
        return self.generate_batch(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override, stop_sequences)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> Generator[str, None, None]:
        
        if not self.is_available:
            return
            
        from vllm import SamplingParams
        
        formatted_prompt = self._format_prompt(prompt, system_prompt, context, conversation_history)
        max_tok = max_tokens_override or self.max_tokens
        
        stops = ["<|end|>", "<|user|>", "<|system|>"] + (stop_sequences or [])
        sampling_params = SamplingParams(
            temperature=self.temperature, 
            max_tokens=max_tok,
            stop=stops
        )
        
        t0 = time.time()
        
        try:
            # vLLM offline inference isn't naturally yield-based streamable via a simple iterator
            # without using the AsyncLLMEngine. For this simple BaseProvider, we simulate
            # streaming by grabbing the output and chunking it, or we would rely on
            # AsyncLLMEngine.generate() if we were in an async context.
            # To keep it completely synchronous for Pihu's existing architecture:
            
            outputs = self.llm.generate([formatted_prompt], sampling_params, use_tqdm=False)
            text = outputs[0].outputs[0].text
            
            # Simulate streaming chunks (since vLLM is incredibly fast anyway)
            # A true production vLLM integration would use an API server or AsyncLLMEngine
            chunk_size = 4
            for i in range(0, len(text), chunk_size):
                if i == 0:
                    log.info("⚡ vLLM first token simulated in %.0fms", (time.time() - t0)*1000)
                yield text[i:i+chunk_size]

            log.info("🧠 vLLM generation complete in %.1fs", time.time() - t0)
        except Exception as e:
            log.error("vLLM generation failed: %s", e)

    def generate_batch(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> str | None:
        
        if not self.is_available:
            return None
            
        from vllm import SamplingParams
            
        formatted_prompt = self._format_prompt(prompt, system_prompt, context, conversation_history)
        max_tok = max_tokens_override or self.max_tokens
        stops = ["<|end|>", "<|user|>", "<|system|>"] + (stop_sequences or [])
        
        sampling_params = SamplingParams(
            temperature=self.temperature, 
            max_tokens=max_tok,
            stop=stops
        )
        
        t0 = time.time()
        
        try:
            outputs = self.llm.generate([formatted_prompt], sampling_params, use_tqdm=False)
            text = outputs[0].outputs[0].text
            log.info("🧠 vLLM batch generation complete in %.1fs", time.time() - t0)
            return text
        except Exception as e:
            log.error("vLLM batch generation failed: %s", e)
            return None

    def generate_structured(self, prompt: str, schema: dict, system_prompt: str = "") -> dict | str | None:
        sys = system_prompt + f"\n\nYou MUST return ONLY raw JSON matching exactly this schema: {json.dumps(schema)}"
        result = self.generate_batch(prompt, system_prompt=sys)
        if not result:
            return None
        clean = result.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return clean
