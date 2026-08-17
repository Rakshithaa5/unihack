"""
backend/extraction/image_extractor.py
=======================================
Phase 2 — Image/Diagram Extraction using Groq Vision (Llama 3.2 Vision 11B).

Extracts fields from product images, nameplates, and spec diagrams that
text-based parsers cannot reach.

Strategy:
  1. Fetch image bytes from URL or local path.
  2. Base64-encode and send to Groq Vision with a structured extraction prompt.
  3. Parse the JSON response into Field objects.
  4. One Groq Vision call per image.

Rate-limit discipline:
  - Single Groq Vision call per extract_image() invocation.
  - Images are resized to ≤1024px on the longest side before encoding
    to reduce token usage (Pillow resize, optional — skipped if Pillow absent).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from backend.schema import Field, Source

load_dotenv()
logger = logging.getLogger(__name__)

_GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"
_MAX_IMAGE_DIM = 1024  # resize longest side to this (reduces tokens)
_PRODUCT_ID_PREFIX = "prod"


# ---------------------------------------------------------------------------
# Image fetch + encode
# ---------------------------------------------------------------------------

def _fetch_image_bytes(source: Source) -> bytes | None:
    """Fetch image bytes from URL or local path."""
    url = source.url
    try:
        if url.startswith("http"):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        else:
            return Path(url).read_bytes()
    except Exception as exc:
        logger.warning("[image_extractor] Fetch failed for %s: %s", url, exc)
        return None


def _resize_image(img_bytes: bytes) -> bytes:
    """Resize image to max _MAX_IMAGE_DIM on longest side. Returns original if Pillow absent."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        if max(w, h) > _MAX_IMAGE_DIM:
            scale = _MAX_IMAGE_DIM / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        fmt = img.format or "JPEG"
        img.save(buf, format=fmt)
        return buf.getvalue()
    except Exception:
        return img_bytes


def _to_base64_data_url(img_bytes: bytes, url: str) -> str:
    """Convert image bytes to a base64 data URL."""
    # Infer MIME type from URL extension
    url_lower = url.lower()
    if url_lower.endswith(".png"):
        mime = "image/png"
    elif url_lower.endswith(".webp"):
        mime = "image/webp"
    elif url_lower.endswith(".gif"):
        mime = "image/gif"
    else:
        mime = "image/jpeg"
    encoded = base64.b64encode(img_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


# ---------------------------------------------------------------------------
# Groq Vision extraction
# ---------------------------------------------------------------------------

def _extract_with_groq_vision(data_url: str, source: Source, product_id: str) -> list[Field]:
    """Call Groq Vision and parse the response into Fields."""
    try:
        from groq import Groq
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key or api_key == "your_groq_api_key_here":
            return []
        client = Groq(api_key=api_key)
    except Exception:
        return []

    prompt = (
        "This is a product image, nameplate, or specification diagram. "
        "Extract all visible technical specifications, part numbers, ratings, and labels. "
        "Return ONLY a JSON array of objects, each with: "
        '{"attribute": "<snake_case_name>", "value": <number_or_string>, "unit": "<unit_or_empty>", '
        '"raw_snippet": "<exact_text_seen_in_image_max_80_chars>"}. '
        "Examples: part_number, voltage_rating, current_rating, serial_number, manufacturer, "
        "model_number, power_rating, frequency, operating_temp. "
        "Return only what is clearly visible. No markdown — pure JSON array only."
    )

    try:
        response = client.chat.completions.create(
            model=_GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=1000,
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
        logger.info("[image_extractor] Groq Vision extracted %d fields from %s", len(fields), source.url)
        return fields
    except Exception as exc:
        logger.warning("[image_extractor] Groq Vision failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_image(source: Source) -> list[Field]:
    """
    Extract structured fields from an image source using Groq Vision.

    Args:
        source: a Source with source_type=IMAGE and a reachable URL or local path.

    Returns:
        list[Field] — may be empty if the image is unreachable or contains no text.
    """
    logger.info("[extract_image] %s", source.url)

    img_bytes = _fetch_image_bytes(source)
    if not img_bytes:
        return []

    img_bytes = _resize_image(img_bytes)
    data_url = _to_base64_data_url(img_bytes, source.url)
    product_id = f"{_PRODUCT_ID_PREFIX}-{source.source_id}"
    return _extract_with_groq_vision(data_url, source, product_id)
