"""
backend/extraction/html_parser.py
===================================
Phase 2 — HTML Extraction using BeautifulSoup + Groq LLM.

Pulls product specification fields from a distributor/manufacturer webpage.
Returns list[Field] matching the schema contract.

Strategy:
  1. Fetch HTML with requests (with User-Agent spoofing).
  2. BeautifulSoup strips boilerplate; targets spec tables, dl/dt/dd, and
     structured divs that typically hold product attributes.
  3. Groq LLM parses the cleaned text into structured Field objects.
  4. One Groq call per HTML page.

Rate-limit discipline:
  - Single Groq call per extract_html() invocation.
  - HTML is cleaned and truncated to ~5000 chars before sending.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from backend.schema import Field, Source

load_dotenv()
logger = logging.getLogger(__name__)

_GROQ_MODEL = "llama-3.3-70b-versatile"
_MAX_TEXT_CHARS = 5000
_PRODUCT_ID_PREFIX = "prod"

# Tags that typically contain spec data on product pages
_SPEC_TAGS = {"table", "dl", "ul", "ol", "div", "section", "article"}
_SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "form"}


# ---------------------------------------------------------------------------
# HTML fetch + clean
# ---------------------------------------------------------------------------

def _fetch_html(url: str) -> str:
    """Fetch HTML from URL or local file path."""
    try:
        if url.startswith("http"):
            import urllib.request
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ProvenIQ/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                # Detect encoding
                charset = "utf-8"
                ct = resp.headers.get("Content-Type", "")
                m = re.search(r"charset=([^\s;]+)", ct)
                if m:
                    charset = m.group(1)
                return raw.decode(charset, errors="replace")
        else:
            return Path(url).read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("[html_parser] Fetch failed for %s: %s", url, exc)
        return ""


def _clean_html(html: str) -> str:
    """
    Use BeautifulSoup to extract spec-relevant text, stripping boilerplate.
    Prioritises tables, definition lists, and spec sections.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 not installed")
        return html[:_MAX_TEXT_CHARS]

    soup = BeautifulSoup(html, "html.parser")

    # Remove noise tags entirely
    for tag in soup(_SKIP_TAGS):
        tag.decompose()

    # Try to find spec-specific containers first
    spec_texts: list[str] = []

    # 1. Tables (most reliable for spec data)
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            spec_texts.append("\n".join(rows))

    # 2. Definition lists
    for dl in soup.find_all("dl"):
        pairs = []
        terms = dl.find_all("dt")
        defs = dl.find_all("dd")
        for dt, dd in zip(terms, defs):
            pairs.append(f"{dt.get_text(strip=True)}: {dd.get_text(strip=True)}")
        if pairs:
            spec_texts.append("\n".join(pairs))

    # 3. Fall back to full body text if spec containers are sparse
    combined = "\n\n".join(spec_texts)
    if len(combined) < 300:
        combined = soup.get_text(separator="\n", strip=True)

    # Collapse excessive whitespace
    combined = re.sub(r"\n{3,}", "\n\n", combined)
    return combined[:_MAX_TEXT_CHARS]


# ---------------------------------------------------------------------------
# Groq LLM field extraction
# ---------------------------------------------------------------------------

def _parse_fields_with_groq(clean_text: str, source: Source, product_id: str) -> list[Field]:
    """Send cleaned HTML text to Groq and parse returned JSON into Fields."""
    try:
        from groq import Groq
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key or api_key == "your_groq_api_key_here":
            return []
        client = Groq(api_key=api_key)
    except Exception:
        return []

    system_prompt = (
        "You are a technical data extraction assistant. Extract product specification fields "
        "from the provided product webpage text. Return ONLY a JSON array of objects, each with: "
        '{"attribute": "<snake_case_name>", "value": <number_or_string>, "unit": "<unit_or_empty>", '
        '"raw_snippet": "<exact_text_fragment_max_80_chars>"}. '
        "Focus on: voltage, current, power, temperature range, dimensions, weight, frequency, "
        "speed, torque, resistance, part number, operating conditions, package type. "
        "Return 5-20 fields. No markdown, no explanation — pure JSON array only."
    )

    try:
        response = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Product page text:\n\n{clean_text}"},
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
        logger.info("[html_parser] Groq extracted %d fields from %s", len(fields), source.url)
        return fields
    except Exception as exc:
        logger.warning("[html_parser] Groq extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_html(source: Source) -> list[Field]:
    """
    Extract structured fields from an HTML source.

    Args:
        source: a Source with source_type=HTML and a reachable URL or local path.

    Returns:
        list[Field] — may be empty if the page is unreachable or has no spec data.
    """
    logger.info("[extract_html] %s", source.url)

    html = _fetch_html(source.url)
    if not html:
        return []

    clean_text = _clean_html(html)
    if len(clean_text.strip()) < 50:
        logger.warning("[extract_html] Cleaned text too short for %s", source.url)
        return []

    product_id = f"{_PRODUCT_ID_PREFIX}-{source.source_id}"
    return _parse_fields_with_groq(clean_text, source, product_id)
