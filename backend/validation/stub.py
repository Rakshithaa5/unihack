"""
backend/validation/stub.py — Phase 3 validation logic
======================================================
Computes a final confidence score from source reliability and model certainty,
then routes low-confidence fields into the HITL review queue.
"""

from __future__ import annotations

from backend.hitl.stub import enqueue_review_field
from backend.schema import FieldStatus, ResolvedField

_VALIDATION_THRESHOLD = 0.70


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def validate(field: ResolvedField) -> ResolvedField:
    """
    Combine source reliability and the LLM's own certainty into a final score.

    The result is always stored back onto the field so downstream storage and
    API layers can read the final confidence and status in one place.
    """
    metadata = dict(field.metadata or {})
    source_trust = float(metadata.get("source_trust_score", field.confidence))
    llm_confidence = float(metadata.get("llm_confidence", field.confidence))

    source_trust = _clamp(source_trust)
    llm_confidence = _clamp(llm_confidence)

    # Weighted blend: source reliability should matter, but the model's stated
    # certainty still influences the final acceptance threshold.
    final_confidence = _clamp((0.6 * source_trust) + (0.4 * llm_confidence))
    field.metadata = metadata
    field.metadata["source_trust_score"] = source_trust
    field.metadata["llm_confidence"] = llm_confidence
    field.metadata["final_confidence"] = round(final_confidence, 4)
    field.metadata["validation_threshold"] = _VALIDATION_THRESHOLD
    field.confidence = final_confidence

    if final_confidence < _VALIDATION_THRESHOLD:
        field.status = FieldStatus.NEEDS_REVIEW
        field.reasoning = (
            f"Confidence {final_confidence:.2f} fell below threshold {_VALIDATION_THRESHOLD:.2f}; "
            "flagged for human review."
        )
        enqueue_review_field(field)
    else:
        field.status = field.status if field.status in {FieldStatus.RESOLVED, FieldStatus.CONFLICT_RESOLVED, FieldStatus.ENRICHED} else FieldStatus.RESOLVED
        field.reasoning = field.reasoning or "Field passed validation confidence threshold."
        if field.status == FieldStatus.NEEDS_REVIEW:
            field.status = FieldStatus.RESOLVED

    return field
