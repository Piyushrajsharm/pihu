"""
Pihu — MiroFish Prediction Engine
Swarm-intelligence-inspired prediction system.
Uses Groq/Cloud LLM for analysis when data is available,
provides pattern-based predictions for market/data queries.
"""

import os
import json
import time
from logger import get_logger

log = get_logger("MIROFISH")


class MiroFishSimulator:
    """Prediction engine using LLM-powered analysis.

    Instead of running a separate backend process, MiroFish uses the
    existing LLM infrastructure to analyze data and generate predictions.
    """

    def __init__(self, project_root="d:\\JarvisProject\\pihu\\tools\\MiroFish"):
        self.project_root = project_root
        self.predictions_cache = {}
        log.info("MiroFish Prediction Engine initialized")

    def predict(self, query: str, data_context: str = "") -> str:
        """Generate a prediction based on the query.

        Args:
            query: What to predict (e.g., "stock market trend", "best sector")
            data_context: Optional CSV/data summary for context

        Returns:
            Prediction result string
        """
        log.info("🐟 MiroFish Prediction: %s", query[:60])
        t0 = time.time()

        # Build analysis prompt
        prompt = self._build_analysis_prompt(query, data_context)

        # Try to use Groq first (fastest), then Cloud LLM
        try:
            from config import GROQ_API_KEY, GROQ_MODEL
            if GROQ_API_KEY:
                prediction = self._predict_via_groq(prompt)
                if prediction:
                    elapsed = time.time() - t0
                    log.info("🐟 Prediction complete in %.1fs", elapsed)
                    return self._format_prediction(query, prediction, elapsed)
        except Exception as e:
            log.warning("Groq prediction failed: %s", e)

        # Fallback: pattern-based response
        return self._pattern_prediction(query)

    def analyze_dataset(self, csv_path: str) -> str:
        """Quick analysis of a CSV dataset for prediction context.

        Args:
            csv_path: Path to CSV file

        Returns:
            Summary string of the dataset
        """
        log.info("📊 Analyzing dataset: %s", csv_path)

        try:
            import csv
            with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                headers = next(reader)
                rows = []
                for i, row in enumerate(reader):
                    if i >= 10:  # First 10 rows only
                        break
                    rows.append(row)

            total_rows = sum(1 for _ in open(csv_path, 'r', encoding='utf-8', errors='ignore')) - 1

            summary = f"Dataset: {os.path.basename(csv_path)}\n"
            summary += f"Columns ({len(headers)}): {', '.join(headers[:10])}\n"
            summary += f"Total rows: {total_rows}\n"
            summary += f"Sample data (first 3 rows):\n"
            for row in rows[:3]:
                summary += f"  {', '.join(row[:6])}\n"

            return summary

        except Exception as e:
            log.error("Dataset analysis failed: %s", e)
            return f"Could not read: {csv_path}"

    def _build_analysis_prompt(self, query: str, data_context: str) -> str:
        """Build the LLM prompt for prediction."""
        prompt = f"""You are MiroFish — a swarm-intelligence prediction engine.

TASK: {query}

"""
        if data_context:
            prompt += f"""DATA CONTEXT:
{data_context}

"""
        prompt += """Based on the available information, provide:
1. A confidence score (0-100%)
2. Your prediction/analysis
3. Key factors driving this prediction
4. Risk factors

Keep your response concise (5-8 lines). Be data-driven, not generic.
If you don't have enough data, say so honestly."""

        return prompt

    def _predict_via_groq(self, prompt: str) -> str | None:
        """Use Groq API for fast prediction."""
        import requests
        from config import GROQ_API_KEY, GROQ_MODEL

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
            "temperature": 0.5,
        }

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "")

    def _pattern_prediction(self, query: str) -> str:
        """Fallback: keyword-based pattern predictions."""
        query_lower = query.lower()

        if any(kw in query_lower for kw in ["stock", "market", "nifty", "sensex"]):
            return ("🐟 MiroFish Analysis:\n"
                    "📊 Market prediction requires real-time data feed.\n"
                    "💡 Tip: Load stock data CSV for detailed sector analysis.\n"
                    "⚠️ Confidence: Low (no live data connected)")

        if any(kw in query_lower for kw in ["weather", "temperature"]):
            return ("🐟 MiroFish Analysis:\n"
                    "🌤️ Weather prediction requires location + API data.\n"
                    "💡 Use 'search weather <city>' for real-time data.")

        return (f"🐟 MiroFish received query: {query}\n"
                f"📊 Insufficient data for prediction. Provide a CSV dataset for analysis.\n"
                f"💡 Usage: 'predict market trend using stocks_df.csv'")

    def _format_prediction(self, query: str, prediction: str, elapsed: float) -> str:
        """Format the prediction output."""
        return (f"🐟 MiroFish Prediction ({elapsed:.1f}s):\n"
                f"📋 Query: {query[:50]}\n"
                f"─────────────────────\n"
                f"{prediction}\n"
                f"─────────────────────\n"
                f"⚡ Powered by Swarm Intelligence Engine")

    def run_simulation(self, csv_path: str, scenario: str = "Market Prediction"):
        """Legacy compatibility — runs prediction on a dataset."""
        data_context = self.analyze_dataset(csv_path)
        result = self.predict(scenario, data_context)
        log.info("Simulation result: %s", result[:100])
        return result
