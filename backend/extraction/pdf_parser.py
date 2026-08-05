"""
backend/extraction/pdf_parser.py
==================================
Phase 2 — PDF Extraction using pdfplumber + PyMuPDF fallback.

Pulls structured fields (labeled key-value pairs, tables) from a datasheet PDF.
Returns list[Field] matching the schema contract.

Strategy:
  1. Try pdfplumber for text + table extraction (best for text-based PDFs).
  2. Fall back to PyMuPDF (fitz) if pdfplumber fails or yields nothing.
  3. Use Groq LLM (llama-3.3-70b) to parse raw text into structured Field objects.
  4. One Groq call per PDF (batched prompt — not per-page).

Rate-limit discipline:
  - Single Groq call per extract_pdf() invocation.
  - Text is truncated to ~6000 chars to stay within token budget.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.schema import Field, Source, SourceType

load_dotenv()
logger = logging.getLogger(__name__)

_GROQ_MODEL = "llama-3.3-70b-versatile"
_MAX_TEXT_CHARS = 6000  # truncate before sending to Groq
_PRODUCT_ID_PREFIX = "prod"


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _fetch_pdf_bytes(source: Source) -> bytes | None:
    """Download PDF bytes from URL or read from local path."""
    url = source.url
    try:
        if url.startswith("http"):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        else:
            return Path(url).read_bytes()
    except Exception as exc:
        logger.warning("Could not fetch PDF from %s: %s", url, exc)
        return None


def _extract_text_pdfplumber(pdf_bytes: bytes) -> str:
    """Extract all text from PDF using pdfplumber."""
    try:
        import pdfplumber
        text_parts: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:10]:  # cap at 10 pages
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
                # Also extract tables
                for table in page.extract_tables() or []:
                    for row in table:
                        if row:
                            text_parts.append(" | ".join(str(c) for c in row if c))
        return "\n".join(text_parts)
    except Exception as exc:
        logger.debug("pdfplumber failed: %s", exc)
        return ""


def _extract_text_pymupdf(pdf_bytes: bytes) -> str:
    """Extract text using PyMuPDF as fallback."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        parts = [doc[i].get_text() for i in range(min(10, len(doc)))]
        doc.close()
        return "\n".join(parts)
    except Exception as exc:
        logger.debug("PyMuPDF failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Groq LLM field extraction
# ---------------------------------------------------------------------------

def _parse_fields_with_groq(raw_text: str, source: Source, product_id: str) -> list[Field]:
    """Send truncated PDF text to Groq and parse returned JSON into Fields."""
    try:
        from groq import Groq
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key or api_key == "your_groq_api_key_here":
            return []
        client = Groq(api_key=api_key)
    except Exception:
        return []

    truncated = raw_text[:_MAX_TEXT_CHARS]
    system_prompt = (
        "You are a technical data extraction assistant. Extract product specification fields "
        "from the provided datasheet text. Return ONLY a JSON array of objects, each with: "
        '{"attribute": "<snake_case_name>", "value": <number_or_string>, "unit": "<unit_or_empty>", '
        '"raw_snippet": "<exact_text_fragment_max_80_chars>"}. '
        "Focus on: voltage, current, power, temperature range, dimensions, weight, frequency, "
        "speed, torque, resistance, capacitance, part number, operating conditions. "
        "Return 5-20 fields. No markdown, no explanation — pure JSON array only."
    )

    try:
        response = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Datasheet text:\n\n{truncated}"},
            ],
            temperature=0.1,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content.strip()
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        items: list[dict] = json.loads(match.group())
        fields: list[Field] = []
        for item in items:
            if not isinstance(item, dict) or "attribute" not in item:
                continue
            fields.append(Field(
                product_id=product_id,
                attribute=str(item.get("attribute", "")).strip().lower().replace(" ", "_"),
                value=item.get("value"),
                unit=str(item.get("unit", "")),
                source_id=source.source_id,
                raw_snippet=str(item.get("raw_snippet", ""))[:200],
            ))
        logger.info("[pdf_parser] Groq extracted %d fields from %s", len(fields), source.url)
        return fields
    except Exception as exc:
        logger.warning("[pdf_parser] Groq extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pdf(source: Source) -> list[Field]:
    """
    Extract structured fields from a PDF source.

    Args:
        source: a Source with source_type=PDF and a reachable URL or local path.

    Returns:
        list[Field] — may be empty if the PDF is unreachable or unreadable.
    """
    logger.info("[extract_pdf] %s", source.url)

    pdf_bytes = _fetch_pdf_bytes(source)
    if not pdf_bytes:
        logger.warning("[extract_pdf] No bytes for %s — returning empty.", source.url)
        return []

    # Try pdfplumber first, fall back to PyMuPDF
    text = _extract_text_pdfplumber(pdf_bytes)
    if len(text.strip()) < 100:
        text = _extract_text_pymupdf(pdf_bytes)

    if len(text.strip()) < 50:
        logger.warning("[extract_pdf] Extracted text too short for %s", source.url)
        return []

    # Derive a stable product_id from source_id
    product_id = f"{_PRODUCT_ID_PREFIX}-{source.source_id}"
    return _parse_fields_with_groq(text, source, product_id)
