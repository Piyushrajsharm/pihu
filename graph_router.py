"""
Pihu — Stateful Agent Router (LangGraph)
Replaces the deterministic if/else `router.py` with a robust, cyclic Graph.
Supports loops, reflection, and human-in-the-loop workflows.
"""

import re
from typing import Any, TypedDict
from logger import get_logger

log = get_logger("GRAPH")

# 1. Define the State
class PihuState(TypedDict):
    input_text: str
    intent: object
    context: list[str]
    tool_calls: list[dict]
    tool_results: list[str]
    final_response: str
    pipeline: str

class GraphRouter:
    """A stateful router using LangGraph to manage complex Pihu agent execution."""

    COMPOSIO_KEYWORDS = ("github", "slack", "calendar", "notion", "email", "gmail", "composio")
    
    def __init__(self, local_llm, cloud_llm, intent_classifier, memory, tools_dict):
        self.local_llm = local_llm
        self.cloud_llm = cloud_llm
        self.intent_classifier = intent_classifier
        self.memory = memory
        self.tools = tools_dict  # e.g., {"vision": VisionTool, "automation": AutomationTool, "composio": ComposioBridge}
        self.app = None
        self._is_available = False
        from security.adult_content_policy import AdultContentPolicy
        self.adult_content_policy = AdultContentPolicy.from_config()
        
        try:
            from langgraph.graph import StateGraph, END
            
            # 2. Build the Graph
            workflow = StateGraph(PihuState)
            
            # Define Nodes
            workflow.add_node("classify_intent", self.node_classify_intent)
            workflow.add_node("retrieve_memory", self.node_retrieve_memory)
            workflow.add_node("execute_tools", self.node_execute_tools)
            workflow.add_node("generate_response", self.node_generate_response)
            
            # Define Edges
            workflow.set_entry_point("classify_intent")
            workflow.add_edge("classify_intent", "retrieve_memory")
            
            # Conditional routing based on intent
            workflow.add_conditional_edges(
                "retrieve_memory",
                self.route_based_on_intent,
                {
                    "tools": "execute_tools",
                    "generate": "generate_response"
                }
            )
            
            workflow.add_edge("execute_tools", "generate_response")
            workflow.add_edge("generate_response", END)
            
            self.app = workflow.compile()
            self._is_available = True
            log.info("✅ LangGraph Stateful Router initialized successfully.")
            
        except ImportError:
            log.warning("LangGraph not installed. Run 'pip install langgraph langchain-core'")
        except Exception as e:
            log.error("Failed to compile LangGraph router: %s", e)

    @property
    def is_available(self) -> bool:
        return self._is_available

    def node_classify_intent(self, state: PihuState) -> dict:
        """Classify the user intent."""
        log.info("Graph: Classifying Intent...")
        existing_intent = self._normalize_intent_type(state.get("intent"))
        if existing_intent:
            return {"intent": existing_intent}

        input_text = state["input_text"]
        
        if self.intent_classifier:
            result = self.intent_classifier.classify(input_text)
            intent = self._normalize_intent_type(result) or "chat"
        else:
            intent = "chat"
            
        return {"intent": intent}

    def node_retrieve_memory(self, state: PihuState) -> dict:
        """Fetch memory context."""
        log.info("Graph: Retrieving Memory Context...")
        if self.memory:
            try:
                context = self.memory.retrieve(state["input_text"])
                # Extract text chunks from Qdrant models
                if context and isinstance(context, list):
                    clean_ctx = [c.text if hasattr(c, 'text') else str(c) for c in context]
                else:
                    clean_ctx = []
                return {"context": clean_ctx}
            except Exception as e:
                log.warning("Graph: Memory retrieval failed: %s", e)
        return {"context": []}

    def route_based_on_intent(self, state: PihuState) -> str:
        """Conditional Edge logic."""
        intent = self._normalize_intent_type(state.get("intent"))

        if intent in ["system_command", "vision_analysis", "ui_generation", "prediction"]:
            return "tools"
            
        # Safety net: If misclassified as chat, but contains obvious SaaS/tool triggers.
        if self._looks_like_composio_request(state.get("input_text", "")):
            log.info("Graph: Overriding intent based on keyword triggers -> routing to tools")
            return "tools"

        advanced_core = self.tools.get("advanced_core")
        if advanced_core and advanced_core.can_handle(state.get("input_text", "")):
            return "tools"
            
        return "generate"

    def node_execute_tools(self, state: PihuState) -> dict:
        """Execute selected tools based on intent."""
        log.info("Graph: Executing Tools...")
        intent = self._normalize_intent_type(state.get("intent"))
        results = []
        pipeline_used = "tools"
        input_text = state["input_text"]
        
        composio = self.tools.get("composio")
        advanced_core = self.tools.get("advanced_core")
        if advanced_core and advanced_core.can_handle(input_text):
            pipeline_used = "advanced_core"
            results.append(str(advanced_core.handle_command(input_text)))

        elif self._tool_available(composio) and self._looks_like_composio_request(input_text):
            pipeline_used = "composio"
            results.append(self._consume_tool_output(composio.execute(input_text)))
            
        elif intent == "vision_analysis":
            vision = self.tools.get("vision")
            if self._tool_available(vision) and hasattr(vision, "analyze_screen"):
                pipeline_used = "vision"
                results.append(str(vision.analyze_screen(input_text)))

        elif intent == "ui_generation":
            mcp = self.tools.get("mcp")
            if self._tool_available(mcp) and hasattr(mcp, "dispatch"):
                pipeline_used = "mcp"
                results.append(str(mcp.dispatch({"task": input_text})))

        elif intent == "prediction":
            pipeline_used = "prediction"
            try:
                mirofish = self.tools.get("mirofish")
                if mirofish is None:
                    from tools.mirofish_simulator import MiroFishSimulator
                    mirofish = MiroFishSimulator()
                if hasattr(mirofish, "predict_stream"):
                    results.append(self._consume_tool_output(mirofish.predict_stream(input_text)))
                else:
                    results.append(str(mirofish.predict(input_text)))
            except Exception as e:
                log.warning("Graph: MiroFish prediction failed: %s", e)

        elif intent == "system_command":
            voice_os = self.tools.get("voice_os")
            if self._tool_available(voice_os) and hasattr(voice_os, "can_handle") and voice_os.can_handle(input_text):
                pipeline_used = "voice_os"
                result = voice_os.execute(input_text)
                results.append(getattr(result, "message", str(result)))
            else:
                openclaw = self.tools.get("openclaw")
                automation = self.tools.get("automation")
                if self._tool_available(openclaw) and hasattr(openclaw, "execute"):
                    pipeline_used = "system"
                    results.append(str(openclaw.execute(input_text)))
                elif self._tool_available(automation) and hasattr(automation, "execute_natural"):
                    pipeline_used = "system"
                    results.append(str(automation.execute_natural(input_text)))
        
        if not results:
            results.append("No specific tool handled this request. Deferring to standard generation.")
            
        return {"tool_results": results, "pipeline": pipeline_used}

    def node_generate_response(self, state: PihuState) -> dict:
        """Final LLM synthesis."""
        log.info("Graph: Generating Final Response...")
        
        prompt = state["input_text"]
        if state.get("tool_results"):
            prompt += "\n\nTool Execution Context:\n" + "\n".join(state["tool_results"])
            
        llm = self.cloud_llm if self.cloud_llm and self.cloud_llm.is_available else self.local_llm
        if not llm:
            if state.get("tool_results"):
                return {"final_response": "\n".join(state["tool_results"])}
            return {"final_response": "Piyush, LLM engines down hain."}

        response = self._generate_text(llm, prompt, state.get("context", []))
        if not response and state.get("tool_results"):
            response = "\n".join(state["tool_results"])
        
        return {"final_response": str(response)}

    def execute(self, user_input: str, intent: Any = None):
        """Run the graph. Returns a dict representing the final state."""
        if not self._is_available:
            return {"final_response": "LangGraph is not available."}

        metadata = getattr(intent, "metadata", {}) if intent is not None else {}
        adult_decision = self.adult_content_policy.evaluate(user_input, metadata)
        if adult_decision.blocked:
            return {
                "input_text": user_input,
                "intent": self._normalize_intent_type(intent) or "chat",
                "context": [],
                "tool_calls": [],
                "tool_results": [],
                "final_response": adult_decision.response or "I can't help with that request.",
                "pipeline": "local_llm",
                "adult_content_reason": adult_decision.reason,
            }
        if adult_decision.force_local:
            prompt = f"{user_input}\n\n[{adult_decision.directive}]"
            context = []
            if self.memory:
                try:
                    retrieved = self.memory.retrieve(user_input)
                    context = [item.text if hasattr(item, "text") else str(item) for item in retrieved or []]
                except Exception as e:
                    log.warning("Graph: adult-mode memory retrieval failed: %s", e)
            response = self._generate_text(self.local_llm, prompt, context)
            return {
                "input_text": user_input,
                "intent": "chat",
                "context": context,
                "tool_calls": [],
                "tool_results": [],
                "final_response": response or "Piyush, local LLM unavailable hai.",
                "pipeline": "local_llm",
                "adult_content_reason": adult_decision.reason,
            }
            
        initial_state = PihuState(
            input_text=user_input,
            intent=self._normalize_intent_type(intent),
            context=[],
            tool_calls=[],
            tool_results=[],
            final_response="",
            pipeline="langgraph"
        )
        
        final_state = self.app.invoke(initial_state)
        return final_state

    def route(self, intent):
        """Compatibility shim for PihuBrain/API callers that expect Router.route()."""
        from router import RouteResult

        if not self._is_available:
            return RouteResult(
                pipeline="langgraph",
                response=iter(["LangGraph is not available."]),
                tool_announcement="",
                fallback_used=True,
            )

        advanced_core = self.tools.get("advanced_core")
        if advanced_core and advanced_core.can_handle(intent.raw_input):
            return RouteResult(
                pipeline="advanced_core",
                response=iter([str(advanced_core.handle_command(intent.raw_input))]),
                tool_announcement="",
                metadata={"advanced": True},
            )

        final_state = self.execute(intent.raw_input, intent=intent)
        response = final_state.get("final_response") or "No response generated."
        return RouteResult(
            pipeline=final_state.get("pipeline", "langgraph"),
            response=iter([str(response)]),
            tool_announcement="",
            metadata={"graph_state": final_state},
        )

    def _normalize_intent_type(self, raw_intent: Any) -> str:
        """Normalize Intent dataclasses, enums, and legacy stringified intents."""
        if raw_intent is None:
            return ""
        if hasattr(raw_intent, "type"):
            return str(getattr(raw_intent, "type", "")).strip().lower()
        if hasattr(raw_intent, "name"):
            return str(getattr(raw_intent, "name", "")).strip().lower()

        text = str(raw_intent).strip()
        match = re.search(r"type=['\"]([^'\"]+)['\"]", text)
        if match:
            return match.group(1).lower()
        return text.lower()

    def _looks_like_composio_request(self, text: str) -> bool:
        input_low = str(text or "").lower()
        return any(keyword in input_low for keyword in self.COMPOSIO_KEYWORDS)

    def _tool_available(self, tool: Any) -> bool:
        if tool is None:
            return False
        available = getattr(tool, "is_available", True)
        return bool(available() if callable(available) else available)

    def _consume_tool_output(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if hasattr(value, "__iter__"):
            return "".join(str(chunk) for chunk in value if chunk is not None)
        return str(value)

    def _generate_text(self, llm: Any, prompt: str, context: list[str]) -> str:
        if hasattr(llm, "generate_batch"):
            response = llm.generate_batch(prompt=prompt, context=context)
        else:
            response = llm.generate(prompt=prompt, context=context, stream=False)

        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if hasattr(response, "__iter__"):
            return "".join(str(chunk) for chunk in response if chunk is not None)
        return str(response)
