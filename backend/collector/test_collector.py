from __future__ import annotations

import io

from backend.collector import handle_upload, merge_sources
from backend.schema import Source, SourceOrigin, SourceType


def test_merge_sources_returns_well_formed_evidence_pool() -> None:
    discovered = [
        Source(
            source_id="disc-1",
            url="https://example.com/datasheet.pdf",
            source_type=SourceType.PDF,
            origin=SourceOrigin.DISCOVERED,
            trust_score=0.92,
            title="Manufacturer datasheet",
        )
    ]
    uploaded = [
        Source(
            source_id="upload-1",
            url="/tmp/uploaded-manual.txt",
            source_type=SourceType.UNKNOWN,
            origin=SourceOrigin.UPLOADED,
            trust_score=0.75,
            title="User manual upload",
        )
    ]

    merged = merge_sources(discovered, uploaded)

    assert len(merged) == 2
    assert {source.origin for source in merged} == {SourceOrigin.DISCOVERED, SourceOrigin.UPLOADED}
    assert all(isinstance(source, Source) for source in merged)
    assert all(0.0 <= source.trust_score <= 1.0 for source in merged)
    assert len({source.source_id for source in merged}) == 2


def test_handle_upload_wraps_files_as_uploaded_sources() -> None:
    source = handle_upload(
        filename="datasheet.pdf",
        file_obj=io.BytesIO(b"%PDF-1.4 fake pdf content"),
        content_type="application/pdf",
    )

    assert isinstance(source, Source)
    assert source.origin == SourceOrigin.UPLOADED
    assert source.source_type == SourceType.PDF
    assert source.source_id.startswith("upload-")
    assert 0.0 <= source.trust_score <= 1.0
    assert source.title == "datasheet.pdf"
