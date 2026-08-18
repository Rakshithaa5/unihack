"""
backend/collector/stub.py — Phase 1 collector implementation
============================================================
Builds the evidence pool by merging discovered and uploaded sources into a
well-formed, deduplicated list that matches the shared `Source` schema.
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from backend.schema import Source, SourceOrigin, SourceType


def _infer_source_type(filename: str, content_type: str | None = None) -> SourceType:
    """Infer a SourceType from upload filename or MIME type."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or (content_type or "").lower() == "application/pdf":
        return SourceType.PDF
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"} or (content_type or "").lower().startswith("image/"):
        return SourceType.IMAGE
    if suffix in {".html", ".htm"}:
        return SourceType.HTML
    return SourceType.UNKNOWN


def handle_upload(
    filename: str,
    file_obj: BinaryIO,
    content_type: str | None = None,
) -> Source:
    """
    Wrap a user-uploaded document as a `Source` tagged as uploaded.

    The resulting object carries an initial baseline trust score and enough
    metadata for later extraction and downstream scoring stages.
    """
    source_type = _infer_source_type(filename, content_type)
    baseline_trust = 0.75

    if source_type == SourceType.PDF:
        baseline_trust = 0.8
    elif source_type == SourceType.IMAGE:
        baseline_trust = 0.7

    return Source(
        source_id=f"upload-{uuid4().hex[:12]}",
        url=str(filename),
        source_type=source_type,
        origin=SourceOrigin.UPLOADED,
        trust_score=baseline_trust,
        title=filename,
        metadata={
            "content_type": content_type or "unknown",
            "uploaded_bytes": getattr(file_obj, "getbuffer", lambda: None)() and len(getattr(file_obj, "getbuffer", lambda: None)()),
        },
    )


def merge_sources(
    discovered: list[Source],
    uploaded: list[Source],
) -> list[Source]:
    """
    Merge discovered and uploaded sources into one evidence pool.

    Rules:
    - uploaded sources are placed first in the pool
    - any duplicate source_id or URL is collapsed to one object
    - every source is validated to remain within the schema contract
    """
    merged: list[Source] = []
    seen: set[str] = set()

    for source in [*uploaded, *discovered]:
        if not isinstance(source, Source):
            raise TypeError("merge_sources expects Source objects only")

        key = source.source_id or source.url
        if key in seen:
            continue

        seen.add(key)
        if not (0.0 <= source.trust_score <= 1.0):
            source.trust_score = max(0.0, min(1.0, source.trust_score))

        merged.append(source)

    return merged
