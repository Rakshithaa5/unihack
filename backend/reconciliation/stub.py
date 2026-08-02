"""
backend/reconciliation/stub.py — Phase 0.5 stub
================================================
Returns the first Field unchanged, wrapped as a ResolvedField with confidence 0.5.
Swap out for real implementation in Phase 2.
"""

from __future__ import annotations

from backend.schema import Field, FieldStatus, ResolvedField


def reconcile(fields: list[Field]) -> ResolvedField:
    """
    STUB: takes the first field from the list and wraps it as a ResolvedField.
    Real implementation (Phase 2) will compare values across sources, detect
    conflicts, and call Groq LLM for arbitration when conflicts exist.
    """
    if not fields:
        raise ValueError("reconcile() received an empty fields list")

    first = fields[0]
    print(f"[STUB] reconcile: attribute={first.attribute!r}, {len(fields)} source(s)")
    return ResolvedField(
        product_id=first.product_id,
        attribute=first.attribute,
        value=first.value,
        unit=first.unit,
        source_id=first.source_id,
        raw_snippet=first.raw_snippet,
        confidence=0.5,
        status=FieldStatus.RESOLVED,
        reasoning="Stub: first source accepted without conflict checking.",
        alternate_values=[],
    )
