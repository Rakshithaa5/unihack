"""
backend/enrichment/agent.py
============================
Phase 3 — RAG Enrichment Agent

Public surface:
    enrich(missing_field: Field, corpus) -> ResolvedField | None

Strategy:
  1. Build (or load) a Chroma collection embedded with sentence-transformers
     all-MiniLM-L6-v2 (local, zero API cost, zero rate limit).
  2. Given a missing field, embed the attribute name as a query and retrieve
     the top-k most relevant text chunks from the corpus.
  3. Send the retrieved chunks to Groq LLM (llama-3.3-70b) with a targeted
     extraction prompt.
  4. If the LLM finds the value, return a ResolvedField with status=ENRICHED
     and a citation to the source chunk.  Return None if nothing is found.

Corpus format:
    A list of dicts, each with keys:
        text       — the chunk text
        source_id  — Source.source_id this chunk came from
        attribute  — optional hint (may be empty)
    Pass corpus=None to use the default catalog-derived corpus built from
    data/reference_catalog.json text snippets.

Rate-limit discipline:
  - Embeddings: fully local, no API calls.
  - Chroma: local embedded mode, no hosted service.
  - Groq: one call per enrich() invocation.
  - Collection is built once per process and reused (module-level singleton).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.schema import Field, FieldStatus, ResolvedField

load_dotenv()
logger = logging.getLogger(__name__)

_GROQ_MODEL = "llama-3.3-70b-versatile"
_EMBED_MODEL = "all-MiniLM-L6-v2"
_TOP_K = 5
_COLLECTION_NAME = "proveniq_enrichment"
_CATALOG_PATH = Path(__file__).parents[2] / "data" / "reference_catalog.json"

# Module-level singletons — built once, reused across calls.
_chroma_client: Any = None
_collection: Any = None
_embed_fn: Any = None


# ---------------------------------------------------------------------------
# Embedding function wrapper for Chroma
# ---------------------------------------------------------------------------

class _SentenceTransformerEmbedding:
    """
    Wraps sentence-transformers for use as a Chroma embedding function.
    Implements the full interface required by Chroma >= 1.0.
    """

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)

    def name(self) -> str:
        return f"sentence-transformers/{self._model_name}"

    def is_legacy(self) -> bool:
        return False

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_numpy=True).tolist()

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self._encode(input)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str = "", **kwargs: object) -> list[float]:
        # Chroma 1.5.x calls embed_query(input=<str>) as a keyword argument
        actual = kwargs.get("input", text)
        return self._encode([str(actual)])[0]


# ---------------------------------------------------------------------------
# Corpus helpers
# ---------------------------------------------------------------------------

def _build_default_corpus() -> list[dict]:
    """
    Build a text corpus from the reference catalog JSON.
    Each catalog source entry becomes one chunk with its title + description.
    """
    if not _CATALOG_PATH.exists():
        logger.warning("[enrichment] Catalog not found at %s — corpus will be empty.", _CATALOG_PATH)
        return []

    try:
        with _CATALOG_PATH.open("r", encoding="utf-8") as f:
            catalog: list[dict] = json.load(f)
    except Exception as exc:
        logger.error("[enrichment] Failed to load catalog: %s", exc)
        return []

    chunks: list[dict] = []
    for product in catalog:
        mpn = product.get("mpn", "")
        brand = product.get("brand", "")
        description = product.get("description", "")
        base_text = f"Product: {brand} {mpn}. {description}."

        for source in product.get("sources", []):
            title = source.get("title", "")
            url = source.get("url", "")
            source_id = "cat-" + __import__("hashlib").sha1(url.encode()).hexdigest()[:12]
            chunk_text = f"{base_text} Source: {title}. URL: {url}."
            chunks.append({
                "text": chunk_text,
                "source_id": source_id,
                "attribute": "",
                "url": url,
                "title": title,
            })

    logger.info("[enrichment] Built default corpus: %d chunks from catalog.", len(chunks))
    return chunks


# ---------------------------------------------------------------------------
# Chroma collection management
# ---------------------------------------------------------------------------

def _get_embed_fn() -> _SentenceTransformerEmbedding:
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = _SentenceTransformerEmbedding(_EMBED_MODEL)
    return _embed_fn


def _get_collection(corpus: list[dict] | None = None) -> Any:
    """
    Return the Chroma collection, building it from corpus if not yet initialised.
    Thread-safety is not required for the hackathon single-process use case.
    """
    global _chroma_client, _collection

    if _collection is not None:
        return _collection

    try:
        import chromadb
    except ImportError:
        logger.error("[enrichment] chromadb not installed — enrichment disabled.")
        return None

    _chroma_client = chromadb.Client()  # in-memory embedded mode

    embed_fn = _get_embed_fn()

    chunks = corpus if corpus is not None else _build_default_corpus()
    if not chunks:
        logger.warning("[enrichment] Empty corpus — enrichment will always return None.")
        return None

    _collection = _chroma_client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=embed_fn,
    )

    # Only populate if the collection is empty (freshly created)
    if _collection.count() == 0:

        # Batch-add all chunks
        ids = [f"chunk-{i}" for i in range(len(chunks))]
        texts = [c["text"] for c in chunks]
        metadatas = [
            {
                "source_id": c.get("source_id", ""),
                "attribute": c.get("attribute", ""),
                "url": c.get("url", ""),
                "title": c.get("title", ""),
            }
            for c in chunks
        ]
        _collection.add(documents=texts, ids=ids, metadatas=metadatas)
        logger.info("[enrichment] Built Chroma collection with %d chunks.", len(chunks))
    else:
        logger.info("[enrichment] Reusing existing Chroma collection (%d chunks).", _collection.count())
    return _collection


def reset_collection() -> None:
    """Force rebuild of the Chroma collection on next call (useful for tests)."""
    global _chroma_client, _collection
    if _chroma_client is not None:
        try:
            _chroma_client.delete_collection(_COLLECTION_NAME)
        except Exception:
            pass
    _chroma_client = None
    _collection = None


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _retrieve(attribute: str, collection: Any, top_k: int = _TOP_K) -> list[dict]:
    """
    Embed the attribute name and retrieve the top-k most relevant chunks.
    Returns list of dicts with keys: text, source_id, url, title.
    """
    try:
        embed_fn = _get_embed_fn()
        query_embedding = embed_fn._encode([attribute])[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("[enrichment] Chroma query failed: %s", exc)
        return []

    chunks: list[dict] = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    for doc, meta in zip(docs, metas):
        chunks.append({
            "text": doc,
            "source_id": meta.get("source_id", ""),
            "url": meta.get("url", ""),
            "title": meta.get("title", ""),
        })
    return chunks


# ---------------------------------------------------------------------------
# Groq LLM extraction from retrieved chunks
# ---------------------------------------------------------------------------

def _extract_with_groq(
    attribute: str,
    chunks: list[dict],
    missing_field: Field,
) -> tuple[Any, str, str, str] | None:
    """
    Ask Groq LLM to extract the attribute value from the retrieved chunks.

    Returns (value, unit, raw_snippet, source_id) or None if not found.
    """
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here":
        return None

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
    except Exception:
        return None

    context = "\n\n".join(
        f"[Source {i+1} | id={c['source_id']}]\n{c['text']}"
        for i, c in enumerate(chunks)
    )

    system_prompt = (
        "You are a technical data extraction assistant. "
        "Given retrieved product documentation chunks, extract the value for the requested attribute. "
        "Return ONLY a JSON object with keys: "
        '{"value": <number_or_string_or_null>, "unit": "<unit_or_empty>", '
        '"raw_snippet": "<exact_text_fragment_max_80_chars>", "source_id": "<source_id_from_context>"}. '
        'If the attribute is not present in any chunk, return {"value": null}. '
        "No markdown, no explanation — pure JSON only."
    )
    user_prompt = (
        f"Attribute to find: {attribute}\n"
        f"Product context: {missing_field.product_id}\n\n"
        f"Retrieved chunks:\n{context}"
    )

    try:
        response = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        data: dict = json.loads(match.group())
        if data.get("value") is None:
            return None
        # Find the best matching source_id from retrieved chunks
        returned_sid = str(data.get("source_id", ""))
        source_id = returned_sid if any(c["source_id"] == returned_sid for c in chunks) \
            else (chunks[0]["source_id"] if chunks else "")
        return (
            data["value"],
            str(data.get("unit", "")),
            str(data.get("raw_snippet", ""))[:200],
            source_id,
        )
    except Exception as exc:
        logger.warning("[enrichment] Groq extraction failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich(missing_field: Field, corpus: list[dict] | None = None) -> ResolvedField | None:
    """
    Attempt to enrich a missing or low-confidence field via RAG.

    Args:
        missing_field: a Field whose value is None or needs enrichment.
        corpus:        optional list of chunk dicts to index; uses the default
                       catalog-derived corpus when None.

    Returns:
        ResolvedField with status=ENRICHED and a source citation, or None if
        the attribute could not be found in the corpus.
    """
    attribute = missing_field.attribute
    logger.info("[enrich] Attempting enrichment for attribute=%r", attribute)

    collection = _get_collection(corpus)
    if collection is None:
        logger.warning("[enrich] No Chroma collection available — skipping.")
        return None

    chunks = _retrieve(attribute, collection)
    if not chunks:
        logger.info("[enrich] No relevant chunks found for %r.", attribute)
        return None

    result = _extract_with_groq(attribute, chunks, missing_field)
    if result is None:
        logger.info("[enrich] Groq could not extract %r from retrieved chunks.", attribute)
        return None

    value, unit, raw_snippet, source_id = result
    reasoning = (
        f"Enriched via RAG: retrieved {len(chunks)} relevant chunk(s) from the corpus "
        f"and extracted '{value} {unit}'.strip() from source {source_id!r}."
    ).strip()

    logger.info("[enrich] Enriched %r = %r %s (source=%s)", attribute, value, unit, source_id)
    return ResolvedField(
        product_id=missing_field.product_id,
        attribute=attribute,
        value=value,
        unit=unit,
        source_id=source_id,
        raw_snippet=raw_snippet,
        confidence=0.65,  # enriched fields carry moderate confidence by default
        status=FieldStatus.ENRICHED,
        reasoning=reasoning,
        alternate_values=[],
    )
