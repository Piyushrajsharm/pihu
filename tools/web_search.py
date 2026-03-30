"""
Pihu — Web Search Tool
DuckDuckGo search with SerpAPI fallback.
"""

from typing import Optional

from logger import get_logger

log = get_logger("TOOL")


class WebSearch:
    """Web search tool using DuckDuckGo (primary) and SerpAPI (fallback)."""

    def __init__(self):
        from config import WEB_SEARCH_MAX_RESULTS, SERPAPI_KEY

        self.max_results = WEB_SEARCH_MAX_RESULTS
        self.serpapi_key = SERPAPI_KEY

        log.info("WebSearch initialized | max_results=%d", self.max_results)

    def search(self, query: str) -> list[dict]:
        """Search the web and return results.
        
        Args:
            query: Search query string

        Returns:
            List of dicts with 'title', 'snippet', 'url'
        """
        log.info("🔍 Searching: '%s'", query)

        # Try DuckDuckGo first
        results = self._duckduckgo_search(query)

        # Fallback to SerpAPI if needed
        if not results and self.serpapi_key:
            results = self._serpapi_search(query)

        log.info("🔍 Found %d results", len(results))
        return results

    def _duckduckgo_search(self, query: str) -> list[dict]:
        """Search using DuckDuckGo."""
        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=self.max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                        "url": r.get("href", ""),
                    })

            return results

        except Exception as e:
            log.error("DuckDuckGo search failed: %s", e)
            return []

    def _serpapi_search(self, query: str) -> list[dict]:
        """Fallback search using SerpAPI."""
        try:
            import httpx

            response = httpx.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": self.serpapi_key,
                    "num": self.max_results,
                },
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for r in data.get("organic_results", [])[:self.max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "url": r.get("link", ""),
                })

            return results

        except Exception as e:
            log.error("SerpAPI search failed: %s", e)
            return []
