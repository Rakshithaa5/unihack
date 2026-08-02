"""
backend/enrichment/stub.py — Phase 0.5 stub
============================================
Returns None (no enrichment found), matching the real function's return type.
Swap out for real RAG implementation in Phase 3.
"""

from __future__ import annotations

from backend.schema import Field, ResolvedField


def enrich(missing_field: Field, corpus: object) -> ResolvedField | None:
    """
    STUB: always returns None, indicating no enrichment was possible.
    Real implementation (Phase 3) will query a Chroma vector store with
    sentence-transformers embeddings and call Groq LLM for extraction.
    """
    print(f"[STUB] enrich: attribute={missing_field.attribute!r} — no enrichment (stub)")
    return None
