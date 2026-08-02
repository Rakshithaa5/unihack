"""
backend/hitl/stub.py — Phase 0.5 stub
======================================
Provides a stub HITL review queue — always empty, override is a no-op.
Swap out for real implementation in Phase 3.
"""

from __future__ import annotations

from backend.schema import ResolvedField


def get_review_queue() -> list[ResolvedField]:
    """
    STUB: returns an empty review queue.
    Real implementation (Phase 3) will query all fields with status=NEEDS_REVIEW
    from the knowledge graph storage.
    """
    print("[STUB] get_review_queue: returning empty queue")
    return []


def override_field(field: ResolvedField, new_value: object) -> ResolvedField:
    """
    STUB: sets the value but does not persist or adjust trust scores.
    Real implementation (Phase 3) will persist to storage and nudge the
    source's trust_score up or down based on the override direction.
    """
    print(f"[STUB] override_field: {field.attribute!r} → {new_value!r}")
    field.value = new_value
    field.reasoning = f"HITL override: accepted value {new_value!r} (stub)"
    return field
