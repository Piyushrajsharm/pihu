"""
Pihu — Composio Bridge
Connects Pihu to Composio's vast ecosystem of tools (GitHub, Notion, Slack, etc.)
"""
import os
from typing import Any, Generator
from logger import get_logger

log = get_logger("COMPOSIO")

class ComposioBridge:
    DEFAULT_TOOLKITS = ["github", "gmail", "notion"]
    TOOLKIT_KEYWORDS = {
        "github": "github",
        "slack": "slack",
        "notion": "notion",
        "calendar": "googlecalendar",
        "gmail": "gmail",
        "email": "gmail",
    }

    def __init__(self, cloud_llm=None, user_id: str = "pihu_user"):
        """Initialize the Composio Bridge. Requires an LLM capable of function calling."""
        self.cloud_llm = cloud_llm
        self.user_id = user_id
        self._is_available = False
        self._backend = ""
        self._unavailable_reason = ""
        self.composio = None
        self.provider = None
        self.toolset = None
        
        try:
            from openai import OpenAI
            import config

            composio_api_key = (
                getattr(config, "COMPOSIO_API_KEY", "")
                or os.getenv("COMPOSIO_API_KEY", "")
            )
            llm_api_key = (
                getattr(config, "NVIDIA_NIM_API_KEY", "")
                or os.getenv("NVIDIA_NIM_API_KEY", "")
                or os.getenv("OPENAI_API_KEY", "")
            )

            if not composio_api_key:
                self._unavailable_reason = "COMPOSIO_API_KEY is not configured."
                log.warning("Composio Bridge unavailable: %s", self._unavailable_reason)
                return
            if not llm_api_key:
                self._unavailable_reason = "NVIDIA_NIM_API_KEY or OPENAI_API_KEY is not configured."
                log.warning("Composio Bridge unavailable: %s", self._unavailable_reason)
                return

            # Use NVIDIA NIM or OpenAI via the OpenAI SDK wrapper for Composio
            self.openai_client = OpenAI(
                api_key=llm_api_key,
                base_url=getattr(config, "NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
            )
            self.model_name = getattr(config, "CLOUD_LLM_MODEL", "meta/llama-3.1-70b-instruct")

            # Current Composio SDK (composio>=0.12): Composio + OpenAIProvider.
            try:
                from composio import Composio
                from composio_openai import OpenAIProvider

                self.provider = OpenAIProvider()
                self.composio = Composio(
                    provider=self.provider,
                    api_key=composio_api_key,
                )
                self._backend = "modern"
            except ImportError:
                # Legacy fallback for older Composio installs.
                from composio.tools.toolset import ComposioToolSet

                self.toolset = ComposioToolSet(api_key=composio_api_key)
                self._backend = "legacy"

            self._is_available = True
            log.info("✅ Composio Bridge initialized successfully (%s SDK).", self._backend)
            
        except ImportError as e:
            log.warning("Composio SDK not installed or missing dependency: %s", e)
        except Exception as e:
            self._unavailable_reason = str(e)
            log.error("Failed to initialize Composio Bridge: %s", e)

    @property
    def is_available(self) -> bool:
        return self._is_available

    def execute(self, prompt: str, app_names: list[str] = None) -> Generator[str, None, None]:
        """Execute a natural language request using Composio tools.
        
        Args:
            prompt: The user's request
            app_names: Specific apps to restrict tools to (e.g., ["GITHUB", "NOTION"])
        """
        if not self._is_available:
            detail = f" ({self._unavailable_reason})" if self._unavailable_reason else ""
            yield f"Composio is not available{detail}"
            return

        yield "🛠️ Activating Composio tools...\n"
        
        try:
            toolkits = self._select_toolkits(prompt, app_names)
            tools = self._get_tools(toolkits)
            if not tools:
                yield "No Composio tools were returned for this request."
                return

            yield "🧠 Brainstorming action plan...\n"
            
            # Using the standard OpenAI client format expected by composio-openai
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                tools=tools,
                messages=[
                    {"role": "system", "content": "You are Pihu, an expert assistant. Use the provided tools to accomplish the user's task. Return the exact function calls needed."},
                    {"role": "user", "content": prompt}
                ]
            )

            if not self._has_tool_calls(response):
                content = self._message_content(response)
                if content:
                    yield content
                else:
                    yield "Composio did not produce a tool call for this request."
                return
            
            # Process function calls using Composio's handler
            result = self._handle_tool_calls(response)
            
            # Generate the final conversational summary
            yield "📊 Compiling results...\n"
            
            final_response = self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are Pihu. Summarize the tool execution results naturally in Hinglish."},
                    {"role": "user", "content": f"Task: {prompt}\n\nTool Results: {result}"}
                ],
                stream=True
            )
            
            for chunk in final_response:
                content = self._chunk_content(chunk)
                if content is not None:
                    yield content

        except Exception as e:
            log.error("Composio execution failed: %s", e)
            yield f"\n❌ Sorry, Composio execution fail ho gaya: {e}"

    def _select_toolkits(self, prompt: str, app_names: list[str] = None) -> list[str]:
        if app_names:
            return [self.TOOLKIT_KEYWORDS.get(name.lower(), name.lower()) for name in app_names]

        prompt_low = prompt.lower()
        selected = [
            toolkit
            for keyword, toolkit in self.TOOLKIT_KEYWORDS.items()
            if keyword in prompt_low
        ]
        return selected or list(self.DEFAULT_TOOLKITS)

    def _get_tools(self, toolkits: list[str]) -> list[dict]:
        if self._backend == "modern":
            return self.composio.tools.get(
                user_id=self.user_id,
                toolkits=toolkits,
                limit=20,
            )

        apps = []
        from composio.client.enums import App
        for toolkit in toolkits:
            enum_name = toolkit.upper()
            if enum_name == "GOOGLECALENDAR":
                enum_name = "GOOGLECALENDAR"
            try:
                apps.append(getattr(App, enum_name))
            except AttributeError:
                log.warning("Unknown legacy Composio App requested: %s", toolkit)
        return self.toolset.get_tools(apps=apps)

    def _handle_tool_calls(self, response: Any) -> Any:
        if self._backend == "modern":
            return self.provider.handle_tool_calls(
                user_id=self.user_id,
                response=response,
            )
        return self.toolset.handle_tool_calls(response)

    def _has_tool_calls(self, response: Any) -> bool:
        choices = getattr(response, "choices", None) or []
        for choice in choices:
            message = getattr(choice, "message", None)
            if getattr(message, "tool_calls", None):
                return True
        return False

    def _message_content(self, response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        return str(getattr(message, "content", "") or "")

    def _chunk_content(self, chunk: Any) -> str | None:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return None
        delta = getattr(choices[0], "delta", None)
        return getattr(delta, "content", None)
