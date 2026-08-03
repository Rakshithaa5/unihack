"""
backend/discovery/web_search.py
================================
Phase 1 — Web-Search Sub-Agent

Responsibilities:
  1. Use Groq LLM (llama-3.1-8b-instant) to formulate 3 targeted search queries
     from an MPN + brand + description.
  2. Execute each query against DuckDuckGo (zero API key, free tier).
  3. Map results to Source objects, scoring trust by domain heuristic.

Rate-limit discipline:
  - Groq: exactly 1 call per discover() invocation (query formulation only).
  - DDGS: small max_results cap + inter-query sleep to avoid bans.
  - Results are NOT cached here; caching is handled at the agent.py level.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Final

from ddgs import DDGS  # formerly duckduckgo_search, renamed to ddgs
from groq import Groq

from backend.schema import Source, SourceOrigin, SourceType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# LLM model: 8B is fast and cheap — query formulation needs very few tokens.
_GROQ_MODEL: Final = "llama-3.1-8b-instant"
_MAX_QUERIES: Final = 3          # number of queries formulated by LLM
_MAX_RESULTS_PER_QUERY: Final = 3  # DuckDuckGo hits per query
_INTER_QUERY_SLEEP: Final = 1.0  # seconds between DDGS calls (politeness)

# Heuristic trust score by domain pattern (order matters — first match wins).
_DOMAIN_TRUST: Final[list[tuple[str, float]]] = [
    # Manufacturer / official product pages (matched before generic .pdf rule)
    (r"alliedmotion\.com", 0.95),
    (r"ti\.com", 0.95),
    (r"st\.com", 0.95),
    (r"nordicsemi\.com", 0.95),
    (r"allegromicro\.com", 0.95),
    (r"invensense\.tdk\.com", 0.95),
    (r"\.com/datasheet", 0.90),
    (r"\.pdf$", 0.90),              # generic PDF — after manufacturer patterns
    # Major distributors
    (r"digikey\.com", 0.75),
    (r"mouser\.com", 0.75),
    (r"arrow\.com", 0.72),
    (r"farnell\.com", 0.72),
    (r"rs-online\.com", 0.70),
    (r"avnet\.com", 0.70),
    # Datasheet aggregators — lower trust
    (r"datasheetspdf\.com", 0.55),  # .pdf$ above doesn't match .com domains
    (r"datasheet\.live", 0.50),
]
_DEFAULT_TRUST: Final = 0.55


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _url_to_source_id(url: str) -> str:
    """Stable, short ID derived from URL hash."""
    return "web-" + hashlib.sha1(url.encode()).hexdigest()[:12]


def _infer_source_type(url: str) -> SourceType:
    """Guess document type from URL extension."""
    url_lower = url.lower()
    if url_lower.endswith(".pdf") or "datasheet" in url_lower:
        return SourceType.PDF
    if re.search(r"\.(jpg|jpeg|png|webp|gif)$", url_lower):
        return SourceType.IMAGE
    return SourceType.HTML


def _score_trust(url: str) -> float:
    """Apply domain heuristic to assign a trust score."""
    url_lower = url.lower()
    for pattern, score in _DOMAIN_TRUST:
        if re.search(pattern, url_lower):
            return score
    return _DEFAULT_TRUST



def _result_to_source(result: dict) -> Source:
    """Convert a single DDGS result dict into a Source object."""
    url = result.get("href") or result.get("url", "")
    title = result.get("title", "")
    body = result.get("body", "")
    return Source(
        source_id=_url_to_source_id(url),
        url=url,
        source_type=_infer_source_type(url),
        origin=SourceOrigin.DISCOVERED,
        trust_score=_score_trust(url),
        title=title,
        metadata={"snippet": body[:300]},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def formulate_queries(
    mpn: str,
    brand: str,
    description: str,
    groq_client: Groq | None,
) -> list[str]:
    """
    Use Groq LLM to produce up to _MAX_QUERIES targeted search strings.

    Returns a list of query strings. Falls back to simple rule-based queries
    if the LLM call fails (e.g. key missing, rate limit hit).
    """
    system_prompt = (
        "You are a technical procurement assistant. Given a product MPN, brand, "
        "and description, generate exactly 3 distinct web search queries that will "
        "find the official datasheet, distributor listing, and manufacturer product "
        "page for this component. Return ONLY a JSON array of 3 strings, no extra text."
    )
    user_prompt = (
        f"MPN: {mpn}\nBrand: {brand}\nDescription: {description}\n\n"
        f"Return 3 search queries as a JSON array of strings."
    )

    try:
        response = groq_client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        # Extract JSON array robustly — the model may wrap it in markdown fences.
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if match:
            queries = json.loads(match.group())
            if isinstance(queries, list):
                return [str(q) for q in queries[:_MAX_QUERIES]]
    except Exception as exc:
        logger.warning("Groq query formulation failed (%s); using rule-based fallback.", exc)

    # Rule-based fallback — always works, zero API cost.
    return [
        f"{brand} {mpn} datasheet",
        f"{brand} {mpn} product specifications",
        f"{mpn} {description} filetype:pdf OR site:digikey.com OR site:mouser.com",
    ]


def search_web(
    queries: list[str],
    max_results_per_query: int = _MAX_RESULTS_PER_QUERY,
) -> list[Source]:
    """
    Execute each query against DuckDuckGo and return deduplicated Sources.

    Applies polite inter-query sleep to avoid rate-banning.
    Silently skips any query that raises an exception.
    """
    seen_urls: set[str] = set()
    sources: list[Source] = []

    with DDGS() as ddgs:
        for i, query in enumerate(queries):
            if i > 0:
                time.sleep(_INTER_QUERY_SLEEP)
            try:
                results = list(ddgs.text(query, max_results=max_results_per_query))
            except Exception as exc:
                logger.warning("DDGS query %r failed: %s", query, exc)
                continue

            for result in results:
                url = result.get("href") or result.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                sources.append(_result_to_source(result))
                logger.debug("Found source: %s (trust=%.2f)", url, sources[-1].trust_score)

    logger.info("[web_search] %d unique sources from %d queries.", len(sources), len(queries))
    return sources
