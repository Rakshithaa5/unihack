"""
backend/extraction/stub.py — Phase 0.5 stub
============================================
Returns hardcoded Field objects that match the Phase 0 schema exactly.
Swap out for real implementations in Phase 2.
"""

from __future__ import annotations

from backend.schema import Field, Source


def extract_pdf(source: Source) -> list[Field]:
    """
    STUB: returns 3 made-up fields as if parsed from a PDF.
    Real implementation (Phase 2) will use pdfplumber / PyMuPDF.
    """
    print(f"[STUB] extract_pdf: {source.url}")
    return [
        Field(
            product_id="STUB-PRODUCT-001",
            attribute="voltage_rating",
            value=24,
            unit="V",
            source_id=source.source_id,
            raw_snippet="Rated Voltage: 24 V (stub)",
        ),
        Field(
            product_id="STUB-PRODUCT-001",
            attribute="current_rating",
            value=10,
            unit="A",
            source_id=source.source_id,
            raw_snippet="Rated Current: 10 A (stub)",
        ),
        Field(
            product_id="STUB-PRODUCT-001",
            attribute="weight",
            value=1.2,
            unit="kg",
            source_id=source.source_id,
            raw_snippet="Net Weight: 1.2 kg (stub)",
        ),
    ]


def extract_html(source: Source) -> list[Field]:
    """
    STUB: returns 3 made-up fields as if scraped from an HTML page.
    Real implementation (Phase 2) will use BeautifulSoup.
    """
    print(f"[STUB] extract_html: {source.url}")
    return [
        Field(
            product_id="STUB-PRODUCT-001",
            attribute="voltage_rating",
            value=24,
            unit="V",
            source_id=source.source_id,
            raw_snippet="Voltage: 24V (stub)",
        ),
        Field(
            product_id="STUB-PRODUCT-001",
            attribute="operating_temp_min",
            value=-20,
            unit="°C",
            source_id=source.source_id,
            raw_snippet="Min Temp: -20°C (stub)",
        ),
        Field(
            product_id="STUB-PRODUCT-001",
            attribute="operating_temp_max",
            value=85,
            unit="°C",
            source_id=source.source_id,
            raw_snippet="Max Temp: 85°C (stub)",
        ),
    ]


def extract_image(source: Source) -> list[Field]:
    """
    STUB: returns 2 made-up fields as if extracted by the VLM.
    Real implementation (Phase 2) will call Groq Vision (Llama 3.2 Vision).
    """
    print(f"[STUB] extract_image: {source.url}")
    return [
        Field(
            product_id="STUB-PRODUCT-001",
            attribute="part_number_visible",
            value="MPN-STUB-001",
            unit="",
            source_id=source.source_id,
            raw_snippet="Nameplate text (stub)",
        ),
        Field(
            product_id="STUB-PRODUCT-001",
            attribute="manufacturer_logo_present",
            value=True,
            unit="",
            source_id=source.source_id,
            raw_snippet="Logo detected in top-left (stub)",
        ),
    ]
