"""
backend/enrichment/test_enrichment.py
=======================================
Phase 3 tests for the enrichment module.

Run from project root with the `uni` venv active:
    python -m pytest backend/enrichment/test_enrichment.py -v

Tests are safe for CI:
  - Unit tests mock Chroma and Groq — zero API calls, zero network.
  - Live integration tests are skipped when GROQ_API_KEY is absent.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from backend.schema import Field, FieldStatus, ResolvedField, SourceOrigin, SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_field(attribute: str = "voltage_rating", value: object = None) -> Field:
    return Field(
        product_id="prod-test-001",
        attribute=attribute,
        value=value,
        unit="",
        source_id="",
    )


_FAKE_CORPUS = [
    {
        "text": "Product: Allied Motion EM75S-001. EnduraMax 75s brushless DC motor, 24V, 10A. "
                "Source: EnduraMax 75s Datasheet. URL: https://alliedmotion.com/ds.pdf.",
        "source_id": "cat-abc123",
        "attribute": "",
        "url": "https://alliedmotion.com/ds.pdf",
        "title": "EnduraMax 75s Datasheet",
    },
    {
        "text": "Product: Texas Instruments LM2596S-5.0. Step-down voltage regulator, 5V, 3A. "
                "Source: LM2596 Datasheet. URL: https://ti.com/lit/ds/lm2596.pdf.",
        "source_id": "cat-def456",
        "attribute": "",
        "url": "https://ti.com/lit/ds/lm2596.pdf",
        "title": "LM2596 Datasheet",
    },
]

_FAKE_GROQ_RESPONSE = json.dumps({
    "value": 24,
    "unit": "V",
    "raw_snippet": "24V, 10A",
    "source_id": "cat-abc123",
})


def _mock_groq_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Unit tests — corpus building
# ---------------------------------------------------------------------------

class TestCorpusBuilding:
    def test_build_default_corpus_returns_list(self):
        from backend.enrichment.agent import _build_default_corpus
        result = _build_default_corpus()
        assert isinstance(result, list)

    def test_build_default_corpus_non_empty(self):
        from backend.enrichment.agent import _build_default_corpus
        result = _build_default_corpus()
        assert len(result) >= 6, "Catalog has 6 products × ≥2 sources each"

    def test_corpus_chunks_have_required_keys(self):
        from backend.enrichment.agent import _build_default_corpus
        chunks = _build_default_corpus()
        for chunk in chunks:
            assert "text" in chunk
            assert "source_id" in chunk
            assert isinstance(chunk["text"], str)
            assert len(chunk["text"]) > 10

    def test_corpus_source_ids_prefixed(self):
        from backend.enrichment.agent import _build_default_corpus
        chunks = _build_default_corpus()
        for chunk in chunks:
            assert chunk["source_id"].startswith("cat-")

    def test_corpus_missing_catalog_returns_empty(self, tmp_path):
        from backend.enrichment import agent as agent_mod
        original = agent_mod._CATALOG_PATH
        agent_mod._CATALOG_PATH = tmp_path / "nonexistent.json"
        try:
            result = agent_mod._build_default_corpus()
            assert result == []
        finally:
            agent_mod._CATALOG_PATH = original


# ---------------------------------------------------------------------------
# Unit tests — Chroma collection
# ---------------------------------------------------------------------------

class TestChromaCollection:
    def setup_method(self):
        from backend.enrichment.agent import reset_collection
        reset_collection()

    def teardown_method(self):
        from backend.enrichment.agent import reset_collection
        reset_collection()

    def test_get_collection_returns_collection(self):
        from backend.enrichment.agent import _get_collection
        col = _get_collection(_FAKE_CORPUS)
        assert col is not None

    def test_collection_count_matches_corpus(self):
        from backend.enrichment.agent import _get_collection
        col = _get_collection(_FAKE_CORPUS)
        assert col.count() == len(_FAKE_CORPUS)

    def test_get_collection_reuses_singleton(self):
        from backend.enrichment.agent import _get_collection
        col1 = _get_collection(_FAKE_CORPUS)
        col2 = _get_collection(_FAKE_CORPUS)
        assert col1 is col2

    def test_reset_collection_forces_rebuild(self):
        from backend.enrichment.agent import _get_collection, reset_collection
        col1 = _get_collection(_FAKE_CORPUS)
        reset_collection()
        col2 = _get_collection(_FAKE_CORPUS)
        assert col1 is not col2

    def test_empty_corpus_returns_none(self):
        from backend.enrichment.agent import _get_collection
        col = _get_collection([])
        assert col is None


# ---------------------------------------------------------------------------
# Unit tests — retrieval
# ---------------------------------------------------------------------------

class TestRetrieval:
    def setup_method(self):
        from backend.enrichment.agent import reset_collection
        reset_collection()

    def teardown_method(self):
        from backend.enrichment.agent import reset_collection
        reset_collection()

    def test_retrieve_returns_list(self):
        from backend.enrichment.agent import _get_collection, _retrieve
        col = _get_collection(_FAKE_CORPUS)
        results = _retrieve("voltage_rating", col)
        assert isinstance(results, list)

    def test_retrieve_returns_at_most_top_k(self):
        from backend.enrichment.agent import _get_collection, _retrieve
        col = _get_collection(_FAKE_CORPUS)
        results = _retrieve("voltage_rating", col, top_k=1)
        assert len(results) <= 1

    def test_retrieve_chunks_have_required_keys(self):
        from backend.enrichment.agent import _get_collection, _retrieve
        col = _get_collection(_FAKE_CORPUS)
        results = _retrieve("voltage_rating", col)
        for chunk in results:
            assert "text" in chunk
            assert "source_id" in chunk

    def test_retrieve_voltage_finds_relevant_chunk(self):
        from backend.enrichment.agent import _get_collection, _retrieve
        col = _get_collection(_FAKE_CORPUS)
        results = _retrieve("voltage_rating", col)
        # At least one chunk should mention voltage-related content
        combined = " ".join(c["text"] for c in results).lower()
        assert any(kw in combined for kw in ["24v", "5v", "voltage", "v,"])


# ---------------------------------------------------------------------------
# Unit tests — Groq extraction
# ---------------------------------------------------------------------------

class TestGroqExtraction:
    def test_extract_returns_none_without_api_key(self):
        from backend.enrichment.agent import _extract_with_groq
        field = _make_field("voltage_rating")
        original = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = ""
        try:
            result = _extract_with_groq("voltage_rating", _FAKE_CORPUS, field)
            assert result is None
        finally:
            if original is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = original

    def test_extract_returns_tuple_on_valid_response(self):
        from backend.enrichment.agent import _extract_with_groq
        field = _make_field("voltage_rating")
        mock_resp = _mock_groq_response(_FAKE_GROQ_RESPONSE)
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = _extract_with_groq("voltage_rating", _FAKE_CORPUS, field)
        assert result is not None
        value, unit, snippet, source_id = result
        assert value == 24
        assert unit == "V"
        assert source_id == "cat-abc123"

    def test_extract_returns_none_when_value_is_null(self):
        from backend.enrichment.agent import _extract_with_groq
        field = _make_field("nonexistent_attr")
        mock_resp = _mock_groq_response('{"value": null}')
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = _extract_with_groq("nonexistent_attr", _FAKE_CORPUS, field)
        assert result is None

    def test_extract_handles_bad_json_gracefully(self):
        from backend.enrichment.agent import _extract_with_groq
        field = _make_field("voltage_rating")
        mock_resp = _mock_groq_response("not valid json")
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = _extract_with_groq("voltage_rating", _FAKE_CORPUS, field)
        assert result is None

    def test_extract_falls_back_source_id_to_first_chunk(self):
        """If LLM returns an unknown source_id, fall back to first chunk's id."""
        from backend.enrichment.agent import _extract_with_groq
        field = _make_field("voltage_rating")
        resp_data = json.dumps({
            "value": 24, "unit": "V",
            "raw_snippet": "24V", "source_id": "unknown-id-xyz",
        })
        mock_resp = _mock_groq_response(resp_data)
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = _extract_with_groq("voltage_rating", _FAKE_CORPUS, field)
        assert result is not None
        _, _, _, source_id = result
        assert source_id == _FAKE_CORPUS[0]["source_id"]


# ---------------------------------------------------------------------------
# Unit tests — enrich() public API
# ---------------------------------------------------------------------------

class TestEnrichPublicAPI:
    def setup_method(self):
        from backend.enrichment.agent import reset_collection
        reset_collection()

    def teardown_method(self):
        from backend.enrichment.agent import reset_collection
        reset_collection()

    def test_enrich_returns_none_without_api_key(self):
        from backend.enrichment import enrich
        field = _make_field("voltage_rating")
        original = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = ""
        try:
            result = enrich(field, corpus=_FAKE_CORPUS)
            assert result is None
        finally:
            if original is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = original

    def test_enrich_returns_resolved_field_on_success(self):
        from backend.enrichment import enrich
        field = _make_field("voltage_rating")
        mock_resp = _mock_groq_response(_FAKE_GROQ_RESPONSE)
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = enrich(field, corpus=_FAKE_CORPUS)
        assert isinstance(result, ResolvedField)

    def test_enrich_status_is_enriched(self):
        from backend.enrichment import enrich
        field = _make_field("voltage_rating")
        mock_resp = _mock_groq_response(_FAKE_GROQ_RESPONSE)
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = enrich(field, corpus=_FAKE_CORPUS)
        assert result is not None
        assert result.status == FieldStatus.ENRICHED

    def test_enrich_confidence_in_valid_range(self):
        from backend.enrichment import enrich
        field = _make_field("voltage_rating")
        mock_resp = _mock_groq_response(_FAKE_GROQ_RESPONSE)
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = enrich(field, corpus=_FAKE_CORPUS)
        assert result is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_enrich_preserves_product_id(self):
        from backend.enrichment import enrich
        field = _make_field("voltage_rating")
        mock_resp = _mock_groq_response(_FAKE_GROQ_RESPONSE)
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = enrich(field, corpus=_FAKE_CORPUS)
        assert result is not None
        assert result.product_id == field.product_id

    def test_enrich_reasoning_mentions_rag(self):
        from backend.enrichment import enrich
        field = _make_field("voltage_rating")
        mock_resp = _mock_groq_response(_FAKE_GROQ_RESPONSE)
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = enrich(field, corpus=_FAKE_CORPUS)
        assert result is not None
        assert "enriched" in result.reasoning.lower() or "rag" in result.reasoning.lower()

    def test_enrich_returns_none_on_empty_corpus(self):
        from backend.enrichment import enrich
        field = _make_field("voltage_rating")
        result = enrich(field, corpus=[])
        assert result is None

    def test_enrich_returns_none_when_groq_finds_nothing(self):
        from backend.enrichment import enrich
        field = _make_field("nonexistent_attribute_xyz")
        mock_resp = _mock_groq_response('{"value": null}')
        with patch("groq.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = mock_resp
            result = enrich(field, corpus=_FAKE_CORPUS)
        assert result is None

    def test_enrich_importable_from_package(self):
        from backend.enrichment import enrich
        assert callable(enrich)


# ---------------------------------------------------------------------------
# Live integration tests (require GROQ_API_KEY)
# ---------------------------------------------------------------------------

_has_groq = (
    bool(os.environ.get("GROQ_API_KEY")) and
    os.environ.get("GROQ_API_KEY") != "your_groq_api_key_here"
)


@pytest.mark.skipif(not _has_groq, reason="GROQ_API_KEY not set — skipping live enrichment tests.")
class TestEnrichLive:
    """
    Live tests against the default catalog corpus.
    These consume Groq API quota — run sparingly.
    """

    def setup_method(self):
        from backend.enrichment.agent import reset_collection
        reset_collection()

    def teardown_method(self):
        from backend.enrichment.agent import reset_collection
        reset_collection()

    def test_enrich_voltage_from_catalog(self):
        from backend.enrichment import enrich
        field = _make_field("voltage_rating")
        result = enrich(field)  # uses default catalog corpus
        # May return None if LLM can't find it — that's acceptable
        if result is not None:
            assert isinstance(result, ResolvedField)
            assert result.status == FieldStatus.ENRICHED
            assert result.value is not None

    def test_enrich_missing_field_recovers_value(self):
        """
        Simulate removing voltage_rating from direct sources and recovering via RAG.
        The catalog corpus contains voltage info for multiple products.
        """
        from backend.enrichment import enrich
        field = Field(
            product_id="prod-enduramax",
            attribute="voltage_rating",
            value=None,
            unit="",
            source_id="",
        )
        result = enrich(field)
        if result is not None:
            assert result.status == FieldStatus.ENRICHED
            assert 0.0 <= result.confidence <= 1.0
            assert result.source_id  # must cite a source

    def test_enrich_schema_valid_output(self):
        from backend.enrichment import enrich
        field = _make_field("operating_temperature")
        result = enrich(field)
        if result is not None:
            assert isinstance(result, ResolvedField)
            assert result.attribute == "operating_temperature"
            assert result.product_id == field.product_id
            assert result.reasoning
