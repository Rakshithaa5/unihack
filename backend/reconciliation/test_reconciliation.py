from __future__ import annotations

from backend.schema import Field, FieldStatus
from backend.reconciliation.stub import reconcile


def test_reconcile_detects_conflict_and_prefers_high_trust_source() -> None:
    fields = [
        Field(
            product_id="P-001",
            attribute="voltage_rating",
            value=24,
            unit="V",
            source_id="pdf-1",
            raw_snippet="Rated Voltage: 24 V",
            metadata={
                "source_type": "pdf",
                "source_origin": "discovered",
                "source_trust_score": 0.92,
            },
        ),
        Field(
            product_id="P-001",
            attribute="voltage_rating",
            value=26,
            unit="V",
            source_id="web-1",
            raw_snippet="Voltage: 26V",
            metadata={
                "source_type": "html",
                "source_origin": "discovered",
                "source_trust_score": 0.65,
            },
        ),
        Field(
            product_id="P-001",
            attribute="voltage_rating",
            value=22,
            unit="V",
            source_id="upload-1",
            raw_snippet="Manual says 22 V",
            metadata={
                "source_type": "pdf",
                "source_origin": "uploaded",
                "source_trust_score": 0.75,
            },
        ),
    ]

    resolved = reconcile(fields)

    assert resolved.attribute == "voltage_rating"
    assert resolved.status == FieldStatus.CONFLICT_RESOLVED
    assert resolved.value == 24
    assert resolved.source_id == "pdf-1"
    assert "conflict" in resolved.reasoning.lower()
    assert "24" in resolved.reasoning


def test_reconcile_accepts_consistent_values_without_conflict() -> None:
    fields = [
        Field(
            product_id="P-002",
            attribute="current_rating",
            value=10,
            unit="A",
            source_id="pdf-2",
            raw_snippet="10 A",
            metadata={
                "source_type": "pdf",
                "source_origin": "discovered",
                "source_trust_score": 0.9,
            },
        ),
        Field(
            product_id="P-002",
            attribute="current_rating",
            value=10,
            unit="A",
            source_id="web-2",
            raw_snippet="Current 10A",
            metadata={
                "source_type": "html",
                "source_origin": "discovered",
                "source_trust_score": 0.7,
            },
        ),
    ]

    resolved = reconcile(fields)

    assert resolved.status == FieldStatus.RESOLVED
    assert resolved.value == 10
    assert resolved.confidence >= 0.7
    assert resolved.source_id in {"pdf-2", "web-2"}
