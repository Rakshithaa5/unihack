"""
backend/pipeline.py — Owned exclusively by Ramya
==================================================
Wires the pipeline stages together. Rakshitha's functions are imported and
called here; Rakshitha never pushes to this file.

Phase 0.5: stub chain — calls each module's stub in sequence.
Phase 6 target: swap each stub call for the real function, one at a time.
"""

from __future__ import annotations

from backend.schema import Field, FieldStatus, ResolvedField, Source
from backend.discovery import discover
from backend.collector import merge_sources
from backend.extraction import extract_pdf, extract_html, extract_image
from backend.reconciliation import reconcile
from backend.enrichment import enrich
from backend.validation import validate
from backend import storage


def run_pipeline(
    mpn: str,
    brand: str,
    description: str,
    uploaded_sources: list[Source] | None = None,
) -> dict[str, ResolvedField]:
    """
    Full pipeline: discover → collect → extract → reconcile → enrich → validate → store.

    Supports both demo workflows:
      Workflow A — discovery-only:   uploaded_sources=None or []
      Workflow B — discovery+upload: uploaded_sources=[<Source>, ...]

    Returns:
        dict mapping attribute name → ResolvedField (the product's knowledge record).
    """
    uploaded_sources = uploaded_sources or []

    # Stage 1 — Discovery
    discovered = discover(mpn, brand, description)

    # Stage 2 — Source collection / merge
    evidence_pool: list[Source] = merge_sources(discovered, uploaded_sources)

    # Stage 3 — Extraction (all source types)
    all_fields: list[Field] = []
    for source in evidence_pool:
        from backend.schema import SourceType
        if source.source_type == SourceType.PDF:
            all_fields.extend(extract_pdf(source))
        elif source.source_type == SourceType.HTML:
            all_fields.extend(extract_html(source))
        elif source.source_type == SourceType.IMAGE:
            all_fields.extend(extract_image(source))

    # Stage 4 — Group by attribute, then reconcile each group
    from collections import defaultdict
    fields_by_attr: dict[str, list[Field]] = defaultdict(list)
    for f in all_fields:
        fields_by_attr[f.attribute].append(f)

    resolved_fields: dict[str, ResolvedField] = {}
    for attribute, fields in fields_by_attr.items():
        resolved = reconcile(fields)

        # Stage 5 — Enrichment (only for missing / low-confidence fields)
        if resolved.confidence < 0.4:
            enriched = enrich(
                Field(
                    product_id=resolved.product_id,
                    attribute=resolved.attribute,
                    value=None,
                    source_id="",
                ),
                corpus=None,  # Phase 3 will pass a real Chroma corpus here
            )
            if enriched is not None:
                resolved = enriched

        # Stage 6 — Validation (confidence scoring + HITL routing)
        resolved = validate(resolved)

        # Stage 7 — Persist to knowledge graph
        storage.write_field(resolved)
        resolved_fields[attribute] = resolved

    return resolved_fields
