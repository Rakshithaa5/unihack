"""
backend/discovery/stub.py — Phase 0.5 stub
==========================================
Returns hardcoded Source objects that match the Phase 0 schema exactly.
Swap this out for the real implementation in Phase 1.
"""

from __future__ import annotations

import uuid
from backend.schema import Field, ResolvedField, Source, SourceOrigin, SourceType


def discover(mpn: str, brand: str, description: str) -> list[Source]:
    """
    STUB: returns 3 made-up Source objects with correct schema shapes.
    Real implementation (Phase 1) will call Groq LLM + web-search API.
    """
    print(f"[STUB] discover called: mpn={mpn!r}, brand={brand!r}")
    return [
        Source(
            source_id=str(uuid.uuid4()),
            url=f"https://example-manufacturer.com/{mpn}-datasheet.pdf",
            source_type=SourceType.PDF,
            origin=SourceOrigin.DISCOVERED,
            trust_score=0.9,
            title=f"{brand} {mpn} Datasheet",
        ),
        Source(
            source_id=str(uuid.uuid4()),
            url=f"https://distributor.example.com/products/{mpn}",
            source_type=SourceType.HTML,
            origin=SourceOrigin.DISCOVERED,
            trust_score=0.6,
            title=f"{mpn} — Distributor Listing",
        ),
        Source(
            source_id=str(uuid.uuid4()),
            url=f"https://images.example.com/{mpn}-nameplate.jpg",
            source_type=SourceType.IMAGE,
            origin=SourceOrigin.DISCOVERED,
            trust_score=0.5,
            title=f"{mpn} Nameplate Image",
        ),
    ]
