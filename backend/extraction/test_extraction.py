"""
backend/extraction/test_extraction.py
=======================================
Phase 2 tests for the extraction module.

Run from project root with the `uni` venv active:
    python -m pytest backend/extraction/test_extraction.py -v

Tests are designed to be safe for CI:
  - Unit tests mock network/Groq calls — zero API usage.
  - Live integration tests are skipped when GROQ_API_KEY is absent.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from backend.schema import Field, Source, SourceOrigin, SourceType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_source(source_type: SourceType, url: str = "https://example.com/product") -> Source:
    return Source(
        source_id="test-src-001",
        url=url,
        source_type=source_type,
        origin=SourceOrigin.DISCOVERED,
        trust_score=0.9,
        title="Test Source",
    )


_FAKE_GROQ_FIELDS = json.dumps([
    {"attribute": "voltage_rating", "value": 24, "unit": "V", "raw_snippet": "Rated Voltage: 24 V"},
    {"attribute": "current_rating", "value": 10, "unit": "A", "raw_snippet": "Rated Current: 10 A"},
    {"attribute": "operating_temp_min", "value": -20, "unit": "°C", "raw_snippet": "Min Temp: -20°C"},
])


def _mock_groq_response(content: str) -> MagicMock:
    """Build a mock Groq response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# PDF parser unit tests
# ---------------------------------------------------------------------------

class TestPdfParser:
    def test_extract_pdf_returns_list(self):
        from backend.extraction.pdf_parser import extract_pdf
        src = _make_source(SourceType.PDF)
        with patch("backend.extraction.pdf_parser._fetch_pdf_bytes", return_value=None):
            result = extract_pdf(src)
        assert isinstance(result, list)

    def test_extract_pdf_empty_on_fetch_failure(self):
        from backend.extraction.pdf_parser import extract_pdf
        src = _make_source(SourceType.PDF)
        with patch("backend.extraction.pdf_parser._fetch_pdf_bytes", return_value=None):
            result = extract_pdf(src)
        assert result == []

    def test_extract_pdf_fields_schema_valid(self):
        from backend.extraction.pdf_parser import extract_pdf, _parse_fields_with_groq
        src = _make_source(SourceType.PDF)
        fake_bytes = b"%PDF-1.4 fake content voltage 24V current 10A"

        mock_resp = _mock_groq_response(_FAKE_GROQ_FIELDS)

        with patch("backend.extraction.pdf_parser._fetch_pdf_bytes", return_value=fake_bytes), \
             patch("backend.extraction.pdf_parser._extract_text_pdfplumber", return_value="voltage 24V current 10A weight 1.2kg"), \
             patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = extract_pdf(src)

        assert isinstance(result, list)
        for f in result:
            assert isinstance(f, Field)
            assert f.source_id == src.source_id
            assert f.attribute  # non-empty
            assert f.product_id.startswith("prod-")

    def test_extract_pdf_short_text_returns_empty(self):
        from backend.extraction.pdf_parser import extract_pdf
        src = _make_source(SourceType.PDF)
        with patch("backend.extraction.pdf_parser._fetch_pdf_bytes", return_value=b"tiny"), \
             patch("backend.extraction.pdf_parser._extract_text_pdfplumber", return_value=""), \
             patch("backend.extraction.pdf_parser._extract_text_pymupdf", return_value=""):
            result = extract_pdf(src)
        assert result == []

    def test_parse_fields_groq_no_api_key(self):
        from backend.extraction.pdf_parser import _parse_fields_with_groq
        src = _make_source(SourceType.PDF)
        original = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = ""
        try:
            result = _parse_fields_with_groq("some text", src, "prod-001")
            assert result == []
        finally:
            if original is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = original

    def test_parse_fields_handles_bad_json(self):
        from backend.extraction.pdf_parser import _parse_fields_with_groq
        src = _make_source(SourceType.PDF)
        mock_resp = _mock_groq_response("not valid json at all")
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = _parse_fields_with_groq("some text", src, "prod-001")
        assert isinstance(result, list)

    def test_pdfplumber_text_extraction(self):
        """_extract_text_pdfplumber returns a string (even if empty for fake bytes)."""
        from backend.extraction.pdf_parser import _extract_text_pdfplumber
        result = _extract_text_pdfplumber(b"not a real pdf")
        assert isinstance(result, str)

    def test_pymupdf_text_extraction(self):
        """_extract_text_pymupdf returns a string (even if empty for fake bytes)."""
        from backend.extraction.pdf_parser import _extract_text_pymupdf
        result = _extract_text_pymupdf(b"not a real pdf")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# HTML parser unit tests
# ---------------------------------------------------------------------------

class TestHtmlParser:
    def test_extract_html_returns_list(self):
        from backend.extraction.html_parser import extract_html
        src = _make_source(SourceType.HTML)
        with patch("backend.extraction.html_parser._fetch_html", return_value=""):
            result = extract_html(src)
        assert isinstance(result, list)

    def test_extract_html_empty_on_fetch_failure(self):
        from backend.extraction.html_parser import extract_html
        src = _make_source(SourceType.HTML)
        with patch("backend.extraction.html_parser._fetch_html", return_value=""):
            result = extract_html(src)
        assert result == []

    def test_clean_html_extracts_table_text(self):
        from backend.extraction.html_parser import _clean_html
        html = """
        <html><body>
        <table><tr><th>Voltage</th><td>24 V</td></tr>
        <tr><th>Current</th><td>10 A</td></tr></table>
        </body></html>
        """
        result = _clean_html(html)
        assert "24" in result
        assert "Voltage" in result

    def test_clean_html_strips_script_tags(self):
        from backend.extraction.html_parser import _clean_html
        html = "<html><body><script>alert('x')</script><p>Voltage: 24V</p></body></html>"
        result = _clean_html(html)
        assert "alert" not in result
        assert "24V" in result

    def test_clean_html_extracts_dl_pairs(self):
        from backend.extraction.html_parser import _clean_html
        html = """
        <html><body>
        <dl><dt>Voltage</dt><dd>24 V</dd><dt>Current</dt><dd>10 A</dd></dl>
        </body></html>
        """
        result = _clean_html(html)
        assert "Voltage" in result
        assert "24 V" in result

    def test_extract_html_fields_schema_valid(self):
        from backend.extraction.html_parser import extract_html
        src = _make_source(SourceType.HTML)
        fake_html = "<html><body><table><tr><td>Voltage</td><td>24V</td></tr></table></body></html>"
        mock_resp = _mock_groq_response(_FAKE_GROQ_FIELDS)

        with patch("backend.extraction.html_parser._fetch_html", return_value=fake_html), \
             patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = extract_html(src)

        assert isinstance(result, list)
        for f in result:
            assert isinstance(f, Field)
            assert f.source_id == src.source_id
            assert f.product_id.startswith("prod-")

    def test_parse_fields_no_api_key(self):
        from backend.extraction.html_parser import _parse_fields_with_groq
        src = _make_source(SourceType.HTML)
        original = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = ""
        try:
            result = _parse_fields_with_groq("some text", src, "prod-001")
            assert result == []
        finally:
            if original is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = original


# ---------------------------------------------------------------------------
# Image extractor unit tests
# ---------------------------------------------------------------------------

class TestImageExtractor:
    def test_extract_image_returns_list(self):
        from backend.extraction.image_extractor import extract_image
        src = _make_source(SourceType.IMAGE, "https://example.com/nameplate.jpg")
        with patch("backend.extraction.image_extractor._fetch_image_bytes", return_value=None):
            result = extract_image(src)
        assert isinstance(result, list)

    def test_extract_image_empty_on_fetch_failure(self):
        from backend.extraction.image_extractor import extract_image
        src = _make_source(SourceType.IMAGE, "https://example.com/nameplate.jpg")
        with patch("backend.extraction.image_extractor._fetch_image_bytes", return_value=None):
            result = extract_image(src)
        assert result == []

    def test_to_base64_data_url_jpeg(self):
        from backend.extraction.image_extractor import _to_base64_data_url
        url = _to_base64_data_url(b"\xff\xd8\xff", "https://example.com/photo.jpg")
        assert url.startswith("data:image/jpeg;base64,")

    def test_to_base64_data_url_png(self):
        from backend.extraction.image_extractor import _to_base64_data_url
        url = _to_base64_data_url(b"\x89PNG", "https://example.com/photo.png")
        assert url.startswith("data:image/png;base64,")

    def test_to_base64_data_url_webp(self):
        from backend.extraction.image_extractor import _to_base64_data_url
        url = _to_base64_data_url(b"RIFF", "https://example.com/photo.webp")
        assert url.startswith("data:image/webp;base64,")

    def test_extract_image_fields_schema_valid(self):
        from backend.extraction.image_extractor import extract_image
        src = _make_source(SourceType.IMAGE, "https://example.com/nameplate.jpg")
        fake_bytes = b"\xff\xd8\xff fake jpeg"
        mock_resp = _mock_groq_response(_FAKE_GROQ_FIELDS)

        with patch("backend.extraction.image_extractor._fetch_image_bytes", return_value=fake_bytes), \
             patch("backend.extraction.image_extractor._resize_image", return_value=fake_bytes), \
             patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = extract_image(src)

        assert isinstance(result, list)
        for f in result:
            assert isinstance(f, Field)
            assert f.source_id == src.source_id
            assert f.product_id.startswith("prod-")

    def test_extract_image_no_api_key(self):
        from backend.extraction.image_extractor import _extract_with_groq_vision
        src = _make_source(SourceType.IMAGE)
        original = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = ""
        try:
            result = _extract_with_groq_vision("data:image/jpeg;base64,abc", src, "prod-001")
            assert result == []
        finally:
            if original is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = original


# ---------------------------------------------------------------------------
# Cross-module: __init__ exports correct functions
# ---------------------------------------------------------------------------

class TestExtractionPublicInterface:
    def test_extract_pdf_importable(self):
        from backend.extraction import extract_pdf
        assert callable(extract_pdf)

    def test_extract_html_importable(self):
        from backend.extraction import extract_html
        assert callable(extract_html)

    def test_extract_image_importable(self):
        from backend.extraction import extract_image
        assert callable(extract_image)

    def test_all_return_list_on_empty_input(self):
        from backend.extraction import extract_pdf, extract_html, extract_image
        src_pdf = _make_source(SourceType.PDF)
        src_html = _make_source(SourceType.HTML)
        src_img = _make_source(SourceType.IMAGE, "https://example.com/img.jpg")

        with patch("backend.extraction.pdf_parser._fetch_pdf_bytes", return_value=None), \
             patch("backend.extraction.html_parser._fetch_html", return_value=""), \
             patch("backend.extraction.image_extractor._fetch_image_bytes", return_value=None):
            assert isinstance(extract_pdf(src_pdf), list)
            assert isinstance(extract_html(src_html), list)
            assert isinstance(extract_image(src_img), list)


# ---------------------------------------------------------------------------
# Live integration tests (require GROQ_API_KEY + network)
# ---------------------------------------------------------------------------

_has_groq = (
    bool(os.environ.get("GROQ_API_KEY")) and
    os.environ.get("GROQ_API_KEY") != "your_groq_api_key_here"
)


@pytest.mark.skipif(not _has_groq, reason="GROQ_API_KEY not set — skipping live extraction tests.")
class TestExtractionLive:
    """
    Live tests against the EnduraMax 75s catalog sources.
    These consume Groq API quota — run sparingly.
    """

    def _enduramax_pdf_source(self) -> Source:
        # TI LM2596 datasheet — reliably accessible, good spec content
        return Source(
            source_id="cat-lm2596-pdf",
            url="https://www.ti.com/lit/ds/symlink/lm2596.pdf",
            source_type=SourceType.PDF,
            origin=SourceOrigin.DISCOVERED,
            trust_score=0.98,
            title="LM2596 Datasheet — Texas Instruments",
        )

    def _enduramax_html_source(self) -> Source:
        return Source(
            source_id="cat-lm2596-html",
            url="https://www.ti.com/product/LM2596",
            source_type=SourceType.HTML,
            origin=SourceOrigin.DISCOVERED,
            trust_score=0.95,
            title="LM2596 Product Page — Texas Instruments",
        )

    def test_pdf_extraction_returns_fields(self):
        from backend.extraction import extract_pdf
        fields = extract_pdf(self._enduramax_pdf_source())
        assert isinstance(fields, list)
        assert len(fields) >= 3, f"Expected ≥3 fields from PDF, got {len(fields)}"

    def test_pdf_fields_schema_valid(self):
        from backend.extraction import extract_pdf
        fields = extract_pdf(self._enduramax_pdf_source())
        for f in fields:
            assert isinstance(f, Field)
            assert f.attribute
            assert f.source_id == "cat-lm2596-pdf"
            assert f.product_id.startswith("prod-")

    def test_html_extraction_returns_fields(self):
        from backend.extraction import extract_html
        fields = extract_html(self._enduramax_html_source())
        assert isinstance(fields, list)
        assert len(fields) >= 2, f"Expected ≥2 fields from HTML, got {len(fields)}"

    def test_html_fields_schema_valid(self):
        from backend.extraction import extract_html
        fields = extract_html(self._enduramax_html_source())
        for f in fields:
            assert isinstance(f, Field)
            assert f.attribute
            assert f.source_id == "cat-lm2596-html"

    def test_pdf_and_html_share_common_attributes(self):
        """Both sources should surface at least one overlapping attribute (for reconciliation)."""
        from backend.extraction import extract_pdf, extract_html
        pdf_fields = extract_pdf(self._enduramax_pdf_source())
        html_fields = extract_html(self._enduramax_html_source())
        pdf_attrs = {f.attribute for f in pdf_fields}
        html_attrs = {f.attribute for f in html_fields}
        overlap = pdf_attrs & html_attrs
        assert len(overlap) >= 1, (
            f"Expected ≥1 overlapping attribute between PDF and HTML. "
            f"PDF: {pdf_attrs}, HTML: {html_attrs}"
        )
