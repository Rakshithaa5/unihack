"""
backend/test_phase1_extended.py
================================
Extended Phase 1 verification tests for both team members.

Covers:
  - Rakshitha (discovery): catalog matching, trust scoring, query formulation,
    deduplication, ranking, schema compliance, edge cases.
  - Ramya (collector): merge_sources logic, handle_upload file types, trust
    clamping, deduplication, type validation, edge cases.
  - Cross-boundary: collector works correctly with discovery real and stub output.

Run from project root with the uni venv active:
    uni\Scripts\python.exe -m pytest backend/test_phase1_extended.py -v
"""

from __future__ import annotations

import io
import os

import pytest

from backend.schema import Source, SourceOrigin, SourceType


# ============================================================================
# RAMYA — Collector (merge_sources + handle_upload)
# ============================================================================

class TestMergeSourcesExtended:
    """Extended tests for Ramya merge_sources function."""

    def _make_source(self, sid, url, origin=SourceOrigin.DISCOVERED, trust=0.8):
        return Source(
            source_id=sid,
            url=url,
            source_type=SourceType.HTML,
            origin=origin,
            trust_score=trust,
            title="Test Source",
        )

    def test_empty_both_inputs_returns_empty(self):
        from backend.collector import merge_sources
        result = merge_sources([], [])
        assert result == []

    def test_only_discovered_returns_discovered(self):
        from backend.collector import merge_sources
        src = self._make_source("d1", "https://example.com/product")
        result = merge_sources([src], [])
        assert len(result) == 1
        assert result[0].origin == SourceOrigin.DISCOVERED

    def test_only_uploaded_returns_uploaded(self):
        from backend.collector import merge_sources
        src = self._make_source("u1", "https://upload.example.com", origin=SourceOrigin.UPLOADED)
        result = merge_sources([], [src])
        assert len(result) == 1
        assert result[0].origin == SourceOrigin.UPLOADED

    def test_uploaded_appears_before_discovered(self):
        """Uploaded sources should be first in the merged pool."""
        from backend.collector import merge_sources
        disc = self._make_source("d1", "https://disc.example.com", origin=SourceOrigin.DISCOVERED)
        upl = self._make_source("u1", "https://upload.example.com", origin=SourceOrigin.UPLOADED)
        result = merge_sources([disc], [upl])
        assert result[0].origin == SourceOrigin.UPLOADED, "Uploaded must come before discovered"
        assert result[1].origin == SourceOrigin.DISCOVERED

    def test_duplicate_source_id_is_collapsed(self):
        """Sources with the same source_id must appear only once."""
        from backend.collector import merge_sources
        src = self._make_source("dup-id", "https://a.com")
        src2 = self._make_source("dup-id", "https://a.com")
        result = merge_sources([src], [src2])
        assert len(result) == 1

    def test_non_source_object_raises_type_error(self):
        """Non-Source objects must raise TypeError."""
        from backend.collector import merge_sources
        with pytest.raises(TypeError):
            merge_sources(["not a Source"], [])

    def test_large_pool_preserves_all_unique_sources(self):
        """50 unique sources should all survive the merge."""
        from backend.collector import merge_sources
        sources = [
            self._make_source(f"d{i}", f"https://example.com/{i}")
            for i in range(50)
        ]
        result = merge_sources(sources, [])
        assert len(result) == 50

    def test_all_sources_are_schema_instances(self):
        """Every item in the merged pool must be a Source instance."""
        from backend.collector import merge_sources
        disc = [self._make_source(f"d{i}", f"https://disc.example.com/{i}") for i in range(3)]
        upl = [self._make_source(f"u{i}", f"https://upload.example.com/{i}", origin=SourceOrigin.UPLOADED) for i in range(2)]
        result = merge_sources(disc, upl)
        assert all(isinstance(s, Source) for s in result)

    def test_trust_scores_in_valid_range(self):
        from backend.collector import merge_sources
        disc = [self._make_source(f"d{i}", f"https://example.com/{i}", trust=round(i * 0.1, 1)) for i in range(1, 10)]
        result = merge_sources(disc, [])
        assert all(0.0 <= s.trust_score <= 1.0 for s in result)


class TestHandleUploadExtended:
    """Extended tests for Ramya handle_upload function."""

    def test_pdf_gets_high_trust(self):
        from backend.collector import handle_upload
        src = handle_upload("spec.pdf", io.BytesIO(b"%PDF data"), "application/pdf")
        assert src.trust_score >= 0.75, "PDF uploads should have trust >= 0.75"

    def test_image_gets_lower_trust_than_pdf(self):
        from backend.collector import handle_upload
        pdf_src = handle_upload("spec.pdf", io.BytesIO(b"%PDF"), "application/pdf")
        img_src = handle_upload("nameplate.jpg", io.BytesIO(b"JFIF"), "image/jpeg")
        assert pdf_src.trust_score > img_src.trust_score, "PDF should have higher trust than image"

    def test_unknown_file_type_returns_unknown_source_type(self):
        from backend.collector import handle_upload
        src = handle_upload("notes.txt", io.BytesIO(b"some text"), "text/plain")
        assert src.source_type == SourceType.UNKNOWN

    def test_png_file_gets_image_source_type(self):
        from backend.collector import handle_upload
        src = handle_upload("photo.png", io.BytesIO(b"\x89PNG"), "image/png")
        assert src.source_type == SourceType.IMAGE

    def test_html_file_gets_html_source_type(self):
        from backend.collector import handle_upload
        src = handle_upload("page.html", io.BytesIO(b"<html>"), "text/html")
        assert src.source_type == SourceType.HTML

    def test_source_id_is_unique_across_calls(self):
        from backend.collector import handle_upload
        s1 = handle_upload("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")
        s2 = handle_upload("b.pdf", io.BytesIO(b"%PDF"), "application/pdf")
        assert s1.source_id != s2.source_id, "Each upload must get a unique source_id"

    def test_source_id_starts_with_upload_prefix(self):
        from backend.collector import handle_upload
        src = handle_upload("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")
        assert src.source_id.startswith("upload-")

    def test_origin_is_always_uploaded(self):
        from backend.collector import handle_upload
        for filename in ["a.pdf", "b.jpg", "c.html", "d.txt"]:
            src = handle_upload(filename, io.BytesIO(b"data"))
            assert src.origin == SourceOrigin.UPLOADED

    def test_title_matches_filename(self):
        from backend.collector import handle_upload
        src = handle_upload("product_manual.pdf", io.BytesIO(b"%PDF"), "application/pdf")
        assert src.title == "product_manual.pdf"

    def test_trust_score_always_in_valid_range(self):
        from backend.collector import handle_upload
        for filename in ["x.pdf", "y.png", "z.html", "w.xyz"]:
            src = handle_upload(filename, io.BytesIO(b"data"))
            assert 0.0 <= src.trust_score <= 1.0

    def test_jpeg_extension_is_image_type(self):
        from backend.collector import handle_upload
        src = handle_upload("photo.jpeg", io.BytesIO(b"JFIF"))
        assert src.source_type == SourceType.IMAGE

    def test_webp_extension_is_image_type(self):
        from backend.collector import handle_upload
        src = handle_upload("render.webp", io.BytesIO(b"RIFF"))
        assert src.source_type == SourceType.IMAGE


# ============================================================================
# RAKSHITHA — Discovery (catalog + web_search helpers + agent)
# ============================================================================

class TestCatalogExtended:
    """Additional catalog tests beyond the base test_discovery.py suite."""

    @pytest.fixture(scope="class")
    def catalog(self):
        from backend.discovery.catalog import load_catalog
        return load_catalog()

    def test_all_catalog_sources_have_urls(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("EM75S-001", "Allied Motion", catalog)
        assert all(s.url for s in sources), "Every catalog source must have a non-empty URL"

    def test_all_catalog_sources_have_source_ids(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("EM75S-001", "Allied Motion", catalog)
        assert all(s.source_id for s in sources)

    def test_catalog_source_ids_are_unique(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("EM75S-001", "Allied Motion", catalog)
        ids = [s.source_id for s in sources]
        assert len(ids) == len(set(ids)), "Catalog source IDs must be unique"

    def test_catalog_trust_scores_in_range(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("EM75S-001", "Allied Motion", catalog)
        assert all(0.0 <= s.trust_score <= 1.0 for s in sources)

    def test_catalog_source_id_prefix_is_cat(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("EM75S-001", "Allied Motion", catalog)
        assert all(s.source_id.startswith("cat-") for s in sources)

    def test_case_insensitive_mpn_match(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources_upper = search_catalog("EM75S-001", "Allied Motion", catalog)
        sources_lower = search_catalog("em75s-001", "allied motion", catalog)
        assert len(sources_upper) == len(sources_lower), "MPN match must be case-insensitive"

    def test_missing_catalog_file_returns_empty(self, tmp_path):
        from backend.discovery.catalog import load_catalog
        result = load_catalog(path=tmp_path / "nonexistent.json")
        assert result == []

    def test_stm32_sources_schema_valid(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("STM32F103C8T6", "STMicroelectronics", catalog)
        for src in sources:
            assert isinstance(src, Source)
            assert src.origin == SourceOrigin.DISCOVERED
            assert src.source_type in (SourceType.PDF, SourceType.HTML, SourceType.IMAGE)

    def test_all_origins_are_discovered(self, catalog):
        from backend.discovery.catalog import search_catalog
        sources = search_catalog("EM75S-001", "Allied Motion", catalog)
        assert all(s.origin == SourceOrigin.DISCOVERED for s in sources)


class TestWebSearchHelpersExtended:
    """Additional tests for Rakshitha web_search helper functions."""

    def test_source_id_length_is_16_chars(self):
        from backend.discovery.web_search import _url_to_source_id
        sid = _url_to_source_id("https://example.com")
        assert len(sid) == 16  # "web-" (4) + 12 hex chars

    def test_source_id_is_stable_across_calls(self):
        from backend.discovery.web_search import _url_to_source_id
        url = "https://stable-test.com/product"
        assert _url_to_source_id(url) == _url_to_source_id(url)

    def test_different_urls_produce_different_ids(self):
        from backend.discovery.web_search import _url_to_source_id
        id1 = _url_to_source_id("https://a.com")
        id2 = _url_to_source_id("https://b.com")
        assert id1 != id2

    def test_pdf_url_is_pdf_type(self):
        from backend.discovery.web_search import _infer_source_type
        assert _infer_source_type("https://ti.com/lit/ds/lm2596.pdf") == SourceType.PDF

    def test_datasheet_keyword_is_pdf_type(self):
        from backend.discovery.web_search import _infer_source_type
        assert _infer_source_type("https://ti.com/datasheet/lm2596") == SourceType.PDF

    def test_jpg_is_image_type(self):
        from backend.discovery.web_search import _infer_source_type
        assert _infer_source_type("https://example.com/nameplate.jpg") == SourceType.IMAGE

    def test_png_is_image_type(self):
        from backend.discovery.web_search import _infer_source_type
        assert _infer_source_type("https://example.com/photo.png") == SourceType.IMAGE

    def test_alliedmotion_gets_high_trust(self):
        from backend.discovery.web_search import _score_trust
        score = _score_trust("https://www.alliedmotion.com/product/enduramax-75s")
        assert score >= 0.90

    def test_stmicro_gets_high_trust(self):
        from backend.discovery.web_search import _score_trust
        score = _score_trust("https://www.st.com/en/microcontrollers-microprocessors/stm32f103.html")
        assert score >= 0.90

    def test_mouser_gets_distributor_trust(self):
        from backend.discovery.web_search import _score_trust
        score = _score_trust("https://www.mouser.com/ProductDetail/stm32f103")
        assert 0.65 <= score < 0.90

    def test_pdf_url_gets_high_trust(self):
        from backend.discovery.web_search import _score_trust
        score = _score_trust("https://unknown-site.example.com/product.pdf")
        assert score >= 0.85  # .pdf$ pattern

    def test_result_to_source_all_fields_set(self):
        from backend.discovery.web_search import _result_to_source
        result = {
            "href": "https://www.ti.com/product/LM2596",
            "title": "LM2596 - TI",
            "body": "Step-down voltage regulator.",
        }
        src = _result_to_source(result)
        assert src.source_id
        assert src.url == "https://www.ti.com/product/LM2596"
        assert src.title == "LM2596 - TI"
        assert src.origin == SourceOrigin.DISCOVERED
        assert src.metadata.get("snippet")

    def test_source_id_prefix_is_web(self):
        from backend.discovery.web_search import _url_to_source_id
        sid = _url_to_source_id("https://any.example.com/page")
        assert sid.startswith("web-")


class TestDiscoverAgentExtended:
    """Extended offline-only tests for Rakshitha discover() function."""

    def _offline_discover(self, mpn, brand, description=""):
        """Run discover() with Groq disabled and web search mocked out."""
        original_key = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = ""
        try:
            import backend.discovery.agent as agent_mod
            original_search = agent_mod.search_web
            agent_mod.search_web = lambda *a, **kw: []  # no network
            try:
                return agent_mod.discover(mpn, brand, description)
            finally:
                agent_mod.search_web = original_search
        finally:
            if original_key is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = original_key

    def test_discover_returns_list(self):
        result = self._offline_discover("EM75S-001", "Allied Motion")
        assert isinstance(result, list)

    def test_discover_known_product_returns_at_least_one_source(self):
        result = self._offline_discover("EM75S-001", "Allied Motion", "brushless motor 24V")
        assert len(result) >= 1

    def test_discover_sources_are_schema_valid(self):
        result = self._offline_discover("EM75S-001", "Allied Motion")
        for src in result:
            assert isinstance(src, Source)
            assert src.source_id
            assert src.url.startswith("http")
            assert src.origin == SourceOrigin.DISCOVERED
            assert 0.0 <= src.trust_score <= 1.0

    def test_discover_output_is_sorted_by_trust_desc(self):
        result = self._offline_discover("EM75S-001", "Allied Motion")
        scores = [s.trust_score for s in result]
        assert scores == sorted(scores, reverse=True)

    def test_discover_no_duplicate_urls(self):
        result = self._offline_discover("EM75S-001", "Allied Motion")
        urls = [s.url for s in result]
        assert len(urls) == len(set(urls))

    def test_discover_stm32_multiple_sources(self):
        result = self._offline_discover("STM32F103C8T6", "STMicroelectronics")
        assert len(result) >= 2

    def test_discover_returns_list_for_unknown_product(self):
        result = self._offline_discover("UNKNOWN-XYZABC-9999", "NoSuchBrandXYZ")
        assert isinstance(result, list)

    def test_discover_handles_empty_description_gracefully(self):
        result = self._offline_discover("EM75S-001", "Allied Motion", description="")
        assert isinstance(result, list)

    def test_discover_no_duplicate_source_ids(self):
        result = self._offline_discover("EM75S-001", "Allied Motion")
        ids = [s.source_id for s in result]
        assert len(ids) == len(set(ids))


# ============================================================================
# CROSS-BOUNDARY — Discovery output flows into Collector (Sync Checkpoint)
# ============================================================================

class TestDiscoveryToCollectorIntegration:
    """
    Verifies that Rakshitha discover() output can flow directly into
    Ramya merge_sources() — the Phase 1 sync checkpoint scenario.
    """

    def _offline_discover(self, mpn, brand):
        original_key = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = ""
        try:
            import backend.discovery.agent as agent_mod
            original_search = agent_mod.search_web
            agent_mod.search_web = lambda *a, **kw: []
            try:
                return agent_mod.discover(mpn, brand, "")
            finally:
                agent_mod.search_web = original_search
        finally:
            if original_key is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = original_key

    def test_discovery_output_directly_feeds_merger(self):
        from backend.collector import merge_sources, handle_upload
        discovered = self._offline_discover("EM75S-001", "Allied Motion")
        uploaded = [handle_upload("manual.pdf", io.BytesIO(b"%PDF-test"), "application/pdf")]
        merged = merge_sources(discovered, uploaded)
        assert len(merged) >= 1
        assert all(isinstance(s, Source) for s in merged)

    def test_merged_pool_contains_both_origins(self):
        from backend.collector import merge_sources, handle_upload
        discovered = self._offline_discover("EM75S-001", "Allied Motion")
        uploaded = [handle_upload("spec.pdf", io.BytesIO(b"%PDF"), "application/pdf")]
        merged = merge_sources(discovered, uploaded)
        origins = {s.origin for s in merged}
        assert SourceOrigin.UPLOADED in origins
        assert SourceOrigin.DISCOVERED in origins

    def test_merged_pool_no_duplicate_ids(self):
        from backend.collector import merge_sources, handle_upload
        discovered = self._offline_discover("EM75S-001", "Allied Motion")
        uploaded = [handle_upload("photo.jpg", io.BytesIO(b"JFIF"), "image/jpeg")]
        merged = merge_sources(discovered, uploaded)
        ids = [s.source_id for s in merged]
        assert len(ids) == len(set(ids))

    def test_merged_pool_all_trust_scores_valid(self):
        from backend.collector import merge_sources, handle_upload
        discovered = self._offline_discover("STM32F103C8T6", "STMicroelectronics")
        uploaded = [handle_upload("datasheet.pdf", io.BytesIO(b"%PDF"), "application/pdf")]
        merged = merge_sources(discovered, uploaded)
        assert all(0.0 <= s.trust_score <= 1.0 for s in merged)

    def test_stub_discovery_output_also_works_with_merger(self):
        """Ramya can use Rakshitha stub discovery output — no real API needed."""
        from backend.discovery.stub import discover as stub_discover
        from backend.collector import merge_sources
        discovered = stub_discover("ANY-MPN", "AnyBrand", "any description")
        merged = merge_sources(discovered, [])
        assert isinstance(merged, list)
        assert len(merged) == 3  # stub returns exactly 3 sources
        assert all(isinstance(s, Source) for s in merged)

    def test_uploaded_comes_before_catalog_in_merged_pool(self):
        """In the merged pool, uploaded sources appear first."""
        from backend.collector import merge_sources, handle_upload
        discovered = self._offline_discover("EM75S-001", "Allied Motion")
        uploaded = [handle_upload("spec.pdf", io.BytesIO(b"%PDF"), "application/pdf")]
        merged = merge_sources(discovered, uploaded)
        first_origins = [s.origin for s in merged[:len(uploaded)]]
        assert all(o == SourceOrigin.UPLOADED for o in first_origins)
