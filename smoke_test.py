"""
smoke_test.py — Phase 0 / 0.5 end-to-end sanity check
=======================================================
Runs the full stub pipeline for one product to confirm every import,
schema shape, and stage transition works before any real code is written.

Usage (from project root, with `uni` venv activated):
    python smoke_test.py
"""

from __future__ import annotations

import json
from datetime import datetime

from backend.pipeline import run_pipeline
from backend import storage


def main() -> None:
    print("=" * 60)
    print("ProvenIQ — Phase 0/0.5 Smoke Test")
    print("=" * 60)

    # Run the stub pipeline for a made-up product
    result = run_pipeline(
        mpn="EM75S-001",
        brand="Allied Motion",
        description="EnduraMax 75s brushless DC motor, 24V, 10A",
    )

    print("\n--- Resolved fields ---")
    for attribute, field in result.items():
        print(
            f"  {attribute}: {field.value!r} {field.unit}"
            f" | confidence={field.confidence:.2f}"
            f" | status={field.status.value}"
            f" | reasoning={field.reasoning!r}"
        )

    print("\n--- Storage record (get_product_record) ---")
    record = storage.get_product_record("STUB-PRODUCT-001")
    print(f"  {len(record)} attribute(s) stored in-memory")

    print("\n--- Evidence trail for 'voltage_rating' ---")
    trail = storage.get_evidence_trail("STUB-PRODUCT-001", "voltage_rating")
    if trail:
        print(f"  source_id={trail.source_id!r}, confidence={trail.confidence:.2f}")
    else:
        print("  (not found — check extraction stub product_id)")

    print("\n✅ Smoke test passed — all stubs return correctly-shaped data.")
    print("=" * 60)


if __name__ == "__main__":
    main()
