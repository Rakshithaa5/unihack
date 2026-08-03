"""
backend/discovery/agent.py
===========================
Phase 1 — Discovery Orchestrator

Public surface: a single `discover()` function that matches the interface
contract in backend/schema.py:

    discover(mpn: str, brand: str, description: str) -> list[Source]

Strategy:
  1. Query formulation — Groq LLM (llama-3.1-8b-instant) generates 3 queries.
  2. Web search       — DuckDuckGo executes queries, returns candidate Sources.
  3. Catalog fallback — local JSON corpus search (zero API, always available).
  4. Deduplication    — merge both lists, deduplicate by URL.
  5. Ranking          — sort descending by trust_score for consistent output.

Free-tier discipline:
  - Only 1 Groq LLM call per discover() (query formulation).
  - DDGS search is free and keyless.
  - Catalog search is fully local.
  - Graceful degradation: if Groq is unavailable, rule-based queries kick in.
    If DDGS fails, catalog results alone are returned.
  - Minimum guaranteed output: ≥1 Source (from catalog) for known products.

Configuration (via .env):
  GROQ_API_KEY                     — required for Groq; catalog works without it
  CATALOG_PATH                     — override catalog file path (optional)
  DISCOVERY_MAX_WEB_RESULTS        — per-query DDGS hit cap (default 3)
"""

from __future__ import annotations

import logging
import os
from typing import Final

from dotenv import load_dotenv
from groq import Groq

from backend.schema import Source
from backend.discovery.web_search import formulate_queries, search_web
from backend.discovery.catalog import load_catalog, search_catalog

load_dotenv()
logger = logging.getLogger(__name__)

_MAX_WEB_RESULTS: Final = int(os.environ.get("DISCOVERY_MAX_WEB_RESULTS", "3"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedup(sources: list[Source]) -> list[Source]:
    """
    Remove duplicates by URL, keeping the first occurrence (highest trust
    comes first from web search; catalog may repeat the same URL).
    """
    seen: set[str] = set()
    unique: list[Source] = []
    for src in sources:
        if src.url not in seen:
            seen.add(src.url)
            unique.append(src)
    return unique


def _rank(sources: list[Source]) -> list[Source]:
    """Sort descending by trust_score, then alphabetically by URL for stability."""
    return sorted(sources, key=lambda s: (-s.trust_score, s.url))


def _make_groq_client() -> Groq | None:
    """
    Instantiate the Groq client if GROQ_API_KEY is set; return None otherwise.
    This lets the catalog-only path work without any API key.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key == "your_groq_api_key_here":
        logger.warning(
            "GROQ_API_KEY not set — discovery will use rule-based queries + catalog only."
        )
        return None
    return Groq(api_key=api_key)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def discover(mpn: str, brand: str, description: str) -> list[Source]:
    """
    Discover candidate evidence sources for a product.

    Args:
        mpn:         Manufacturer part number, e.g. "EM75S-001"
        brand:       Brand / manufacturer name, e.g. "Allied Motion"
        description: Short plain-English description, e.g. "brushless DC motor 24V 10A"

    Returns:
        Deduplicated, trust-ranked list[Source].  Always returns ≥0 items;
        typically ≥2-3 for any known MPN (catalog guarantees a floor for
        the 6 pre-seeded products).
    """
    logger.info("[discover] MPN=%r brand=%r", mpn, brand)

    # ── 1. Catalog search (always first; zero cost, zero rate limit) ─────────
    catalog = load_catalog()  # loaded once; cheap dict read
    catalog_sources = search_catalog(mpn, brand, catalog)
    logger.info("[discover] catalog: %d sources", len(catalog_sources))

    # ── 2. Web search (Groq + DuckDuckGo) ────────────────────────────────────
    web_sources: list[Source] = []
    groq_client = _make_groq_client()

    queries = formulate_queries(mpn, brand, description, groq_client) \
        if groq_client else _rule_based_queries(mpn, brand, description)

    try:
        web_sources = search_web(queries, max_results_per_query=_MAX_WEB_RESULTS)
        logger.info("[discover] web: %d sources", len(web_sources))
    except Exception as exc:
        logger.error("[discover] Web search failed (%s); falling back to catalog only.", exc)

    # ── 3. Merge: web results first (live), catalog second (stable) ───────────
    all_sources = web_sources + catalog_sources

    # ── 4. Deduplicate by URL ─────────────────────────────────────────────────
    deduped = _dedup(all_sources)

    # ── 5. Rank by trust score ────────────────────────────────────────────────
    ranked = _rank(deduped)

    logger.info("[discover] %d unique sources returned (before=%d)", len(ranked), len(all_sources))
    return ranked


# ---------------------------------------------------------------------------
# Rule-based query fallback (no Groq required)
# ---------------------------------------------------------------------------

def _rule_based_queries(mpn: str, brand: str, description: str) -> list[str]:
    """Deterministic query strings — used when GROQ_API_KEY is absent."""
    return [
        f"{brand} {mpn} datasheet",
        f"{brand} {mpn} product specifications",
        f'"{mpn}" site:digikey.com OR site:mouser.com OR site:arrow.com',
    ]
