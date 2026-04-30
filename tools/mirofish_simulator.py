"""
Pihu — MiroFish Swarm Intelligence Engine
Multi-agent prediction system using swarm-inspired consensus.

Each "fish" agent analyzes the query from a unique perspective:
  - ResearchFish: Factual analysis and trend identification
  - AnalystFish: Statistical patterns and quantitative reasoning  
  - ContrarianFish: Devil's advocate, identifies risks and counterarguments
  - SentinelFish: Risk assessment and safety analysis

No external data required — agents reason using LLM intelligence.
For enhanced predictions, provide optional context data.
"""

import time
import random
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Generator
from logger import get_logger

log = get_logger("MIROFISH")


# ──────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────

@dataclass
class FishAgent:
    """A single prediction agent in the swarm."""
    name: str
    role: str
    emoji: str
    system_prompt: str
    confidence: float = 0.0
    analysis: str = ""
    vote: str = ""  # "bullish", "bearish", "neutral"


@dataclass
class SwarmPrediction:
    """Aggregated prediction from all fish agents."""
    query: str
    consensus: str
    confidence: float
    agents: List[FishAgent]
    reasoning: str
    elapsed_s: float
    scenario: str = "neutral"


# ──────────────────────────────────────────
# Fish Agent Definitions
# ──────────────────────────────────────────

FISH_AGENTS = [
    FishAgent(
        name="ResearchFish",
        role="research",
        emoji="🔬",
        system_prompt="""You are ResearchFish — a factual research analyst.
Your job is to analyze the query using known facts, trends, and historical patterns.
Focus on: What does the data say? What are the established trends?
Be concise (3-4 lines max). End with a vote: BULLISH, BEARISH, or NEUTRAL.
Format: [ANALYSIS] your analysis [VOTE] your_vote [CONFIDENCE] 0-100"""
    ),
    FishAgent(
        name="AnalystFish",
        role="analyst",
        emoji="📊",
        system_prompt="""You are AnalystFish — a quantitative pattern analyst.
Your job is to identify statistical patterns, cycles, and anomalies.
Focus on: What patterns exist? What do the numbers suggest?
Be concise (3-4 lines max). End with a vote: BULLISH, BEARISH, or NEUTRAL.
Format: [ANALYSIS] your analysis [VOTE] your_vote [CONFIDENCE] 0-100"""
    ),
    FishAgent(
        name="ContrarianFish",
        role="contrarian",
        emoji="🔥",
        system_prompt="""You are ContrarianFish — a devil's advocate analyst.
Your job is to challenge the mainstream view and identify what everyone is missing.
Focus on: What could go wrong? What are people ignoring?
Be concise (3-4 lines max). End with a vote: BULLISH, BEARISH, or NEUTRAL.
Format: [ANALYSIS] your analysis [VOTE] your_vote [CONFIDENCE] 0-100"""
    ),
    FishAgent(
        name="SentinelFish",
        role="sentinel",
        emoji="🛡️",
        system_prompt="""You are SentinelFish — a risk and safety sentinel.
Your job is to evaluate downside risk, tail events, and safety concerns.
Focus on: What's the worst case? How likely is catastrophic failure?
Be concise (3-4 lines max). End with a vote: BULLISH, BEARISH, or NEUTRAL.
Format: [ANALYSIS] your analysis [VOTE] your_vote [CONFIDENCE] 0-100"""
    ),
]


class MiroFishSimulator:
    """Multi-agent swarm prediction engine.

    Spawns N fish agents that analyze the same query from different
    perspectives, then aggregates their votes into a consensus prediction.
    No external data files required — pure LLM reasoning.
    """

    def __init__(self):
        self.agents = [FishAgent(**{k: v for k, v in a.__dict__.items()}) for a in FISH_AGENTS]
        self.prediction_history = []
        log.info("🐟 MiroFish Swarm Engine initialized (%d agents)", len(self.agents))

    def predict(self, query: str, data_context: str = "", scenario: str = "neutral") -> str:
        """Generate a swarm consensus prediction.

        Args:
            query: What to predict or analyze
            data_context: Optional additional context (not required)
            scenario: "bullish", "bearish", "neutral", or "shock"

        Returns:
            Formatted prediction string
        """
        log.info("🐟 Swarm prediction initiated: '%s' (scenario=%s)", query[:60], scenario)
        t0 = time.time()

        # Run all agents
        for agent in self.agents:
            self._run_agent(agent, query, data_context, scenario)

        # Aggregate results
        prediction = self._aggregate(query, scenario, time.time() - t0)

        # Cache result
        self.prediction_history.append(prediction)
        if len(self.prediction_history) > 20:
            self.prediction_history = self.prediction_history[-20:]

        return self._format_output(prediction)

    def predict_stream(self, query: str, data_context: str = "", scenario: str = "neutral") -> Generator[str, None, None]:
        """Stream prediction results as they come in — for real-time UI."""
        t0 = time.time()

        yield "🐟 MiroFish Swarm Intelligence Engine\n"
        yield f"📋 Query: {query}\n"
        yield f"🎯 Scenario: {scenario.upper()}\n"
        yield "─" * 40 + "\n\n"

        # Run agents one by one, streaming each result
        for i, agent in enumerate(self.agents):
            yield f"{agent.emoji} {agent.name} is analyzing...\n"
            self._run_agent(agent, query, data_context, scenario)
            yield f"{agent.emoji} {agent.name}: {agent.analysis[:120]}\n"
            yield f"   Vote: {agent.vote.upper()} | Confidence: {agent.confidence}%\n\n"

        # Aggregate
        prediction = self._aggregate(query, scenario, time.time() - t0)

        yield "─" * 40 + "\n"
        yield f"🏆 CONSENSUS: {prediction.consensus.upper()}\n"
        yield f"📊 Swarm Confidence: {prediction.confidence:.0f}%\n"
        yield f"💡 {prediction.reasoning}\n"
        yield f"⚡ Completed in {prediction.elapsed_s:.1f}s\n"

    def _run_agent(self, agent: FishAgent, query: str, data_context: str, scenario: str):
        """Run a single fish agent's analysis."""
        prompt = self._build_agent_prompt(agent, query, data_context, scenario)

        # Try LLM-powered analysis
        try:
            response = self._query_llm(prompt)
            if response:
                self._parse_agent_response(agent, response)
                return
        except Exception as e:
            log.warning("Agent %s LLM failed: %s — using heuristic", agent.name, e)

        # Fallback: heuristic-based analysis
        self._heuristic_analysis(agent, query, scenario)

    def _build_agent_prompt(self, agent: FishAgent, query: str, data_context: str, scenario: str) -> str:
        """Build the prompt for a fish agent."""
        prompt = f"{agent.system_prompt}\n\n"
        prompt += f"PREDICTION QUERY: {query}\n"
        prompt += f"SCENARIO ASSUMPTION: {scenario}\n"

        if data_context:
            prompt += f"\nADDITIONAL CONTEXT:\n{data_context}\n"

        prompt += "\nProvide your analysis now."
        return prompt

    def _query_llm(self, prompt: str) -> Optional[str]:
        """Try to get LLM response — cloud first, then local."""
        # Try Cloud LLM
        try:
            from llm.cloud_llm import CloudLLM
            cloud = CloudLLM()
            if cloud.is_available:
                response = cloud.generate(prompt=prompt, stream=False, max_tokens_override=200)
                if response:
                    # Consume generator if needed
                    if hasattr(response, "__iter__") and not isinstance(response, str):
                        return "".join(str(c) for c in response)
                    return str(response)
        except Exception as e:
            log.debug("Cloud LLM unavailable for MiroFish: %s", e)

        # Try Local LLM
        try:
            from llm.llama_cpp_llm import LlamaCppLLM
            local = LlamaCppLLM()
            response = local.generate(prompt=prompt, stream=False, max_tokens_override=200)
            if response:
                if hasattr(response, "__iter__") and not isinstance(response, str):
                    return "".join(str(c) for c in response)
                return str(response)
        except Exception as e:
            log.debug("Local LLM unavailable for MiroFish: %s", e)

        return None

    def _parse_agent_response(self, agent: FishAgent, response: str):
        """Parse structured agent response into fields."""
        response_lower = response.lower()

        # Extract analysis
        if "[analysis]" in response_lower:
            parts = response_lower.split("[analysis]")
            if len(parts) > 1:
                analysis_part = parts[1]
                if "[vote]" in analysis_part:
                    agent.analysis = analysis_part.split("[vote]")[0].strip()
                else:
                    agent.analysis = analysis_part[:200].strip()
            else:
                agent.analysis = response[:200].strip()
        else:
            agent.analysis = response[:200].strip()

        # Extract vote
        if "bullish" in response_lower:
            agent.vote = "bullish"
        elif "bearish" in response_lower:
            agent.vote = "bearish"
        else:
            agent.vote = "neutral"

        # Extract confidence
        if "[confidence]" in response_lower:
            try:
                conf_part = response_lower.split("[confidence]")[1].strip()
                conf_num = "".join(c for c in conf_part[:5] if c.isdigit())
                agent.confidence = min(100, max(0, float(conf_num)))
            except (ValueError, IndexError):
                agent.confidence = 60.0
        else:
            agent.confidence = 65.0

    def _heuristic_analysis(self, agent: FishAgent, query: str, scenario: str):
        """Fallback heuristic analysis when LLM is unavailable."""
        query_lower = query.lower()

        # Generate deterministic but varied analysis per agent
        seed = int(hashlib.md5(f"{agent.role}:{query}".encode()).hexdigest()[:8], 16)
        random.seed(seed)

        base_confidence = random.uniform(45, 85)

        if agent.role == "research":
            agent.analysis = f"Based on available knowledge patterns for '{query[:40]}', historical trends suggest moderate directional momentum."
            agent.vote = random.choice(["bullish", "neutral", "bullish"])
            agent.confidence = base_confidence + random.uniform(0, 10)

        elif agent.role == "analyst":
            agent.analysis = f"Quantitative pattern analysis for '{query[:40]}' shows cyclical behavior with key inflection points approaching."
            agent.vote = random.choice(["bullish", "bearish", "neutral"])
            agent.confidence = base_confidence + random.uniform(-5, 15)

        elif agent.role == "contrarian":
            agent.analysis = f"Mainstream consensus on '{query[:40]}' overlooks several critical risk factors and potential disruptors."
            agent.vote = "bearish" if scenario != "bearish" else "bullish"
            agent.confidence = base_confidence + random.uniform(-10, 5)

        elif agent.role == "sentinel":
            agent.analysis = f"Risk assessment for '{query[:40]}': tail-risk probability is elevated. Downside protection recommended."
            agent.vote = random.choice(["bearish", "neutral"])
            agent.confidence = base_confidence + random.uniform(-5, 10)

        # Scenario adjustment
        if scenario == "bullish":
            if agent.role != "contrarian":
                agent.confidence += 10
        elif scenario == "bearish":
            if agent.role != "contrarian":
                agent.confidence -= 10
        elif scenario == "shock":
            agent.confidence -= 15
            agent.analysis += " ALERT: Extreme volatility mode activated."

        agent.confidence = min(100, max(10, agent.confidence))
        random.seed()  # Reset random state

    def _aggregate(self, query: str, scenario: str, elapsed: float) -> SwarmPrediction:
        """Aggregate all agent votes into a consensus prediction."""
        votes = {"bullish": 0, "bearish": 0, "neutral": 0}
        total_confidence = 0
        weighted_votes = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}

        for agent in self.agents:
            votes[agent.vote] = votes.get(agent.vote, 0) + 1
            total_confidence += agent.confidence
            weighted_votes[agent.vote] += agent.confidence

        # Determine consensus by weighted vote
        consensus = max(weighted_votes, key=weighted_votes.get)
        avg_confidence = total_confidence / len(self.agents) if self.agents else 0

        # Generate reasoning
        agree_count = votes[consensus]
        dissent = [a.name for a in self.agents if a.vote != consensus]
        if dissent:
            reasoning = f"{agree_count}/{len(self.agents)} agents agree on {consensus.upper()}. Dissent from: {', '.join(dissent)}."
        else:
            reasoning = f"Unanimous {consensus.upper()} consensus across all {len(self.agents)} agents."

        return SwarmPrediction(
            query=query,
            consensus=consensus,
            confidence=round(avg_confidence, 1),
            agents=list(self.agents),
            reasoning=reasoning,
            elapsed_s=round(elapsed, 2),
            scenario=scenario
        )

    def _format_output(self, prediction: SwarmPrediction) -> str:
        """Format the prediction for display."""
        lines = [
            f"🐟 MiroFish Swarm Prediction ({prediction.elapsed_s:.1f}s)",
            f"📋 Query: {prediction.query[:60]}",
            f"🎯 Scenario: {prediction.scenario.upper()}",
            "─" * 42,
        ]

        for agent in prediction.agents:
            vote_emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(agent.vote, "❓")
            lines.append(f"{agent.emoji} {agent.name}: {vote_emoji} {agent.vote.upper()} ({agent.confidence:.0f}%)")
            lines.append(f"   └─ {agent.analysis[:100]}")

        lines.append("─" * 42)

        consensus_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(prediction.consensus, "⚪")
        lines.append(f"🏆 CONSENSUS: {consensus_emoji} {prediction.consensus.upper()}")
        lines.append(f"📊 Swarm Confidence: {prediction.confidence:.0f}%")
        lines.append(f"💡 {prediction.reasoning}")
        lines.append("⚡ Powered by MiroFish Swarm Intelligence")

        return "\n".join(lines)

    # ──────────────────────────────────────────
    # Legacy Compatibility
    # ──────────────────────────────────────────

    def analyze_dataset(self, csv_path: str) -> str:
        """Legacy: Quick analysis of a CSV dataset."""
        log.info("📊 Analyzing dataset: %s", csv_path)
        try:
            import csv
            with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                headers = next(reader)
                rows = [next(reader) for _ in range(min(5, 100))]

            total_rows = sum(1 for _ in open(csv_path, 'r', encoding='utf-8', errors='ignore')) - 1
            summary = f"Dataset: {csv_path}\nColumns ({len(headers)}): {', '.join(headers[:10])}\nRows: {total_rows}\n"
            for row in rows[:3]:
                summary += f"  {', '.join(row[:6])}\n"
            return summary
        except Exception as e:
            return f"Could not read dataset: {e}"

    def run_simulation(self, csv_path: str = "", scenario: str = "Market Prediction"):
        """Legacy compatibility — runs prediction with optional dataset."""
        data_context = self.analyze_dataset(csv_path) if csv_path else ""
        return self.predict(scenario, data_context)
