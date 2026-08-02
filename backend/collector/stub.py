"""
backend/collector/stub.py — Phase 0.5 stub
==========================================
Returns a merged source list (discovered + uploaded) with correct schema shapes.
Swap out for real implementation in Phase 1.
"""

from __future__ import annotations

from backend.schema import Source


def merge_sources(
    discovered: list[Source],
    uploaded: list[Source],
) -> list[Source]:
    """
    STUB: simply concatenates discovered and uploaded sources, uploaded first.
    Real implementation (Phase 1) will deduplicate, validate, and score.
    """
    print(f"[STUB] merge_sources: {len(discovered)} discovered + {len(uploaded)} uploaded")
    # Uploaded docs are prioritized (inserted first in the pool)
    return uploaded + discovered
