"""
Pihu — Brain (Central Orchestrator)
Wires together: STT → Intent → Router → LLM/Tools → Streaming → TTS
Manages conversation state, persona, and emotional intelligence.
"""

import time

from logger import get_logger

log = get_logger("BRAIN")


class PihuBrain:
    """Central orchestrator — Pihu's brain.
    
    Connects all modules:
    STT → Intent Classifier → Router → [LLM/Tools] → Streaming Pipeline → TTS
    
    Also manages:
    - Conversation state (working memory)
    - Persona injection (Hinglish, personality)
    - Emotional intelligence (tone adaptation)
    - Tool announcements
    """

    def __init__(self, backend_mode: bool = False, user_id: str = "pihu_user"):
        from config import PERSONA

        self.persona = PERSONA
        self.backend_mode = backend_mode
        self.user_id = user_id
        self.scheduler = None
        self.stt = None
        self.tts = None
        self.mic = None
        self.player = None
        self.memory = None
        self.advanced_core = None
        self.intent_classifier = None
        self.router = None
        self.pipeline = None

        # State
        self._is_running = False
        self._interaction_count = 0

        log.info("🧠 PihuBrain created | Persona: %s | Backend Mode: %s", self.persona["name"], self.backend_mode)

    def initialize(self):
        """Initialize all modules in correct order."""
        from scheduler import ComputeScheduler
        from memory_engine import MemoryEngine
        from intent_classifier import IntentClassifier
        from llm.llama_cpp_llm import LlamaCppLLM
        from llm.cloud_llm import CloudLLM
        from llm.groq_llm import GroqLLM
        from tools.web_search import WebSearch
        from router import Router
        from streaming_pipeline import StreamingPipeline
        from hardware_profiler import system_profiler

        log.info("🚀 Initializing all modules...")
        t0 = time.time()
        
        # 0. Hardware Profiler Assessment
        hardware_profile = system_profiler.evaluate()
        system_profiler.print_splash_screen()

        # 1. Scheduler (must be first — others depend on it)
        self.scheduler = ComputeScheduler()

        # 2. Audio I/O (Skip in Backend SaaS Mode)
        if not self.backend_mode:
            try:
                from audio_io import MicrophoneStream, AudioPlayer

                self.mic = MicrophoneStream()
                self.player = AudioPlayer()
            except BaseException as e:
                log.warning("Audio hardware failed to initialize: %s. Continuing in degraded mode.", e)

            # 3. STT (preload)
            from stt_engine import STTEngine

            self.stt = STTEngine(scheduler=self.scheduler)
            self.stt.load()

            # 4. TTS (preload)
            from tts_engine import TTSEngine

            self.tts = TTSEngine()
            self.tts.load()
        else:
            log.info("☁️ Backend mode: skipping desktop audio, STT, and TTS initialization")

        # 5. Intent Classifier
        self.intent_classifier = IntentClassifier()

        from llm.local_llm import LocalLLM
        from llm.vllm_engine import VllmEngine
        
        # 7. LLMs (BYOM Provider Setup)
        vllm = VllmEngine(scheduler=self.scheduler)
        vllm_health = vllm.health_check()
        vllm_available = vllm_health.get("available", False)
        
        ollama_llm = LocalLLM(scheduler=self.scheduler)
        ollama_health = ollama_llm.health_check()
        ollama_model_found = ollama_health.get("available", False)
        
        native_llm = LlamaCppLLM(scheduler=self.scheduler)
        native_llm.health_check()

        # Prioritize vLLM first, then Ollama, then native CPU fallback
        if vllm_available:
            active_local = vllm
            log.info("🔥 Using vLLM High-Performance Engine: %s", vllm_health.get("model_name"))
        elif ollama_model_found:
            active_local = ollama_llm
            log.info("✅ Using Ollama LLM: %s", ollama_health.get("model_name"))
        else:
            active_local = native_llm
            log.info("⚠️ vLLM/Ollama models not found — falling back to native CPU Phi-3.5 (llama-cpp)")

        # 7.5 Apply Hardware Profiles to active local model
        active_local.max_tokens = hardware_profile.max_context
        if hasattr(active_local, "primary_model"):
            active_local.primary_model = hardware_profile.recommended_model
            active_local._current_model = hardware_profile.recommended_model
            log.info("⚙️ Hardware Profiler: Bound Local LLM context to %s and model to %s", 
                     active_local.max_tokens, active_local.primary_model)

        cloud_llm = CloudLLM()
        cloud_llm.health_check()
        groq_llm = GroqLLM()
        groq_llm.health_check()
        
        # 8. Memory (Requires LLM for Background Compaction)
        self.memory = MemoryEngine(user_id=self.user_id, backend_mode=self.backend_mode, llm_client=active_local)

        # 8.1 Advanced power-feature core (local deterministic control plane)
        from advanced_features import PihuAdvancedCore
        from config import BASE_DIR
        self.advanced_core = PihuAdvancedCore(workspace=str(BASE_DIR), user_id=self.user_id)

        # 8. Tools
        web_search = WebSearch()
        voice_os = None
        
        if self.backend_mode:
            # === SAAS MODE ===
            vision = None
            grounding = None
            automation = None
            swarm = None
            mcp = None
            openclaw = None
        else:
            # === NATIVE DESKTOP MODE ===
            from tools.vision import VisionTool
            from tools.vision_grounding import VisionGrounding
            from tools.automation import AutomationTool
            from tools.pencil_swarm_agent import PencilSwarmAgent
            from tools.mcp_dispatcher import MCPDispatcher
            from tools.composio_bridge import ComposioBridge

            if "VisionAnalysis" in hardware_profile.capabilities_disabled:
                log.warning("⚙️ Hardware Profiler: Disabling VisionTool (RAM/VRAM limits)")
                vision = None
                grounding = None
            else:
                vision = VisionTool(scheduler=self.scheduler)
                grounding = VisionGrounding(cloud_llm=cloud_llm)
                
            automation = AutomationTool(llm_client=cloud_llm, grounding_tool=grounding)

            from tools.voice_os_control import VoiceOSController
            voice_os = VoiceOSController(automation=automation)
            
            if "HeavySwarmConcurrency" in hardware_profile.capabilities_disabled:
                log.warning("⚙️ Hardware Profiler: Disabling SwarmAgent (RAM/VRAM limits)")
                swarm = None
            else:
                swarm = PencilSwarmAgent(automation_tool=automation, vision_grounding=grounding, groq_llm=groq_llm)
                
            mcp = MCPDispatcher()
            
            # 8.4 Composio Toolset Integration
            composio = ComposioBridge(cloud_llm=cloud_llm)

            # 8.5 OpenClaw Orchestrator
            from openclaw_bridge import OpenClawBridge
            openclaw = OpenClawBridge(swarm_agent=swarm, automation=automation, groq_llm=groq_llm)

        # 8.7 Capability Negotiation
        from capability_negotiator import CapabilityNegotiator
        negotiator = CapabilityNegotiator(hardware_profile=hardware_profile)
        if hasattr(active_local, "primary_model"):
            negotiator.evaluate_model(active_local.primary_model, llm_client=active_local)
        else:
            negotiator.evaluate_model("unknown", llm_client=active_local)

        # 9. Router (Stateful or Deterministic)
        from config import LANGGRAPH_ENABLED
        if LANGGRAPH_ENABLED:
            from graph_router import GraphRouter
            tools_dict = {
                "vision": vision,
                "automation": automation,
                "voice_os": voice_os if not self.backend_mode else None,
                "mcp": mcp if not self.backend_mode else None,
                "composio": composio if not self.backend_mode else None,
                "advanced_core": self.advanced_core,
                "swarm": swarm,
                "openclaw": openclaw,
                "groq": groq_llm,
            }
            self.router = GraphRouter(
                local_llm=active_local,
                cloud_llm=cloud_llm,
                intent_classifier=self.intent_classifier,
                memory=self.memory,
                tools_dict=tools_dict
            )
            log.info("🔀 Router: Stateful LangGraph Engine Active")
        else:
            self.router = Router(
                capability_negotiator=negotiator,
                local_llm=active_local,
                cloud_llm=cloud_llm,
                groq_llm=groq_llm,
                memory=self.memory,
                scheduler=self.scheduler,
                web_search=web_search,
                vision=vision,
                automation=automation,
                voice_os=voice_os,
                mcp=mcp,
                composio=composio if not self.backend_mode else None,
                swarm=swarm,
                openclaw=openclaw,
                backend_mode=self.backend_mode,
                advanced_core=self.advanced_core,
                user_id=self.user_id,
            )
            log.info("🔀 Router: Deterministic Legacy Engine Active")

        # 10. Streaming Pipeline
        if not self.backend_mode:
            self.pipeline = StreamingPipeline(
                tts_engine=self.tts,
                audio_player=self.player,
            )
            
            # 10.5 Async Pipecat Voice Loop (Optional Next-Gen Voice)
            from config import PIPECAT_ENABLED
            if PIPECAT_ENABLED:
                from tools.pipecat_pipeline import PipecatEngine
                self.pipecat_engine = PipecatEngine(
                    tts_engine=self.tts,
                    stt_engine=self.stt,
                    cloud_llm=cloud_llm
                )
                self.pipecat_engine.start_background()

        elapsed = time.time() - t0
        log.info("✅ All modules initialized in %.1fs", elapsed)

    def run(self):
        """Main loop: listen → process → respond → repeat.

        NEVER terminates on its own. Individual cycle failures are caught
        and logged, and the loop continues.
        """
        from config import (
            MAX_CONSECUTIVE_ERRORS,
            ERROR_COOLDOWN_SECONDS,
            ERROR_RETRY_DELAY,
        )

        self._is_running = True
        consecutive_errors = 0

        log.info("=" * 50)
        log.info("   🎤 Pihu is ready! Bolo kuch...")
        log.info("=" * 50)

        # Start microphone
        try:
            if self.mic:
                self.mic.start()
            else:
                log.error("Microphone not initialized — switching to text mode")
                self.run_text_mode()
                return
        except Exception as e:
            log.error("Microphone start failed: %s — switching to text mode", e)
            self.run_text_mode()
            return

        try:
            while self._is_running:
                try:
                    self._listen_and_respond()
                    consecutive_errors = 0 # Reset on success
                except KeyboardInterrupt:
                    raise # Let the outer handler deal with it
                except (IOError, OSError, RuntimeError) as e:
                    # Specific hardware/IO errors
                    consecutive_errors += 1
                    log.error(
                        "⚠️ Listen/respond IO/hardware cycle failed (error %d/%d): %s",
                        consecutive_errors, MAX_CONSECUTIVE_ERRORS, e,
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        log.warning(
                            "Too many consecutive IO errors — cooling down %ds", ERROR_COOLDOWN_SECONDS
                        )
                        import time
                        time.sleep(ERROR_COOLDOWN_SECONDS)
                        consecutive_errors = 0
                    else:
                        import time
                        time.sleep(ERROR_RETRY_DELAY) # Brief pause before retry
                except (ValueError, TypeError, AttributeError) as e:
                    # Specific logic/data errors
                    consecutive_errors += 1
                    log.error(
                        "⚠️ Listen/respond logic cycle failed (error %d/%d): %s",
                        consecutive_errors, MAX_CONSECUTIVE_ERRORS, e,
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        log.warning(
                            "Too many consecutive logic errors — cooling down %ds", ERROR_COOLDOWN_SECONDS
                        )
                        import time
                        time.sleep(ERROR_COOLDOWN_SECONDS)
                        consecutive_errors = 0
                    else:
                        import time
                        time.sleep(ERROR_RETRY_DELAY) # Brief pause before retry
                except Exception as e:
                    # Catch-all for truly unexpected errors
                    consecutive_errors += 1
                    log.exception(
                        "⚠️ Unexpected listen/respond cycle failed (error %d/%d): %s",
                        consecutive_errors, MAX_CONSECUTIVE_ERRORS, e,
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        log.warning(
                            "Too many consecutive unexpected errors — cooling down %ds", ERROR_COOLDOWN_SECONDS
                        )
                        import time
                        time.sleep(ERROR_COOLDOWN_SECONDS)
                        consecutive_errors = 0
                    else:
                        import time
                        time.sleep(ERROR_RETRY_DELAY) # Brief pause before retry
        except KeyboardInterrupt:
            log.info("Keyboard interrupt — shutting down")
        finally:
            self.shutdown()

    def run_text_mode(self):
        """Text-only mode (no microphone, keyboard input).
        
        NEVER terminates on its own. User saying 'quit' just restarts the prompt.
        Only Ctrl+C (handled by main_forever) can stop the agent.
        """
        self._is_running = True
        consecutive_errors = 0

        print("\n" + "=" * 50)
        print("   🧠 Pihu — Text Mode")
        print("   Type your message (Ctrl+C to pause)")
        print("=" * 50 + "\n")

        try:
            while self._is_running:
                try:
                    user_input = input("👤 You: ").strip()
                except EOFError:
                    # stdin closed — wait and retry
                    log.warning("stdin EOF — waiting 5s before retry")
                    import time
                    time.sleep(5)
                    continue

                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit", "bye", "band karo"):
                    print("\n🤖 Pihu: Bye bye! Take care 💜")
                    print("🤖 Pihu: (Main, wapas aa rahi hoon... I never quit 😎)\n")
                    import time
                    time.sleep(1)
                    continue  # Don't break — keep the loop alive

                try:
                    # Inplace thinking status
                    print("\r🤖 Pihu: Thinking...", end="", flush=True)
                    self._process_text(user_input)
                    consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    log.error("Processing error #%d: %s", consecutive_errors, e)
                    print(f"\n🤖 Pihu: Oops, error aa gaya but main hoon na! ({e})\n")
                    if consecutive_errors >= 10:
                        import time
                        time.sleep(5)
                        consecutive_errors = 0

        except KeyboardInterrupt:
            print("\n\n🤖 Pihu: Acha chalo, phir milte hain! 👋")
        finally:
            self.shutdown()

    def _listen_and_respond(self):
        """Single listen-process-respond cycle."""
        # 1. Listen for utterance
        log.info("👂 Listening...")

        try:
            audio = self.mic.listen_for_utterance(max_duration_s=15)
        except Exception as e:
            log.error("Mic capture error: %s", e)
            return

        if audio is None or len(audio) < 1600:  # Skip very short audio
            return

        # 2. Interrupt any current playback
        if self.player:
            try:
                self.player.interrupt()
            except Exception as e:
                log.error("Player interrupt error: %s", e)

        # 3. STT
        try:
            text = self.stt.transcribe(audio)
        except Exception as e:
            log.error("STT transcription error: %s", e)
            return

        if not text or len(text.strip()) < 2:
            return

        # 4. Process text
        self._process_text(text)

    def _process_text(self, text: str):
        """Process user text: classify → route → respond.
        
        Every step is individually guarded so a single failure
        never kills the interaction loop.
        """
        self._interaction_count += 1

        # Store in memory (safe)
        try:
            if self.memory:
                if hasattr(self.memory, "update_memory_async"):
                    self.memory.update_memory_async(f"User: {text}")
                if hasattr(self.memory, "update_dialogue"):
                    self.memory.update_dialogue("user", text)
        except Exception as e:
            log.error("Memory store failed: %s", e)

        # Check system degradation periodically
        try:
            if self._interaction_count % 5 == 0 and self.scheduler:
                self.scheduler.check_degradation()
        except Exception as e:
            log.error("Degradation check failed: %s", e)

        # 1. Classify intent
        try:
            if self.intent_classifier:
                intent = self.intent_classifier.classify(text)
            else:
                # Degraded mode: treat everything as chat
                from intent_classifier import Intent
                intent = Intent(type="chat", confidence=0.5, metadata={}, raw_input=text)
        except Exception as e:
            log.error("Intent classification failed: %s — defaulting to chat", e)
            from intent_classifier import Intent
            intent = Intent(type="chat", confidence=0.5, metadata={}, raw_input=text)

        # 2. Route to pipeline
        try:
            if self.router:
                route_result = self.router.route(intent)
                
                # Startup Resiliency: If first message and it failed, retry once after a short wait
                if (route_result is None or route_result.response is None) and self._interaction_count <= 1:
                    log.info("🕒 Startup lag detected — Retrying routing in 3s...")
                    import time
                    time.sleep(3)
                    route_result = self.router.route(intent)
            else:
                # Degraded mode: just echo
                route_result = None
        except Exception as e:
            log.error("Routing failed: %s", e)
            route_result = None

        # 3. Stream response
        try:
            if route_result is not None and route_result.response is not None:
                if self.pipeline and self.tts and self.tts.is_loaded:
                    full_response = self.pipeline.stream_response(
                        token_generator=route_result.response,
                        tool_announcement=route_result.tool_announcement,
                    )
                elif self.pipeline:
                    full_response = self.pipeline.stream_text_only(
                        token_generator=route_result.response,
                        tool_announcement=route_result.tool_announcement,
                    )
                else:
                    # No pipeline — consume generator manually
                    tokens = []
                    print("\r" + " " * 100 + "\r🤖 Pihu: ", end="", flush=True)
                    for token in route_result.response:
                        print(token, end="", flush=True)
                        tokens.append(token)
                    print()
                    full_response = "".join(tokens)
            else:
                full_response = "Hmm, kuch samajh nahi aaya. Please phir se bolo?"
                print(f"\r🤖 Pihu: {full_response}")

            # Store response in memory
            try:
                if self.memory:
                    if hasattr(self.memory, "update_memory_async"):
                        self.memory.update_memory_async(f"Assistant: {full_response}")
                    if hasattr(self.memory, "update_dialogue"):
                        self.memory.update_dialogue("assistant", full_response)
            except Exception as e:
                log.error("Memory store (response) failed: %s", e)

        except Exception as e:
            log.error("Response processing failed: %s", e)
            print(f"\n🤖 Pihu: Oops, kuch gadbad ho gayi: {str(e)}")

    def shutdown(self):
        """Graceful shutdown."""
        log.info("🔌 Shutting down Pihu...")
        self._is_running = False

        for name, module, method in [
            ("mic", self.mic, "stop"),
            ("pipeline", self.pipeline, "stop"),
            ("player", self.player, "stop"),
        ]:
            if module:
                try:
                    getattr(module, method)()
                except Exception as e:
                    log.error("Error shutting down %s: %s", name, e)

        log.info("👋 Pihu shut down gracefully")
