from __future__ import annotations

from backend.hitl import get_review_queue, override_field
from backend.schema import FieldStatus, ResolvedField
from backend.validation import validate


def _make_field(*, source_id="src-1", value="24", unit="V", confidence=0.82, status=FieldStatus.RESOLVED, source_trust=0.8, llm_conf=0.7):
    return ResolvedField(
        product_id="p-001",
        attribute="voltage_rating",
        value=value,
        unit=unit,
        source_id=source_id,
        raw_snippet="24V",
        confidence=confidence,
        status=status,
        reasoning="Candidate value selected from a high-trust source.",
        metadata={
            "source_trust_score": source_trust,
            "llm_confidence": llm_conf,
        },
    )


def test_validate_combines_source_reliability_and_llm_certainty():
    field = _make_field(source_trust=0.9, llm_conf=0.55)

    result = validate(field)

    assert 0.0 <= result.confidence <= 1.0
    assert result.metadata["source_trust_score"] == 0.9
    assert result.metadata["llm_confidence"] == 0.55
    assert result.confidence > 0.5


def test_validate_routes_low_confidence_fields_to_human_review():
    field = _make_field(confidence=0.55, source_trust=0.35, llm_conf=0.45)

    result = validate(field)

    assert result.status == FieldStatus.NEEDS_REVIEW
    assert result in get_review_queue()


def test_override_field_updates_value_and_adjusts_source_trust():
    field = _make_field(source_id="src-override", value="24", unit="V", confidence=0.55, status=FieldStatus.NEEDS_REVIEW, source_trust=0.72, llm_conf=0.40)

    result = override_field(field, "26")

    assert result.value == "26"
    assert result.status == FieldStatus.RESOLVED
    assert "hitl override" in result.reasoning.lower()
    assert result.metadata["source_trust_score"] < 0.72
