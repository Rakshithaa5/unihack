"""
backend/schema.py — Shared Data Schema
=======================================
Phase 0: Built jointly by both people, then LOCKED.
Neither person edits this file solo afterward.

All downstream agents (extraction, reconciliation, enrichment, validation,
storage, HITL) import from this single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SourceOrigin(str, Enum):
    """How a source entered the evidence pool."""
    DISCOVERED = "discovered"   # found by the Discovery Agent
    UPLOADED = "uploaded"       # provided by the user


class SourceType(str, Enum):
    """Document / media type of the source."""
    PDF = "pdf"
    HTML = "html"
    IMAGE = "image"
    UNKNOWN = "unknown"


class FieldStatus(str, Enum):
    """Processing status of a resolved field."""
    RESOLVED = "resolved"                   # single unambiguous value
    CONFLICT_RESOLVED = "conflict_resolved" # conflict found and arbitrated
    ENRICHED = "enriched"                   # filled via RAG from another doc
    NEEDS_REVIEW = "needs_review"           # low confidence → HITL queue


# ---------------------------------------------------------------------------
# Core data shapes
# ---------------------------------------------------------------------------

@dataclass
class Source:
    """
    A document, webpage, or image that is part of the evidence pool.

    Created by:
      - Discovery Agent (origin=DISCOVERED)
      - Upload Handler  (origin=UPLOADED)
    """
    source_id: str                   # unique identifier (UUID or URL hash)
    url: str                         # URL or file path
    source_type: SourceType          # pdf | html | image | unknown
    origin: SourceOrigin             # discovered | uploaded
    trust_score: float = 0.7         # 0.0–1.0; rule-based baseline, HITL-adjusted
    title: str = ""                  # page/document title
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    raw_content: str = ""            # raw text / bytes reference (optional cache)
    metadata: dict[str, Any] = field(default_factory=dict)  # arbitrary extras

    def __post_init__(self) -> None:
        if not (0.0 <= self.trust_score <= 1.0):
            raise ValueError(f"trust_score must be in [0, 1], got {self.trust_score}")


@dataclass
class Field:
    """
    A single extracted data point from one source.

    Produced by:
      - extract_pdf(), extract_html(), extract_image()  (Rakshitha)
    Consumed by:
      - reconcile()  (Ramya)
    """
    product_id: str          # identifier linking this field to a product
    attribute: str           # e.g. "voltage_rating", "weight", "operating_temp"
    value: Any               # raw extracted value (str | int | float | list)
    unit: str = ""           # e.g. "V", "kg", "°C" — empty if dimensionless
    source_id: str = ""      # Source.source_id this was pulled from
    raw_snippet: str = ""    # the exact text / image region it came from
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedField:
    """
    A Field after reconciliation / enrichment / validation.

    Produced by:
      - reconcile()   → status RESOLVED or CONFLICT_RESOLVED   (Ramya)
      - enrich()      → status ENRICHED                        (Rakshitha)
      - validate()    → status NEEDS_REVIEW (if low confidence)(Ramya)

    Written to the Knowledge Graph by the storage layer (Ramya).
    """
    product_id: str
    attribute: str
    value: Any
    unit: str = ""
    source_id: str = ""           # winning source
    raw_snippet: str = ""
    confidence: float = 0.5       # 0.0–1.0
    status: FieldStatus = FieldStatus.RESOLVED
    reasoning: str = ""           # one-line explanation for the chosen value
    alternate_values: list[dict[str, Any]] = field(default_factory=list)
    # Each entry: {"value": ..., "unit": ..., "source_id": ..., "trust_score": ...}
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


# ---------------------------------------------------------------------------
# Interface contract (function signatures — do NOT change without both people)
# ---------------------------------------------------------------------------
#
# Rakshitha's functions (Ramya's code calls these):
#   discover(mpn: str, brand: str, description: str) -> list[Source]
#   extract_pdf(source: Source) -> list[Field]
#   extract_html(source: Source) -> list[Field]
#   extract_image(source: Source) -> list[Field]
#   enrich(missing_field: Field, corpus) -> ResolvedField | None
#
# Ramya's functions (Rakshitha's code calls these):
#   merge_sources(discovered: list[Source], uploaded: list[Source]) -> list[Source]
#   reconcile(fields: list[Field]) -> ResolvedField
#   validate(field: ResolvedField) -> ResolvedField
#
# ---------------------------------------------------------------------------
