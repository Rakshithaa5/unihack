"""
backend/storage/stub.py — Phase 0.5 stub
=========================================
In-memory (dict-based) stand-in for the SQLite knowledge graph.
Swap out for real SQLite implementation in Phase 4.
"""

from __future__ import annotations

from backend.schema import ResolvedField

# In-memory store: {product_id: {attribute: ResolvedField}}
_store: dict[str, dict[str, ResolvedField]] = {}


def write_field(field: ResolvedField) -> None:
    """
    STUB: stores the field in the in-memory dict (not persisted to disk).
    Real implementation (Phase 4) will INSERT/UPDATE into SQLite.
    """
    print(f"[STUB] write_field: {field.product_id!r}.{field.attribute!r} = {field.value!r}")
    _store.setdefault(field.product_id, {})[field.attribute] = field


def get_product_record(product_id: str) -> dict[str, ResolvedField]:
    """
    STUB: returns all fields for a product from the in-memory store.
    Real implementation (Phase 4) will query SQLite.
    """
    print(f"[STUB] get_product_record: {product_id!r}")
    return _store.get(product_id, {})


def get_evidence_trail(product_id: str, attribute: str) -> ResolvedField | None:
    """
    STUB: returns a single field's evidence trail from the in-memory store.
    Real implementation (Phase 4) will query SQLite with JOIN across source edges.
    """
    print(f"[STUB] get_evidence_trail: {product_id!r}.{attribute!r}")
    return _store.get(product_id, {}).get(attribute)
