"""
backend/batch/stub.py — Phase 0.5 stub
=======================================
Runs the pipeline stub over a list of product inputs and returns a report dict.
Swap out for real batch runner in Phase 5.
"""

from __future__ import annotations


def run_batch(products: list[dict]) -> dict:
    """
    STUB: echoes each product back with placeholder pipeline results.
    Real implementation (Phase 5) will loop the real pipeline.py chain and
    compute conflict_rate, enrichment_rate, and hitl_flag_rate.

    Args:
        products: list of dicts, each with keys: mpn, brand, description
    Returns:
        dict with keys: total, results, conflict_rate, enrichment_rate, hitl_flag_rate
    """
    print(f"[STUB] run_batch: {len(products)} products")
    results = [
        {
            "mpn": p.get("mpn"),
            "brand": p.get("brand"),
            "status": "stub_complete",
            "fields_extracted": 0,
            "conflicts": 0,
            "enriched": 0,
            "hitl_flagged": 0,
        }
        for p in products
    ]
    return {
        "total": len(products),
        "results": results,
        "conflict_rate": 0.0,
        "enrichment_rate": 0.0,
        "hitl_flag_rate": 0.0,
    }
