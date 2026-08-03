"""
backend/discovery/test_discovery.py
=====================================
Phase 1 tests for the discovery module.

Run from project root with the `uni` venv active:
    python -m pytest backend/discovery/test_discovery.py -v

Tests are designed to be fast and safe for CI:
  - catalog tests are fully offline (no API calls).
  - web tests are skipped automatically when GROQ_API_KEY / network unavailable.
  - All assertions operate on the public Source schema — no internal access.
"""

from __future__ import annotations

import os
import pytest

from backend.schema import Source, SourceOrigin, SourceType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def catalog():
    """Load the reference catalog once for all catalog tests."""
    from backend.discovery.catalog import load_catalog
    return load_catalog()


# ---------------------------------------------------------------------------
# Unit tests — catalog sub-agent (always offline, zero API)
# ---------------------------------------------------------------------------

class TestCatalogLoad:
    def test_catalog_loads_non_empty(self, catalog):
        assert len(catalog) >= 1, "Reference catalog must contain at least 1 product."

    def test_catalog_products_have_required_keys(self, catalog):
        for product in catalog:
            assert "mpn" in product
            assert "brand" in product
            assert "sources" in product


class TestCatalogSearch:
    def test_known_mpn_returns_sources(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("EM75S-001", "Allied Motion", catalog)
        assert len(sources) >= 1, "Known MPN must return at least 1 catalog source."

    def test_sources_are_schema_valid(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("EM75S-001", "Allied Motion", catalog)
        for src in sources:
            assert isinstance(src, Source)
            assert src.url.startswith("http")
            assert src.origin == SourceOrigin.DISCOVERED
            assert 0.0 <= src.trust_score <= 1.0
            assert src.source_type in (SourceType.PDF, SourceType.HTML, SourceType.IMAGE)
            assert src.source_id.startswith("cat-")

    def test_unknown_mpn_returns_empty(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("NONEXISTENT-9999", "NoSuchBrand", catalog)
        assert sources == [], "Unknown MPN must return an empty list."

    def test_alias_matching(self, catalog):
        """Catalog should match on known aliases, not just the canonical MPN."""
        from backend.discovery.catalog import search_catalog
        # "EnduraMax 75s" is an alias for EM75S-001 in the catalog.
        sources = search_catalog("EnduraMax 75s", "Allied Motion", catalog)
        assert len(sources) >= 1, "Alias matching must work."

    def test_pdf_source_type_assigned(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("EM75S-001", "Allied Motion", catalog)
        types = {s.source_type for s in sources}
        assert SourceType.PDF in types, "At least one PDF source expected for EnduraMax."

    def test_stm32_known_product(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("STM32F103C8T6", "STMicroelectronics", catalog)
        assert len(sources) >= 2, "STM32 must return multiple catalog sources."


# ---------------------------------------------------------------------------
# Unit tests — web_search helpers (no network, no API)
# ---------------------------------------------------------------------------

class TestWebSearchHelpers:
    def test_url_to_source_id_is_deterministic(self):
        from backend.discovery.web_search import _url_to_source_id
        url = "https://example.com/product"
        assert _url_to_source_id(url) == _url_to_source_id(url)
        assert _url_to_source_id(url).startswith("web-")
        assert len(_url_to_source_id(url)) == 16  # "web-" + 12 hex chars

    def test_infer_source_type_pdf(self):
        from backend.discovery.web_search import _infer_source_type
        assert _infer_source_type("https://ti.com/ds/lm2596.pdf") == SourceType.PDF

    def test_infer_source_type_html(self):
        from backend.discovery.web_search import _infer_source_type
        assert _infer_source_type("https://digikey.com/product/stm32") == SourceType.HTML

    def test_trust_score_manufacturer_high(self):
        from backend.discovery.web_search import _score_trust
        score = _score_trust("https://www.ti.com/product/LM2596")
        assert score >= 0.90, "Manufacturer domain must score ≥0.90."

    def test_trust_score_distributor_medium(self):
        from backend.discovery.web_search import _score_trust
        score = _score_trust("https://www.digikey.com/en/products/detail/lm2596")
        assert 0.65 <= score < 0.90, "Distributor must score between 0.65 and 0.90."

    def test_trust_score_unknown_domain_default(self):
        from backend.discovery.web_search import _score_trust, _DEFAULT_TRUST
        score = _score_trust("https://some-random-blog.com/review")
        assert score == _DEFAULT_TRUST

    def test_result_to_source_schema(self):
        from backend.discovery.web_search import _result_to_source
        fake_result = {
            "href": "https://www.ti.com/product/LM2596",
            "title": "LM2596 | TI",
            "body": "Step-down switching regulator...",
        }
        src = _result_to_source(fake_result)
        assert isinstance(src, Source)
        assert src.url == "https://www.ti.com/product/LM2596"
        assert src.origin == SourceOrigin.DISCOVERED
        assert 0.0 <= src.trust_score <= 1.0


# ---------------------------------------------------------------------------
# Unit tests — query formulation fallback (no Groq API key)
# ---------------------------------------------------------------------------

class TestQueryFormulation:
    def test_rule_based_fallback_returns_3_queries(self):
        from backend.discovery.agent import _rule_based_queries
        queries = _rule_based_queries("EM75S-001", "Allied Motion", "brushless motor 24V")
        assert len(queries) == 3
        for q in queries:
            assert isinstance(q, str)
            assert len(q) > 5

    def test_rule_based_includes_mpn(self):
        from backend.discovery.agent import _rule_based_queries
        queries = _rule_based_queries("LM2596S-5.0", "Texas Instruments", "voltage regulator")
        assert any("LM2596S-5.0" in q for q in queries)

    def test_groq_formulation_fallback_on_bad_key(self):
        """If Groq returns garbage JSON, formulate_queries must return 3 fallback strings."""
        from unittest.mock import MagicMock
        from backend.discovery.web_search import formulate_queries

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("rate limit")
        queries = formulate_queries("EM75S-001", "Allied Motion", "motor", mock_client)
        assert len(queries) == 3


# ---------------------------------------------------------------------------
# Integration tests — discover() (offline path, catalog only)
# ---------------------------------------------------------------------------

class TestDiscoverOffline:
    """
    These tests run discover() without a valid GROQ_API_KEY so only the catalog
    + rule-based-query path is exercised. No network calls, no API quota used.
    """

    def _run_without_groq(self, mpn, brand, description):
        """Patch env so Groq client is not created."""
        original = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = ""
        try:
            from backend.discovery.agent import discover
            # Also patch search_web to avoid live network in offline test
            import backend.discovery.agent as agent_mod
            original_search = agent_mod.search_web
            agent_mod.search_web = lambda *a, **kw: []  # no network
            try:
                return discover(mpn, brand, description)
            finally:
                agent_mod.search_web = original_search
        finally:
            if original is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = original

    def test_known_product_returns_sources(self):
        sources = self._run_without_groq("EM75S-001", "Allied Motion", "brushless motor 24V")
        assert len(sources) >= 1

    def test_all_sources_schema_valid(self):
        sources = self._run_without_groq("EM75S-001", "Allied Motion", "brushless motor 24V")
        for src in sources:
            assert isinstance(src, Source)
            assert src.url.startswith("http")
            assert 0.0 <= src.trust_score <= 1.0
            assert src.origin == SourceOrigin.DISCOVERED

    def test_sources_ranked_by_trust(self):
        sources = self._run_without_groq("EM75S-001", "Allied Motion", "brushless motor 24V")
        if len(sources) > 1:
            scores = [s.trust_score for s in sources]
            assert scores == sorted(scores, reverse=True), "Sources must be trust-ranked."

    def test_no_duplicate_urls(self):
        sources = self._run_without_groq("EM75S-001", "Allied Motion", "brushless motor 24V")
        urls = [s.url for s in sources]
        assert len(urls) == len(set(urls)), "No duplicate URLs allowed."

    def test_unknown_product_returns_empty_list(self):
        sources = self._run_without_groq("ZZZZ-9999", "NoSuchBrand", "fictitious product")
        assert isinstance(sources, list)


# ---------------------------------------------------------------------------
# Integration test — live discover() (requires GROQ_API_KEY + network)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY") or
    os.environ.get("GROQ_API_KEY") == "your_groq_api_key_here",
    reason="GROQ_API_KEY not set — skipping live discovery test.",
)
class TestDiscoverLive:
    def test_discover_enduramax_returns_multiple_sources(self):
        from backend.discovery.agent import discover
        sources = discover("EM75S-001", "Allied Motion", "EnduraMax 75s brushless DC motor 24V 10A")
        assert len(sources) >= 2, (
            f"Expected ≥2 sources for EnduraMax, got {len(sources)}: {[s.url for s in sources]}"
        )

    def test_discover_sources_all_valid(self):
        from backend.discovery.agent import discover
        sources = discover("LM2596S-5.0", "Texas Instruments", "step-down voltage regulator 5V 3A")
        for src in sources:
            assert isinstance(src, Source)
            assert src.url.startswith("http")
            assert 0.0 <= src.trust_score <= 1.0
            assert src.source_id  # non-empty

    def test_discover_no_duplicates(self):
        from backend.discovery.agent import discover
        sources = discover("STM32F103C8T6", "STMicroelectronics", "ARM Cortex-M3 microcontroller")
        urls = [s.url for s in sources]
        assert len(urls) == len(set(urls)), "Duplicate URLs found in live discover() output."
