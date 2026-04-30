"""
Pihu — Intent Classifier
Deterministic intent classification for every input.
Hybrid: keyword matching (fast path) + LLM classification (fallback).
"""

import re
from dataclasses import dataclass
from typing import Optional

from logger import get_logger

log = get_logger("INTENT")


@dataclass
class Intent:
    """Classified intent with confidence and metadata."""

    type: str           # One of INTENT_TYPES
    confidence: float   # 0.0 — 1.0
    metadata: dict      # Extra info (e.g. search query, command)
    raw_input: str      # Original text


class IntentClassifier:
    """Deterministic intent classification.
    
    Every input MUST be classified into one of:
    - chat: Normal conversation
    - realtime_query: Time-sensitive, needs web search
    - deep_reasoning: Complex analysis, needs cloud LLM
    - vision_analysis: Screen/image analysis
    - ui_generation: UI creation via MCP
    - system_command: Local system execution
    - prediction: MiroFish swarm intelligence predictions
    
    Approach: Keyword patterns first (fast), LLM fallback if ambiguous.
    """

    # ──────────────────────────────────────────
    # Keyword Patterns (HIGH PRIORITY — fast path)
    # ──────────────────────────────────────────

    REALTIME_PATTERNS = [
        # English
        r"\b(search|latest|news|current|today|weather|price|stock)\b",
        r"\b(what is happening|trending|update|score)\b",
        r"\b(google|search for|look up|find out)\b",
        # Hindi / Hinglish
        r"\b(khoj|dhundh|taza|latest news)\b",
        r"\b(market|price kya)\b",
    ]

    VISION_PATTERNS = [
        r"\b(look|screen|see|dekh|dikhao|show me|analyze screen)\b",
        r"\b(screenshot|what.s on.*screen|screen pe kya)\b",
        r"\b(image|photo|picture|tasveer)\b",
        r"\b(screen.*dekh|dekho.*screen|yeh kya hai)\b",
    ]

    DEEP_REASONING_PATTERNS = [
        r"\b(explain|analyze|compare|evaluate|why does|how does)\b",
        r"\b(in detail|step by step|deep dive|samjhao)\b",
        r"\b(solve|calculate|derive|prove|research)\b",
        r"\b(write.*code|code.*likh|implement|algorithm)\b",
        r"\b(essay|article|report|analysis)\b",
    ]

    UI_GENERATION_PATTERNS = [
        r"\b(create.*ui|build.*interface|design.*page)\b",
        r"\b(generate.*ui|make.*website|bana.*page)\b",
        r"\b(ui.*bana|interface.*design|layout.*create)\b",
        r"\b(html|webpage|dashboard.*create)\b",
        r"\b(build.*dashboard|dashboard.*build|build.*website|create.*dashboard)\b",
    ]

    SYSTEM_COMMAND_PATTERNS = [
        r"\b(open|close|run|execute|launch|start|stop)\s+(?:the\s+)?(?:app|program|terminal|cmd|powershell|chrome|browser|notepad|calculator|vlc|spotify|server|service|script|file|folder|process|whatsapp|excel|powerbi|power bi|downloads|documents|desktop|settings|task manager)\b",
        r"^\s*(?:hey\s+)?pihu[:,\s]+(?:open|launch|start|run|kholo|khol|chalao|type|write|likho|press|hit|click|scroll|focus|switch to|close|google|youtube|search|move|drag|maximize|minimize|snap|copy|paste)\b",
        r"^\s*(?:open|launch|start|run|kholo|khol|chalao|show|go to)\s+(?:youtube|google|gmail|github|chatgpt|settings|paint|camera|photos|file explorer|vs code|vscode|downloads|documents|desktop|project|workspace|task manager)\b",
        r"\b(copy|paste|select all|save|undo|redo|new tab|close tab|task manager|show desktop|voice typing|dictation|address bar|clipboard)\b",
        r"\b(scroll up|scroll down|volume up|volume down|mute|focus|switch to|maximize|minimize|snap left|snap right|right click|double click|move mouse|drag)\b",
        r"^\s*(?:run command|execute command|shell command|terminal command|powershell command|cmd command)\b",
        r"\b(shutdown|restart|volume|brightness)\b",
        r"\b(khol|kholo|band kar|chala|chalao|terminal|cmd)\b",
        r"\b(install|uninstall|delete file|create folder)\b",
        r"\b(type|likh|likho|click|press|key|mouse)\b",
    ]

    PREDICTION_PATTERNS = [
        r"\b(predict|forecast|prediction|bhavishya)\b",
        r"\b(mirofish|swarm.*predict|swarm.*analy)\b",
        r"\b(market.*analysis|trend.*forecast)\b",
        r"\b(what will happen|kya hoga|future.*trend)\b",
        r"\b(bull|bear|sentiment.*analy|risk.*assess)\b",
    ]

    def __init__(self):
        from config import INTENT_CONFIDENCE_THRESHOLD
        self.confidence_threshold = INTENT_CONFIDENCE_THRESHOLD

        # Compile patterns
        self._patterns = {
            "realtime_query": [re.compile(p, re.IGNORECASE) for p in self.REALTIME_PATTERNS],
            "vision_analysis": [re.compile(p, re.IGNORECASE) for p in self.VISION_PATTERNS],
            "deep_reasoning": [re.compile(p, re.IGNORECASE) for p in self.DEEP_REASONING_PATTERNS],
            "ui_generation": [re.compile(p, re.IGNORECASE) for p in self.UI_GENERATION_PATTERNS],
            "system_command": [re.compile(p, re.IGNORECASE) for p in self.SYSTEM_COMMAND_PATTERNS],
            "prediction": [re.compile(p, re.IGNORECASE) for p in self.PREDICTION_PATTERNS],
        }

        log.info("IntentClassifier initialized | %d pattern groups", len(self._patterns))

    def classify(self, text: str) -> Intent:
        """Classify input text into an intent.
        
        Args:
            text: User input text

        Returns:
            Intent with type, confidence, and metadata
        """
        if not text or not text.strip():
            return Intent(
                type="chat",
                confidence=1.0,
                metadata={},
                raw_input=text,
            )

        text_clean = text.strip()

        # Step 1: Keyword pattern matching (fast path)
        scores = self._score_patterns(text_clean)

        if scores:
            best_type = max(scores, key=scores.get)
            best_score = scores[best_type]

            # High confidence match
            if best_score >= self.confidence_threshold:
                intent = Intent(
                    type=best_type,
                    confidence=best_score,
                    metadata=self._extract_metadata(best_type, text_clean),
                    raw_input=text_clean,
                )
                log.info(
                    "🎯 Intent: %s (%.0f%%) | '%s'",
                    intent.type, intent.confidence * 100, text_clean[:50],
                )
                return intent

        # Step 2: Fallback (Fast Path) for ambiguous intents
        # We NO LONGER call the slow Cloud LLM for intent classification.
        # This achieves 0ms latency. If it's ambiguous, it's just a chat.
        best_score = max(scores.values()) if scores else 0
        if best_score > 0:
            log.info("Ambiguous intent detected (score %.2f) — defaulting to local chat", best_score)

        # Step 3: Default to chat
        intent = Intent(
            type="chat",
            confidence=0.8,
            metadata={},
            raw_input=text_clean,
        )
        log.info(
            "🎯 Intent: chat (default, 80%%) | '%s'",
            text_clean[:50],
        )
        return intent



    def _score_patterns(self, text: str) -> dict[str, float]:
        """Score text against all pattern groups."""
        scores = {}

        for intent_type, patterns in self._patterns.items():
            match_count = sum(
                1 for p in patterns if p.search(text)
            )
            if match_count > 0:
                if intent_type == "system_command":
                    scores[intent_type] = min(0.72 + (match_count - 1) * 0.14, 1.0)
                    continue
                # Score = matches / total patterns, capped at 1.0
                scores[intent_type] = min(match_count / max(len(patterns) * 0.3, 1), 1.0)

        return scores

    def _extract_metadata(self, intent_type: str, text: str) -> dict:
        """Extract relevant metadata based on intent type."""
        metadata = {}

        if intent_type == "realtime_query":
            # Extract the search query
            metadata["search_query"] = text

        elif intent_type == "system_command":
            # Try to extract the command
            metadata["command_text"] = text

        elif intent_type == "vision_analysis":
            metadata["vision_mode"] = "screen" if "screen" in text.lower() else "general"

        return metadata
