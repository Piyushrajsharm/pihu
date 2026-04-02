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

    def __init__(self):
        from config import PERSONA

        self.persona = PERSONA
        self.scheduler = None
        self.stt = None
        self.tts = None
        self.mic = None
        self.player = None
        self.memory = None
        self.intent_classifier = None
        self.router = None
        self.pipeline = None

        # State
        self._is_running = False
        self._interaction_count = 0

        log.info("🧠 PihuBrain created | Persona: %s", self.persona["name"])

    def initialize(self):
        """Initialize all modules in correct order."""
        from scheduler import ComputeScheduler
        from stt_engine import STTEngine
        from tts_engine import TTSEngine
        from audio_io import MicrophoneStream, AudioPlayer
        from memory_engine import MemoryEngine
        from intent_classifier import IntentClassifier
        from llm.llama_cpp_llm import LlamaCppLLM
        from llm.cloud_llm import CloudLLM
        from tools.web_search import WebSearch
        from tools.vision import VisionTool
        from tools.vision_grounding import VisionGrounding
        from tools.automation import AutomationTool
        from tools.pencil_swarm_agent import PencilSwarmAgent
        from tools.mcp_dispatcher import MCPDispatcher
        from router import Router
        from streaming_pipeline import StreamingPipeline

        log.info("🚀 Initializing all modules...")
        t0 = time.time()

        # 1. Scheduler (must be first — others depend on it)
        self.scheduler = ComputeScheduler()

        # 2. Audio I/O
        self.mic = MicrophoneStream()
        self.player = AudioPlayer()

        # 3. STT (preload)
        self.stt = STTEngine(scheduler=self.scheduler)
        self.stt.load()

        # 4. TTS (preload)
        self.tts = TTSEngine()
        self.tts.load()

        # 5. Memory
        self.memory = MemoryEngine()

        # 6. Intent Classifier
        self.intent_classifier = IntentClassifier()

        # 7. LLMs (Native Direct Loading — No Ollama)
        local_llm = LlamaCppLLM(scheduler=self.scheduler)
        cloud_llm = CloudLLM()

        # Check native model status
        local_llm.check_models()

        # 8. Tools
        web_search = WebSearch()
        vision = VisionTool(scheduler=self.scheduler)
        grounding = VisionGrounding(cloud_llm=cloud_llm)
        automation = AutomationTool(llm_client=cloud_llm, grounding_tool=grounding)
        swarm = PencilSwarmAgent(automation_tool=automation, vision_grounding=grounding, groq_llm=None)
        mcp = MCPDispatcher()

        # 8.5 OpenClaw Orchestrator
        from openclaw_bridge import OpenClawBridge
        openclaw = OpenClawBridge(swarm_agent=swarm, automation=automation, groq_llm=None)

        # 9. Router (Primary Engine is now LocalLLM)
        self.router = Router(
            local_llm=local_llm,
            cloud_llm=cloud_llm,
            groq_llm=None,
            memory=self.memory,
            scheduler=self.scheduler,
            web_search=web_search,
            vision=vision,
            automation=automation,
            mcp=mcp,
            swarm=swarm,
            openclaw=openclaw,
        )

        # 10. Streaming Pipeline
        self.pipeline = StreamingPipeline(
            tts_engine=self.tts,
            audio_player=self.player,
        )

        elapsed = time.time() - t0
        log.info("✅ All modules initialized in %.1fs", elapsed)

    def run(self):
        """Main loop: listen → process → respond → repeat.
        
        NEVER terminates on its own. Individual cycle failures are caught
        and logged, and the loop continues.
        """
        self._is_running = True
        consecutive_errors = 0
        MAX_CONSECUTIVE_ERRORS = 20

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
                    consecutive_errors = 0  # Reset on success
                except KeyboardInterrupt:
                    raise  # Let the outer handler deal with it
                except Exception as e:
                    consecutive_errors += 1
                    log.error(
                        "⚠️ Listen/respond cycle failed (error %d/%d): %s",
                        consecutive_errors, MAX_CONSECUTIVE_ERRORS, e,
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        log.warning(
                            "Too many consecutive errors — cooling down 10s"
                        )
                        import time
                        time.sleep(10)
                        consecutive_errors = 0
                    else:
                        import time
                        time.sleep(0.5)  # Brief pause before retry
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
            else:
                # Degraded mode: just echo
                route_result = None
        except Exception as e:
            log.error("Routing failed: %s", e)
            route_result = None

        # 3. Stream response
        try:
            if route_result is not None and route_result.response is not None:
                if self.pipeline:
                    full_response = self.pipeline.stream_text_only(
                        token_generator=route_result.response,
                        tool_announcement=route_result.tool_announcement,
                    )
                else:
                    # No pipeline — consume generator manually
                    tokens = []
                    print("\n🤖 Pihu: ", end="", flush=True)
                    for token in route_result.response:
                        print(token, end="", flush=True)
                        tokens.append(token)
                    print()
                    full_response = "".join(tokens)
            else:
                full_response = "Hmm, kuch samajh nahi aaya. Please phir se bolo?"
                print(f"\n🤖 Pihu: {full_response}")

            # Store response in memory
            try:
                if self.memory:
                    if hasattr(self.memory, "update_memory_async"):
                        self.memory.update_memory_async(f"Assistant: {full_response}")
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
