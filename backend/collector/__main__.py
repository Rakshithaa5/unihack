from __future__ import annotations

import io

from backend.collector import handle_upload, merge_sources
from backend.schema import Source, SourceOrigin, SourceType


def main() -> None:
    discovered = [
        Source(
            source_id="disc-demo-1",
            url="https://example.com/manufacturer/datasheet.pdf",
            source_type=SourceType.PDF,
            origin=SourceOrigin.DISCOVERED,
            trust_score=0.92,
            title="Manufacturer datasheet",
        )
    ]

    uploaded = [
        handle_upload(
            filename="manual.pdf",
            file_obj=io.BytesIO(b"%PDF-1.4 demo upload"),
            content_type="application/pdf",
        )
    ]

    merged = merge_sources(discovered, uploaded)
    print(f"Evidence pool size: {len(merged)}")
    for idx, source in enumerate(merged, start=1):
        print(f"{idx}. {source.origin.value} | {source.source_type.value} | {source.title} | trust={source.trust_score:.2f}")


if __name__ == "__main__":
    main()
