"""
Pihu — Deterministic Routing Engine
Routes classified intents to the correct execution pipeline.
NO guesswork. NO hallucinations.
"""

import asyncio
from dataclasses import dataclass, field
import os
import sys
from pathlib import Path
from typing import Optional, Generator, Any

from logger import get_logger
from intent_classifier import Intent

log = get_logger("ROUTER")


@dataclass
class RouteResult:
    """Result of routing decision."""

    pipeline: str          # "local_llm", "cloud_llm", "web_search", "vision", "mcp", "system"
    response: Any          # Generator, string, or None
    tool_announcement: str  # What to tell user ("Searching web…")
    metadata: dict = field(default_factory=dict)
    fallback_used: bool = False


class Router:
    """Deterministic routing engine.
    
    Routing Rules (NO GUESSWORK):
    ┌────────────────────┬─────────────────────────┐
    │ Condition          │ Action                  │
    ├────────────────────┼─────────────────────────┤
    │ Time-sensitive     │ Web Search FIRST        │
    │ Complex reasoning  │ Cloud LLM               │
    │ Normal chat        │ Local LLM               │
    │ UI request         │ MCP Tool                │
    │ "Look / Screen"   │ Vision pipeline          │
    │ System command     │ Local execution          │
    └────────────────────┴─────────────────────────┘
    
    Anti-Hallucination: if confidence < threshold → force tool usage.
    """

    def __init__(
        self,
        local_llm,
        cloud_llm,
        groq_llm=None,
        memory=None,
        scheduler=None,
        web_search=None,
        vision=None,
        automation=None,
        mcp=None,
        swarm=None,
        openclaw=None,
    ):
        self.local_llm = local_llm
        self.cloud_llm = cloud_llm
        self.groq_llm = groq_llm
        self.memory = memory
        self.scheduler = scheduler
        self.web_search = web_search
        self.vision = vision
        self.automation = automation
        self.mcp = mcp
        self.swarm = swarm
        self.openclaw = openclaw

        from config import INTENT_CONFIDENCE_THRESHOLD, PERSONA
        self.confidence_threshold = INTENT_CONFIDENCE_THRESHOLD
        self.system_prompt = PERSONA["system_prompt"]

        log.info("Router initialized | Groq=%s, OpenClaw=%s",
                 "✅" if groq_llm and groq_llm.is_available else "❌",
                 "✅" if openclaw else "❌")
                 
        from telemetry_logger import TelemetryCore
        self.telemetry = TelemetryCore()
        
        from interpreter_engine import InterpreterEngine
        self.interpreter_engine = InterpreterEngine()
        
        from ocr_engine import OCREngine
        self.ocr_engine = OCREngine()
        
        from planner_engine import PlannerEngine
        self.planner_engine = PlannerEngine(project_dir=str(Path(__file__).parent / "third_party" / "taskweaver" / "project"))
        
        from context_rag_engine import ContextRAGEngine
        self.rag_engine = ContextRAGEngine()

    def route(self, intent: Intent) -> RouteResult:
        """Route an intent to the correct pipeline.
        
        Args:
            intent: Classified intent from IntentClassifier

        Returns:
            RouteResult with pipeline, response, and announcement
        """
        log.info("Routing intent: %s (%.0f%%)", intent.type, intent.confidence * 100)
        input_lower = intent.raw_input.lower().strip()

        # 0. Weekly Review Bypass
        if "weekly review" in input_lower or "evaluate your week" in input_lower:
            summary = self.telemetry.get_weekly_summary()
            log.info("Triggered Weekly Review")
            prompt_injection = f"{intent.raw_input}\n\n[SYSTEM DIRECTIVE: Perform a Weekly Review. Here is your raw telemetry:\n{summary}\nAnalyse your failure records brutally. Be humble, admit where you wasted the user's time or entirely misunderstood context. Keep it short.]"
            intent.raw_input = prompt_injection
            # Let it fall through to chat routing so she naturally reads the data

        # 0.5 Goal setting override
        if any(g in input_lower for g in ["mera goal hai", "set goal", "target hai"]):
            goal_text = intent.raw_input
            for phrase in ["mera goal hai", "set goal", "target hai", "ki", ":"]:
                goal_text = goal_text.lower().replace(phrase, "").strip()
            if self.memory and goal_text:
                self.memory.set_active_goal(goal_text)
                return RouteResult(
                    pipeline="system",
                    response=iter([f"Done babu, ab maine active goal track karna shuru kar diya: '{goal_text}'. Ab bhatakne nahi dungi tumko."]),
                    tool_announcement=""
                )

        # 1. Clear goal block
        if input_lower in ["clear goal", "goal clear", "goal achieved", "target pura ho gaya"]:
            if self.memory:
                self.memory.clear_active_goal()
                if self.memory.task_state.active: self.memory.task_state.close()
                return RouteResult(
                    pipeline="system",
                    response=iter(["Acha theek hai, purana goal clear kar diya maine. Congrats. Next kya?"]),
                    tool_announcement=""
                )
                
        # 1.5 Task State Toggles (Failure / Success)
        if self.memory:
            fail_triggers = ["nahi hua", "kaam nahi", "fail", "error", "phat gaya", "nahi chal"]
            if self.memory.task_state.active and any(f in input_lower for f in fail_triggers):
                self.memory.task_state.mark_failure()
                
                # Infinite Loop Break Test
                if len(self.memory.task_state.failures) >= 3:
                    self.telemetry.log_event("SURRENDER", self.memory.task_state.issue)
                    self.memory.task_state.close()
                    log.error("TaskState hit Infinite Loop. Forcing AI Surrender.")
                    return RouteResult(
                        pipeline="system",
                        response=iter(["yaar maine 3 alag tareeqe try kar liye, kuch kaam nahi kar raha. mera dimag kharab ho gaya hai ab, khud hi theek karlo isko please. mera guess fail ho raha hai baar baar."]),
                        tool_announcement=""
                    )
                
            success_triggers = ["ho gaya", "solve", "fixed", "chal gaya", "thank"]
            if self.memory.task_state.active and any(s in input_lower for s in success_triggers):
                self.telemetry.log_event("SUCCESS", self.memory.task_state.issue)
                self.memory.task_state.close()
                
            problem_triggers = ["fix karo", "isko theek", "problem hai"]
            if not self.memory.task_state.active and any(p in input_lower for p in problem_triggers):
                self.memory.task_state.reset(intent.raw_input)

        # 1.6 Context Miss Triggers
        context_misses = ["galat samajh", "yeh nahi pucha", "wrong", "kya bol rahi hai", "meri baat sun", "not this", "context miss"]
        if any(c in input_lower for c in context_misses):
            self.telemetry.log_event("CONTEXT_MISS", intent.raw_input)

        # 2. Smart Initiative Intercept (Pattern Automation)
        if self.memory:
            self.memory.record_action(intent.raw_input)
            pattern = self.memory.check_automation_opportunity()
            if pattern:
                self.telemetry.log_event("MACRO_PROPOSED", pattern)
                self.memory.action_history.clear() # Prevent spam loop
                log.info("Smart Initiative Triggered: '%s'", pattern)
                return RouteResult(
                    pipeline="system",
                    response=iter([f"ruko. tum har baar '{pattern}' kar rahe ho manually... pagal ho kya? main isko forever automate kar dun script se?"]),
                    tool_announcement=""
                )

        # 3. Proactive Vague Intent Intercept
        vague_triggers = ["fat gaya", "error aa", "chal nahi raha", "kaam nahi", "broken", "kese theek"]
        if any(v in input_lower for v in vague_triggers) and len(intent.raw_input.split()) <= 6:
            # Check if pointing word active context triggered
            self._build_context_prompt(intent) 
            if "USER CLIPBOARD CONTENTS" not in getattr(self, "_last_context", ""):
                log.warning("Intercepted Vague Intent. Forcing user to provide data.")
                return RouteResult(
                    pipeline="local_llm", 
                    response=iter(["kahan phata? code chipkao pehle ya error copy karke toh do, guess thodi karungi main hawa mein..."]),
                    tool_announcement=""
                )

        # 4. Anti-hallucination: low confidence → force tool
        if intent.confidence < self.confidence_threshold and intent.type == "chat":
            log.warning(
                "Low confidence (%.0f%%) on chat → forcing web search",
                intent.confidence * 100,
            )
            return self._route_realtime_query(intent)

        # 4. Deterministic routing
        route_map = {
            "realtime_query": self._route_realtime_query,
            "deep_reasoning": self._route_deep_reasoning,
            "chat": self._route_chat,
            "vision_analysis": self._route_vision,
            "ui_generation": self._route_ui_generation,
            "system_command": self._route_system_command,
        }

        handler = route_map.get(intent.type, self._route_chat)
        result = handler(intent)
        
        # 5. Stateful Tracking & Extraction Wrapper
        if self.memory and hasattr(result.response, "__iter__") and not isinstance(result.response, str):
            result.response = self._wrap_for_memory(result.response, intent.raw_input)
            
        return result

    def _wrap_for_memory(self, generator, raw_input):
        """Silently caches the complete LLM response stream without blocking TTFT."""
        full_text = ""
        for chunk in generator:
            full_text += str(chunk)
            yield chunk
            
        if self.memory:
            if getattr(self.memory, "task_state", None) and self.memory.task_state.active:
                self.memory.task_state.last_assistant_reply = full_text.strip()
            # LLM generation is completely done. GPU is free.
            # Trigger Mem0 background LLM extraction (0 latency cost to user)
            if hasattr(self.memory, "update_memory_async"):
                self.memory.update_memory_async(raw_input)
            
    # ──────────────────────────────────────────
    # Context Builder
    # ──────────────────────────────────────────
    def _build_context_prompt(self, intent: Intent) -> str:
        """Injects ambient OS context and deliberate clipboard boundaries."""
        context = []
        
        # 1. Window state
        if self.automation and hasattr(self.automation, "window_manager"):
            try:
                active_win = self.automation.window_manager.get_active_window()
                if active_win:
                    context.append(f"Active UI Window: '{active_win}'")
            except Exception as e:
                import pywintypes
                if isinstance(e, pywintypes.error):
                    log.warning("Window context unreadable (COM/RPC error ignored)")
                else:
                    log.debug("Active window logic failed silently: %s", e)
        # 2. Context Builder (Epistemic Logic -> Clipboard -> Screenshot OCRFallback)
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            clipboard_data = win32clipboard.GetClipboardData().strip()
            win32clipboard.CloseClipboard()
            if clipboard_data and len(clipboard_data) > 5:
                # Max Intent Priority: Explicit copying
                truncated = clipboard_data[-1000:] if len(clipboard_data) > 1000 else clipboard_data
                context.append(f"[EXACT CLIPBOARD HIGHLIGHT]\n{truncated}")
                
                if self.memory and getattr(self.memory, "task_state", None) and self.memory.task_state.active:
                    self.memory.task_state.add_clipboard(truncated)
            else:
                raise ValueError("Empty clipboard triggered OCR Context fallback")

        except Exception as e:
            # Fallback to OCR Context Ripping if they point epistemic intent ("isko", "idhar")
            import pywintypes
            if isinstance(e, pywintypes.error):
                log.warning("Clipboard locked by OS. Falling back to OCR context.")
            import win32clipboard
            try: win32clipboard.CloseClipboard()
            except Exception: pass
            
            epistemic_pointers = ["isko", "yeh", "here", "this error", "screen", "dekho", "look", "what is this"]
            if any(p in intent.raw_input.lower() for p in epistemic_pointers):
                if hasattr(self, "ocr_engine") and getattr(self.ocr_engine, "is_available", False):
                    # Zero clipboard? Take a screenshot and rip the text natively in 150ms!
                    screen_text = self.ocr_engine.get_screen_text(max_length=3000)
                    if screen_text:
                        context.append(f"[docTR PYTORCH ACTIVE SCREEN OCR]\n{screen_text}")
                        if self.memory and getattr(self.memory, "task_state", None) and self.memory.task_state.active:
                            self.memory.task_state.add_clipboard(screen_text[-500:])
                
        # 3. Vector Semantic Memory (Mem0) & Soft Goal Anchors
        if self.memory:
            # Sub-15ms Forward Retrieval
            mem_context = getattr(self.memory, "get_context_for_query", lambda x: "")(intent.raw_input)
            if mem_context: 
                context.append(f"[LONG-TERM MEMORY (Vectorized): {mem_context}]")
            
            # Goal tracker injection (Soft Tether)
            active_goal = getattr(self.memory, "get_active_goal", lambda: "")()
            if active_goal:
                context.append(f"[USER'S CURRENT MISSION: {active_goal}. Allow them to explore tangents freely. Only lightly tether the conversation back if they ask 'what's next?']")

            # Active Task State injection
            if hasattr(self.memory, "task_state") and self.memory.task_state.active:
                ts_context = self.memory.task_state.get_context()
                if ts_context: context.append(f"[TASK STATE LAYER: {ts_context}]")

        if context:
            ctx_str = " | ".join(context)
            
            # 4. Phase 6 Enhancement: Semantic Context Filtering (RAG)
            if len(ctx_str) > 500 and hasattr(self, "rag_engine") and self.rag_engine.is_available:
                log.info("🧩 Triggering RAG Cognitive Filter...")
                ctx_str = self.rag_engine.filter_context(intent.raw_input, ctx_str)

            self._last_context = ctx_str
            
            # Use a more restrictive wrapper to keep Pihu from "explaining" the system state
            return (
                f"### INTERNAL_BACKGROUND_KNOWLEDGE (DO NOT MENTION TO USER):\n"
                f"{ctx_str}\n"
                f"### END_BACKGROUND_KNOWLEDGE\n\n"
                f"USER INPUT: {intent.raw_input}"
            )
        
        self._last_context = ""
        return intent.raw_input

    # ──────────────────────────────────────────
    # Route Handlers
    # ──────────────────────────────────────────

    def _route_chat(self, intent: Intent) -> RouteResult:
        """Chat routing: Groq (fastest) → Cloud → Local fallback."""

        # ─── GROQ FAST PATH (ALL chat goes here first) ───
        if self.groq_llm and self.groq_llm.is_available:
            log.info("⚡ GROQ PATH: ultra-fast inference")
            try:
                is_short = len(intent.raw_input.strip()) < 30
                max_tok = 80 if is_short else 150
                prompt_with_context = self._build_context_prompt(intent)
                response = self.groq_llm.generate(
                    prompt=prompt_with_context,
                    system_prompt=self.system_prompt,
                    stream=True,
                    max_tokens_override=max_tok,
                )
                if response:
                    return RouteResult(
                        pipeline="groq",
                        response=response,
                        tool_announcement="",
                    )
            except Exception as e:
                log.error("Groq failed: %s — falling back", e)

        # ─── LOCAL FALLBACK ───
        log.warning("Falling back to local LLM for chat")
        prompt_with_context = self._build_context_prompt(intent)

        # Use turbo model for short messages (much faster on CPU)
        is_short = len(intent.raw_input.strip()) < 30
        from config import LOCAL_LLM_TURBO, LOCAL_LLM_TURBO_MAX_TOKENS
        model_override = LOCAL_LLM_TURBO if is_short else None
        max_tok = LOCAL_LLM_TURBO_MAX_TOKENS if is_short else 100

        response = self.local_llm.generate(
            prompt=prompt_with_context,
            system_prompt=self.system_prompt,
            stream=True,
            model_override=model_override,
            max_tokens_override=max_tok,
        )

        return RouteResult(
            pipeline="local_llm",
            response=response,
            tool_announcement="",
            fallback_used=True,
        )

    def _route_realtime_query(self, intent: Intent) -> RouteResult:
        """Time-sensitive → Web Search FIRST, then LLM summarization."""
        announcement = "🔍 Search kar rahi hoon..."

        search_results = []
        if self.web_search:
            try:
                query = intent.metadata.get("search_query", intent.raw_input)
                search_results = self.web_search.search(query)
            except Exception as e:
                log.error("Web search failed: %s", e)

        if search_results:
            # Summarize search results with LLM
            results_text = "\n".join(
                f"- {r.get('title', '')}: {r.get('snippet', '')}"
                for r in search_results[:5]
            )
            prompt = f"""Based on these search results, answer the user's question concisely.

Search Results:
{results_text}

User Question: {intent.raw_input}

Answer in Hinglish naturally. Be factual — use only the search results."""

            response = self.local_llm.generate(
                prompt=prompt,
                system_prompt=self.system_prompt,
                stream=True,
            )

            return RouteResult(
                pipeline="web_search",
                response=response,
                tool_announcement=announcement,
                metadata={"search_results": search_results},
            )
        else:
            # Fallback: LLM without search
            log.warning("Web search returned no results, using LLM directly")
            return self._route_chat(intent)

    def _route_deep_reasoning(self, intent: Intent) -> RouteResult:
        """Complex reasoning → Cloud LLM with local fallback."""
        announcement = "🧠 Deep analysis kar rahi hoon..."

        if self.cloud_llm and self.cloud_llm.is_available:
            try:
                # Try cloud LLM (streaming)
                response = self.cloud_llm.generate(
                    prompt=intent.raw_input,
                    system_prompt=self.system_prompt,
                    stream=True,
                )

                if response:
                    return RouteResult(
                        pipeline="cloud_llm",
                        response=response,
                        tool_announcement=announcement,
                    )
            except Exception as e:
                log.error("Cloud LLM failed: %s", e)

        # Fallback to local LLM
        log.info("Cloud LLM unavailable/timed out, using local LLM")
        response = self.local_llm.generate(
            prompt=intent.raw_input,
            system_prompt=self.system_prompt,
            stream=True,
        )

        return RouteResult(
            pipeline="local_llm",
            response=response,
            tool_announcement=announcement,
            fallback_used=True,
        )

    def _route_vision(self, intent: Intent) -> RouteResult:
        """Vision → Screen capture + Vision model."""
        announcement = "👁️ Screen dekh rahi hoon..."

        if self.vision:
            try:
                vision_mode = intent.metadata.get("vision_mode", "screen")
                if vision_mode == "screen":
                    description = self.vision.analyze_screen(intent.raw_input)
                else:
                    description = self.vision.analyze_screen(intent.raw_input)

                if description:
                    return RouteResult(
                        pipeline="vision",
                        response=iter([description]),
                        tool_announcement=announcement,
                        metadata={"vision_result": description},
                    )
            except Exception as e:
                log.error("Vision pipeline failed: %s", e)

        # Fallback: tell user vision is unavailable
        fallback_msg = "Vision module available nahi hai abhi. Text me bata do kya chahiye?"
        return RouteResult(
            pipeline="local_llm",
            response=iter([fallback_msg]),
            tool_announcement="",
            fallback_used=True,
        )

    def _route_ui_generation(self, intent: Intent) -> RouteResult:
        """UI generation → MCP dispatcher."""
        announcement = "🎨 UI generate kar rahi hoon..."

        if self.mcp:
            try:
                result = self.mcp.dispatch({"task": intent.raw_input})
                return RouteResult(
                    pipeline="mcp",
                    response=iter([str(result)]),
                    tool_announcement=announcement,
                )
            except Exception as e:
                log.error("MCP dispatch failed: %s", e)

        # Fallback: generate code with LLM
        prompt = f"""Generate a clean, modern UI based on this request:
{intent.raw_input}

Provide the HTML/CSS/JS code."""

        response = self.local_llm.generate(
            prompt=prompt,
            system_prompt=self.system_prompt,
            stream=True,
        )

        return RouteResult(
            pipeline="local_llm",
            response=response,
            tool_announcement=announcement,
            fallback_used=True,
        )

    def _route_system_command(self, intent: Intent) -> RouteResult:
        """System command → TaskWeaver Planner → OpenInterpreter Execution."""
        announcement = "🧠 Planning and executing..."

        # 1. Complexity Shield (Architectural Hierarchy)
        input_low = intent.raw_input.lower()
        complex_triggers = ["and then", "first", "next", "after that", "analyze", "sequence", "fix and"]
        is_multi_step = any(t in input_low for t in complex_triggers)
        
        def synergistic_execution_stream():
            # A. TaskWeaver Planning Node
            if is_multi_step and hasattr(self, "planner_engine") and self.planner_engine.is_available:
                log.info("📐 Triggering TaskWeaver Planner for complex request")
                yield from self.planner_engine.plan_task(intent.raw_input)
                yield "\n--- Planning Complete. Executing steps... ---\n"
            
            # B. OpenInterpreter Execution Node (Phase 2 Hand-off)
            if hasattr(self, "interpreter_engine") and self.interpreter_engine.is_available:
                log.info("🔧 Routing to OpenInterpreter Sandbox")
                yield from self.interpreter_engine.execute_stream(intent.raw_input)
            else:
                yield "Execution engine (OpenInterpreter) missing. Action halted."

        if hasattr(self, "interpreter_engine") and self.interpreter_engine.is_available:
            return RouteResult(
                pipeline="hybrid_planner",
                response=synergistic_execution_stream(),
                tool_announcement="",
            )

        # Fallback: legacy automation (via OpenClaw)
        if self.openclaw:
            log.info("🛡️ Routing to OpenClaw Secured Orchestrator")
            return RouteResult(
                pipeline="system",
                response=iter([self.openclaw.execute(intent.raw_input)]),
                tool_announcement=announcement,
            )

        if self.automation:
            log.info("⚙️ Routing to Direct Automation Tool")
            return RouteResult(
                pipeline="system",
                response=iter([self.automation.execute_natural(intent.raw_input)]),
                tool_announcement=announcement,
            )

        return RouteResult(
            pipeline="local_llm",
            response=iter(["Arre Piyush, system engines available nahi hain. Ek baar installer check karlo please."]),
            tool_announcement="",
            fallback_used=True,
        )
