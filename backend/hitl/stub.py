"""
backend/hitl/stub.py — Phase 3 HITL review queue
================================================
Tracks fields that fell below the validation threshold and lets a human accept
or correct a value while nudging the winning source trust score up or down.
"""

from __future__ import annotations

from backend.schema import FieldStatus, ResolvedField

_REVIEW_QUEUE: list[ResolvedField] = []


def enqueue_review_field(field: ResolvedField) -> None:
    """Append a flagged field to the review queue unless it is already present."""
    if field not in _REVIEW_QUEUE:
        _REVIEW_QUEUE.append(field)


def get_review_queue() -> list[ResolvedField]:
    """Return the current list of fields awaiting human review."""
    return list(_REVIEW_QUEUE)


def override_field(field: ResolvedField, new_value: object) -> ResolvedField:
    """
    Apply a human override to a flagged or manually reviewed field.

    If the override changes the value, the source trust score is reduced slightly.
    If the human keeps the same value, the source trust score is nudged upward.
    """
    previous_value = field.value
    before = float(field.metadata.get("source_trust_score", 0.7))

    field.value = new_value
    field.status = FieldStatus.RESOLVED
    field.reasoning = (
        f"HITL override: accepted value {new_value!r} instead of {previous_value!r}; "
        "manual review updated the field."
    )

    if new_value == previous_value:
        adjusted = min(1.0, before + 0.05)
        field.reasoning = f"HITL override: confirmed original value {new_value!r}; trust nudged up."
    else:
        adjusted = max(0.0, before - 0.10)
        field.reasoning = (
            f"HITL override: corrected value from {previous_value!r} to {new_value!r}; "
            "trust score reduced for the source."
        )

    field.metadata["source_trust_score"] = round(adjusted, 4)
    field.metadata["override_applied"] = True
    field.metadata["override_value"] = new_value
    field.confidence = max(0.0, min(1.0, field.confidence + 0.05))

    if field in _REVIEW_QUEUE:
        _REVIEW_QUEUE.remove(field)

    return field
