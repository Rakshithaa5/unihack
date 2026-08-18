"""
backend/discovery/catalog.py
=============================
Phase 1 — Catalog Sub-Agent (local reference corpus fallback)

Searches a small pre-loaded JSON catalog file for products matching
the given MPN or brand — completely offline, zero API cost, zero rate limit.

Use cases:
  - Primary fallback when live web search is thin or unavailable.
  - Demo rehearsal mode: always returns deterministic results for known MPNs.
  - Groq rate-limit buffer: if the LLM call quota is exhausted, the catalog
    still gives Ramya's merger something to work with.

Catalog format: data/reference_catalog.json (list of product dicts).
See data/reference_catalog.json for the full schema.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Final

from backend.schema import Source, SourceOrigin, SourceType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CATALOG_PATH: Final = Path(__file__).parents[2] / "data" / "reference_catalog.json"

_SOURCE_TYPE_MAP: Final[dict[str, SourceType]] = {
    "pdf":   SourceType.PDF,
    "html":  SourceType.HTML,
    "image": SourceType.IMAGE,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _url_to_source_id(url: str) -> str:
    """Stable ID derived from URL hash, prefixed for catalog entries."""
    return "cat-" + hashlib.sha1(url.encode()).hexdigest()[:12]


def _normalise(text: str) -> str:
    """Lower-case and strip for fuzzy matching."""
    return text.lower().strip()


def _matches(product: dict, mpn: str, brand: str) -> bool:
    """
    Return True if the catalog product matches by MPN or brand substring.

    Matching rules (evaluated in priority order):
      1. MPN exact match (case-insensitive) — highest confidence.
      2. MPN substring match within any product alias.
      3. Brand substring match — only when MPN is absent/unknown and brand
         has ≥3 chars (guards against empty strings matching everything).
    """
    mpn_norm  = _normalise(mpn)
    brand_norm = _normalise(brand)

    # Guard: nothing to match on
    if not mpn_norm and not brand_norm:
        return False

    # 1. Exact MPN match
    if mpn_norm and mpn_norm == _normalise(product.get("mpn", "")):
        return True

    # 2. MPN substring match in any alias
    if mpn_norm:
        for alias in product.get("aliases", []):
            if mpn_norm == _normalise(alias) or mpn_norm in _normalise(alias):
                return True

    # 3. Brand-only match: require ≥3 chars and no MPN provided
    #    (avoids brand match when caller supplies a real but unrecognised MPN)
    if not mpn_norm and len(brand_norm) >= 3:
        if brand_norm in _normalise(product.get("brand", "")):
            return True

    return False


def _entry_to_source(entry: dict) -> Source:
    """Convert a catalog source dict into a schema-compliant Source object."""
    url = entry.get("url", "")
    raw_type = entry.get("source_type", "html")
    return Source(
        source_id=_url_to_source_id(url),
        url=url,
        source_type=_SOURCE_TYPE_MAP.get(raw_type, SourceType.HTML),
        origin=SourceOrigin.DISCOVERED,
        trust_score=float(entry.get("trust_score", 0.85)),
        title=entry.get("title", ""),
        metadata={"catalog": True},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_catalog(path: Path | str | None = None) -> list[dict]:
    """
    Load and return the reference catalog as a list of product dicts.

    Args:
        path: explicit path to catalog JSON. Defaults to data/reference_catalog.json.

    Returns empty list (and logs a warning) if the file is missing or malformed.
    """
    catalog_path = Path(path) if path else _DEFAULT_CATALOG_PATH

    # Allow env override for testing / deployment flexibility.
    env_path = os.environ.get("CATALOG_PATH")
    if env_path:
        catalog_path = Path(env_path)

    if not catalog_path.exists():
        logger.warning("Catalog file not found: %s — catalog sub-agent disabled.", catalog_path)
        return []

    try:
        with catalog_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Catalog JSON must be a list of product dicts.")
        logger.debug("Loaded catalog: %d products from %s", len(data), catalog_path)
        return data
    except Exception as exc:
        logger.error("Failed to load catalog from %s: %s", catalog_path, exc)
        return []


def search_catalog(
    mpn: str,
    brand: str,
    catalog: list[dict] | None = None,
) -> list[Source]:
    """
    Find all sources in the catalog that match this MPN / brand.

    Args:
        mpn:     manufacturer part number.
        brand:   product brand / manufacturer name.
        catalog: pre-loaded catalog list; loads from disk if None.

    Returns:
        List of Source objects (may be empty if no match found).
    """
    if catalog is None:
        catalog = load_catalog()

    sources: list[Source] = []
    for product in catalog:
        if not _matches(product, mpn, brand):
            continue
        for entry in product.get("sources", []):
            sources.append(_entry_to_source(entry))

    logger.info("[catalog] %d sources found for MPN=%r brand=%r", len(sources), mpn, brand)
    return sources
