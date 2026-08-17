"""
backend/reconciliation/stub.py — Phase 2 reconciliation logic
=============================================================
Implements source-reliability weighting, conflict detection, and LLM-assisted
arbitration for synthetic tests before Rakshitha's real extraction output exists.
"""

from __future__ import annotations

import math
import os
from typing import Any

from backend.schema import Field, FieldStatus, ResolvedField

try:
    from groq import Groq
except Exception:  # pragma: no cover - dependency may be absent at runtime
    Groq = None  # type: ignore[assignment]


def _source_quality(field: Field) -> float:
    """Weighted trust score combining baseline source reliability and metadata."""
    metadata = field.metadata or {}
    trust = float(metadata.get("source_trust_score", 0.7))

    source_type = str(metadata.get("source_type", "unknown")).lower()
    type_weight = {
        "pdf": 1.0,
        "html": 0.75,
        "image": 0.7,
        "catalog": 0.65,
        "unknown": 0.5,
    }.get(source_type, 0.5)

    origin = str(metadata.get("source_origin", "discovered")).lower()
    origin_weight = 1.0 if origin == "discovered" else 0.82

    recency = float(metadata.get("recency_score", 0.8))
    specificity = float(metadata.get("specificity_score", 0.8))
    internal_consistency = float(metadata.get("internal_consistency", 0.8))

    score = (
        0.5 * trust
        + 0.25 * type_weight
        + 0.1 * origin_weight
        + 0.05 * recency
        + 0.05 * specificity
        + 0.05 * internal_consistency
    )
    return max(0.0, min(1.0, score))


def _normalise_numeric(value: Any) -> float | None:
    """Coerce numeric values to floats when possible."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().lower().replace(",", "")
        if not stripped:
            return None
        try:
            return float(stripped.rstrip("v").rstrip("a").rstrip("w").rstrip("s"))
        except ValueError:
            return None
    return None


def _coerce_value_pair(first: Field, second: Field) -> tuple[float | None, float | None]:
    """Convert both values into numeric space when the units are comparable."""
    left = _normalise_numeric(first.value)
    right = _normalise_numeric(second.value)

    if left is None or right is None:
        return left, right

    if first.unit and second.unit and first.unit != second.unit:
        # Simple unit-normalization for the common engineering dimensions used here.
        unit_map = {
            "v": 1.0,
            "mv": 1e-3,
            "kv": 1e3,
            "a": 1.0,
            "ma": 1e-3,
            "ka": 1e3,
            "w": 1.0,
            "mw": 1e-3,
            "kw": 1e3,
            "kg": 1.0,
            "g": 1e-3,
            "lb": 0.45359237,
            "°c": 1.0,
            "c": 1.0,
        }
        left_factor = unit_map.get(first.unit.lower().replace(" ", ""), 1.0)
        right_factor = unit_map.get(second.unit.lower().replace(" ", ""), 1.0)
        left = left * left_factor
        right = right * right_factor

    return left, right


def _find_best_field(fields: list[Field]) -> Field:
    return max(fields, key=lambda f: (_source_quality(f), float(f.metadata.get("source_trust_score", 0.7))))


def _llm_arbitrate(winner: Field, fields: list[Field]) -> str:
    """Attempt Groq-based arbitration; fallback to a rule-based one-sentence reason."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    winner_value = f"{winner.value} {winner.unit}".strip()
    if not api_key or Groq is None:
        return (
            f"Conflict detected across {len(fields)} sources for {winner.attribute}; "
            f"selected {winner_value} from the highest-trust source ({winner.source_id}) as the best-supported value."
        )

    try:
        client = Groq(api_key=api_key)
        prompt = (
            "You are reconciling conflicting extracted values for a product attribute. "
            "Use the source quality and trust metadata as weighting signals. Return one sentence only. "
            f"Attribute: {winner.attribute}. "
            f"Candidate values: {[(f.value, f.unit, f.source_id, round(_source_quality(f), 3)) for f in fields]}. "
            "Choose the most credible value and explain briefly."
        )
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        text = completion.choices[0].message.content.strip()
        if text:
            if "value" in text.lower() or "selected" in text.lower():
                return text if text.endswith(".") else f"{text}."
            return f"Conflict detected for {winner.attribute}; selected {winner_value} from {winner.source_id}."
    except Exception:
        pass

    return (
        f"Conflict detected across {len(fields)} sources for {winner.attribute}; "
        f"selected {winner_value} from the highest-trust source ({winner.source_id}) based on source reliability weighting."
    )


def reconcile(fields: list[Field]) -> ResolvedField:
    """
    Compare values for the same attribute across sources, detect conflicts,
    and reconcile to a single winning value using a trust-weighted heuristic.
    """
    if not fields:
        raise ValueError("reconcile() received an empty fields list")

    first = fields[0]
    attribute_name = first.attribute
    candidate_fields = [f for f in fields if f.attribute == attribute_name]
    if not candidate_fields:
        candidate_fields = fields

    distinct_values: list[Any] = []
    for field in candidate_fields:
        value_key = field.value
        if isinstance(field.value, str):
            value_key = field.value.strip().lower()
        if value_key not in distinct_values:
            distinct_values.append(value_key)

    # Numeric conflict detection with tolerance for equivalent floats.
    numeric_pairs = []
    for i in range(len(candidate_fields)):
        for j in range(i + 1, len(candidate_fields)):
            left, right = _coerce_value_pair(candidate_fields[i], candidate_fields[j])
            if left is not None and right is not None:
                numeric_pairs.append((left, right, candidate_fields[i], candidate_fields[j]))

    conflict = False
    if len(candidate_fields) > 1:
        for left, right, _, _ in numeric_pairs:
            if not math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-2):
                conflict = True
                break

    if not conflict and len(candidate_fields) > 1:
        # For string values, check an exact match after lowercasing; otherwise they are different values.
        seen_text = set()
        for field in candidate_fields:
            key = str(field.value).strip().lower()
            if key in seen_text:
                continue
            seen_text.add(key)
        conflict = len(seen_text) > 1 and any(
            not isinstance(field.value, (int, float)) for field in candidate_fields
        )

    winner = _find_best_field(candidate_fields)
    quality = _source_quality(winner)
    confidence = 0.52 + (quality * 0.43)

    if conflict:
        alternate_values = []
        for field in candidate_fields:
            if field.source_id == winner.source_id:
                continue
            alt = {
                "value": field.value,
                "unit": field.unit,
                "source_id": field.source_id,
                "trust_score": round(_source_quality(field), 4),
            }
            alternate_values.append(alt)

        reasoning = _llm_arbitrate(winner, candidate_fields)
        return ResolvedField(
            product_id=winner.product_id,
            attribute=winner.attribute,
            value=winner.value,
            unit=winner.unit,
            source_id=winner.source_id,
            raw_snippet=winner.raw_snippet,
            confidence=max(0.5, min(0.99, confidence)),
            status=FieldStatus.CONFLICT_RESOLVED,
            reasoning=reasoning,
            alternate_values=alternate_values,
        )

    reasoning = (
        f"All {len(candidate_fields)} source(s) agree on {winner.value} {winner.unit or ''} "
        f"and the highest-trust source was selected."
    ).strip()

    return ResolvedField(
        product_id=winner.product_id,
        attribute=winner.attribute,
        value=winner.value,
        unit=winner.unit,
        source_id=winner.source_id,
        raw_snippet=winner.raw_snippet,
        confidence=max(0.7, min(0.99, confidence)),
        status=FieldStatus.RESOLVED,
        reasoning=reasoning,
        alternate_values=[],
    )
