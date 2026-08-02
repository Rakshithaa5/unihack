"""
backend/validation/stub.py — Phase 0.5 stub
============================================
Returns the field unchanged (no confidence adjustment, no HITL routing).
Swap out for real implementation in Phase 3.
"""

from __future__ import annotations

from backend.schema import ResolvedField


def validate(field: ResolvedField) -> ResolvedField:
    """
    STUB: returns the ResolvedField exactly as received.
    Real implementation (Phase 3) will compute a final confidence score and
    route low-confidence fields to status=NEEDS_REVIEW for the HITL queue.
    """
    print(f"[STUB] validate: attribute={field.attribute!r}, confidence={field.confidence:.2f}")
    return field
