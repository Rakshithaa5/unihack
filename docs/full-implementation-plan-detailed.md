# ProvenIQ — Full Implementation Plan
### Free-Tier Stack · Folder Structure · Every Phase, Both People, Zero Merge Conflicts

---

## 1. Tech Stack (100% free tier / open source)

| Layer | Choice | Why free |
|---|---|---|
| Discovery / web search | Free-tier web-search API + Groq LLM for query formulation | No card required |
| LLM (reasoning, reconciliation, enrichment) | **Groq API** — Llama 3.3 70B / 3.1 8B | Generous free tier, fast inference |
| VLM (image/diagram extraction) | **Groq API** — Llama 3.2 Vision (11B) | Same key, free vision preview |
| PDF parsing | **pdfplumber** / **PyMuPDF** | Open source, local, zero cost |
| HTML parsing | **BeautifulSoup** | Open source, local, zero cost |
| Embeddings (RAG) | **sentence-transformers** (`all-MiniLM-L6-v2`, local) | Runs locally, no API cost, no rate limit |
| Vector store | **Chroma** (local, embedded mode) | Free, no hosted service |
| Knowledge graph storage | **SQLite** | Free, local file |
| Agent orchestration | **LangGraph** or hand-rolled Python loop | Free |
| Backend | **FastAPI** | Free, self-hosted |
| Frontend | **Next.js / React** | Free |
| Backend hosting | **Render free tier** | 750 free instance-hours/month |
| Frontend hosting | **Vercel free tier** | Free for hackathon projects |
| Version control | **GitHub** | Free repo |

**Only constraint to design around:** Groq's free-tier rate limits — handled via local embeddings, caching during dev, and pre-running the batch demo rather than running 20 products live on stage.

---

## 2. Folder Structure

```
provenIQ/
├── backend/
│   ├── discovery/          ← RAKSHITHA
│   ├── collector/           ← RAMYA
│   ├── extraction/           ← RAKSHITHA
│   ├── reconciliation/        ← RAMYA
│   ├── enrichment/             ← RAKSHITHA
│   ├── validation/              ← RAMYA
│   ├── hitl/                     ← RAMYA
│   ├── storage/                   ← RAMYA
│   ├── batch/                      ← RAKSHITHA
│   ├── api/                         ← RAMYA
│   ├── pipeline.py                   ← RAMYA (sole editor, shared)
│   └── schema.py                      ← BOTH (joint, locked after Phase 0)
├── frontend/
│   ├── components/
│   │   ├── DiscoveryView.tsx          ← RAKSHITHA
│   │   ├── KGVisualization.tsx        ← RAKSHITHA
│   │   ├── BatchReport.tsx            ← RAKSHITHA
│   │   ├── ConflictEvidenceView.tsx   ← RAMYA
│   │   ├── HITLQueue.tsx              ← RAMYA
│   │   └── UploadPanel.tsx            ← RAMYA
│   └── pages/
│       └── index.tsx                   ← RAKSHITHA (sole editor, shared)
├── data/
│   ├── real/                            ← RAKSHITHA
│   └── synthetic/                        ← RAKSHITHA
├── requirements.txt
├── package.json
└── README.md
```

**Rule:** if you're about to edit a file outside your own folder, stop — it's either one of the 3 named shared files below, or you've drifted outside scope.

**The 3 shared files, fixed rules:**
| File | Editor | Rule |
|---|---|---|
| `backend/schema.py` | Both, jointly | Built together in Phase 0, then locked — later changes need both people on a call |
| `backend/pipeline.py` | Ramya only | Rakshitha's functions are imported and called, never edited by Ramya; Rakshitha never pushes here |
| `frontend/pages/index.tsx` | Rakshitha only | Assembles both people's components; Ramya hands off finished components, never pushes here |

---

## 3. Why No Phase Creates a Bottleneck

A bottleneck happens when one person's *start* depends on the other's *finish*. This plan removes that: in Phase 0, both people agree on a shared data schema and function signatures, then **immediately write a 15-20 minute stub** of their own functions (hardcoded return values matching the schema). From that point on, either person can build, test, and run their entire side of the pipeline against stubs — nobody is ever sitting idle waiting for real code to land. Sync checkpoints later just swap stub data for real data; they're quick confirmations, not gates.

---

## 4. Phase-by-Phase Plan — Every Phase, Both People

### Phase 0 — Shared Foundation
**Who: Both, together, one sitting (~45 min)**

Sit down together and write `backend/schema.py`. This defines the three data shapes everything else depends on:
- `Field` — a single extracted data point (product, attribute, value, unit, which source it came from, the raw snippet, when it was extracted)
- `ResolvedField` — a `Field` plus confidence score, status (resolved/conflict-resolved/enriched/needs-review), a one-line reasoning string, and any alternate values considered
- `Source` — a document/page/image reference, tagged as `discovered` or `uploaded`, with a trust score

Also agree on the function signatures crossing the boundary between your two tracks (who calls what, what goes in, what comes out — see Section 5). This file is **locked** the moment this session ends. Neither person edits it solo afterward.

### Phase 0.5 — Stub Writing
**Who: Both, individually, immediately after Phase 0 (~15-20 min each)**

Each person writes a fake version of their own functions that returns hardcoded data matching the Phase 0 schema — e.g. Rakshitha's `discover()` returns 2-3 made-up `Source` objects; Ramya's `reconcile()` returns the first `Field` it's given, unchanged, with `confidence: 0.5`. This single step is what makes every phase below fully parallel — both people can now run the *whole* pipeline end-to-end on fake-but-correctly-shaped data before any real feature exists.

---

### Phase 1 — Discovery vs. Source Collection

**Rakshitha's tasks (`backend/discovery/`):**
- Build the web-search sub-agent: takes MPN + brand + short description, formulates search queries (via Groq LLM), calls a free-tier web-search API, and returns candidate URLs/documents as `Source` objects
- Build the catalog sub-agent: searches a small pre-loaded reference corpus as a reliable, rate-limit-safe fallback when live search is thin or during demo rehearsal
- Test: given a real product's MPN+brand+description, confirm it surfaces at least 2-3 genuinely relevant sources

**Ramya's tasks (`backend/collector/`):**
- Build the source merger: takes discovered sources (from Rakshitha, or her stub in the meantime) and any uploaded documents, and combines them into one evidence pool
- Build the upload handler: accepts PDF/image/manual file uploads, wraps them as `Source` objects tagged `origin: "uploaded"`, and assigns an initial trust score
- Test: feed it Rakshitha's *stub* discovery output plus a fake upload, confirm the merged list is well-formed — no need to wait for Rakshitha's real discovery agent to be done

**Sync checkpoint:** 10-15 min call — Rakshitha shares real `Source` output from a live discovery run, Ramya confirms her merger handles it without changes needed.

---

### Phase 2 — Extraction vs. Reconciliation

**Rakshitha's tasks (`backend/extraction/`):**
- PDF parser: pull structured fields (labeled values, tables) out of a datasheet using pdfplumber/PyMuPDF
- HTML parser: pull the same overlapping fields out of a product webpage using BeautifulSoup
- VLM extractor: call Groq Vision on spec images/diagrams/nameplates to pull fields text-based parsing can't reach
- Test on the real Allied Motion EnduraMax 75s source set (manufacturer PDF, distributor page, older revision) — it has a genuine, already-documented cross-source conflict, useful for Ramya's phase too

**Ramya's tasks (`backend/reconciliation/`):**
- Source-reliability scoring: rule-based baseline (datasheet > webpage > third-party catalog) plus signal adjustments (recency, specificity, internal consistency)
- Conflict detector: pure-logic comparison across sources for the same attribute (unit-normalized) — flags disagreement without needing an LLM call
- Reconciliation agent: when a conflict is flagged, calls Groq LLM to arbitrate using the scoring as weighted input, producing a `ResolvedField` with a one-sentence reasoning string
- Test entirely on hand-seeded synthetic conflicts first — doesn't need Rakshitha's real extraction output to get started

**Sync checkpoint:** 10-15 min — run Rakshitha's real extracted fields (including the known real conflict) through Ramya's reconciler; confirm it correctly identifies and arbitrates it.

---

### Phase 3 — Enrichment vs. Validation & HITL

**Rakshitha's tasks (`backend/enrichment/`):**
- Vector store: build a small Chroma index over 5-10 other product docs, embedded locally with sentence-transformers (no API cost, no rate limit)
- RAG agent: given a missing field, retrieve top-k relevant chunks, ask Groq LLM to extract the value if present, tag the result `status: "enriched"` with a citation to the retrieved source
- Test: deliberately remove 3-5 fields from the demo product's direct sources, confirm enrichment recovers them from the wider corpus

**Ramya's tasks (`backend/validation/`, `backend/hitl/`):**
- Confidence scorer: combines source-reliability weight with the LLM's own certainty signal into a final confidence number per field
- Threshold routing: anything below the confidence threshold gets `status: "needs_review"`
- HITL review queue: a simple structure listing flagged fields, plus an `override()` function letting a human accept/correct a value — which also nudges that source's trust weight up or down slightly
- Test: both on synthetic `ResolvedField` inputs — the schema has existed since Phase 0, so no dependency on Rakshitha's real enrichment output yet

**Sync checkpoint:** 15-20 min — manual end-to-end run for one product, real data throughout: discover → collect → extract → reconcile → enrich → validate. First real full-chain test.

---

### Phase 4 — Demo Data vs. Knowledge Graph Storage

**Rakshitha's tasks (`data/real/`, `data/synthetic/`):**
- Source and document 1-2 more real products with genuine multi-source specs (repeat the search pattern used for the Allied Motion example)
- Write a synthetic catalog generator: produces realistic fake product records with deliberately injected conflicts and missing fields, so the batch demo's conflict/enrichment rates are controllable rather than random
- Assemble a mixed catalog (real + synthetic, 10-20 products) covering both discovery-only and discovery+upload scenarios
- Pure data work — zero dependency on anyone's code this phase

**Ramya's tasks (`backend/storage/`):**
- KG schema: SQLite tables for products, attributes, values, sources, with edges carrying confidence and reasoning as properties
- Writer: takes a `ResolvedField` and persists it into the graph structure
- Query functions: fetch a product's full record, or a single attribute's full evidence trail, for the frontend to consume
- Test against synthetic `ResolvedField` records — schema-driven, doesn't block on Phase 3's real output being finished

**Sync checkpoint:** 10 min — confirm the KG writer correctly ingests real `ResolvedField` records produced by the Phase 3 chain.

---

### Phase 5 — Batch Mode vs. API Layer

**Rakshitha's tasks (`backend/batch/`):**
- Batch runner: loops the pipeline across the Phase 4 catalog (10-20 products)
- Aggregation: computes conflict rate, enrichment rate, and HITL flag rate across the batch into a consistency report
- Built against the *stub* `pipeline.py` (a simple hardcoded chain call) — swaps to the real orchestration once Phase 6 lands, with no rewrite needed
- Cache results during dev/testing to stay well inside Groq's free-tier rate limits

**Ramya's tasks (`backend/api/`):**
- FastAPI routes: expose the pipeline, KG queries, and HITL queue as REST endpoints for the frontend
- Built against her own already-real storage/validation code — no dependency on Rakshitha's batch runner

**Sync checkpoint:** 10 min — confirm batch runner and API layer agree on data shapes where they'll eventually connect (e.g. batch results being queryable via API).

---

### Phase 6 — Orchestration (Real Integration)

**Ramya's tasks (`backend/pipeline.py`, sole editor):**
- Wire the real chain: discover → collect → extract → reconcile → enrich → validate → write to KG, swapping each stub call for the real function one at a time (not a single big-bang merge)
- Handle both demo workflows: discovery-only (Workflow A) and discovery+upload (Workflow B) as input variations to the same chain

**Rakshitha's tasks:** available to fix her own functions if a mismatch surfaces during wiring, but never edits `pipeline.py` herself — she reports issues, Ramya adjusts the wiring or messages back what needs to change.

**Exit criteria:** pipeline runs end-to-end on real data, both demo scenarios, 2-3 real products, via direct function calls.

---

### Phase 7 — Frontend Components (Parallel, No Overlap)

**Rakshitha's tasks (`frontend/components/`):**
- `DiscoveryView.tsx` — shows the discovery process live (this is Demo 1's hero moment — "we gave it three words and it found the data itself")
- `KGVisualization.tsx` — visual view of the product → attribute → source graph
- `BatchReport.tsx` — catalog-level consistency report view

**Ramya's tasks (`frontend/components/`):**
- `ConflictEvidenceView.tsx` — click into a field, see source, confidence, reasoning, alternate values
- `HITLQueue.tsx` — review queue UI with accept/override buttons
- `UploadPanel.tsx` — file upload UI for Demo 2, wired to her `upload_handler.py`

Both sides build against mocked API JSON (hardcoded, matching the schema) rather than waiting for Phase 5's real endpoints to be live — fully decoupled from backend timing.

---

### Phase 8 — Frontend Integration

**Rakshitha's tasks (`frontend/pages/index.tsx`, sole editor):**
- Assemble all 6 components (her 3 + Ramya's 3) into the final demo page
- Support both Demo 1 (discovery-only) and Demo 2 (discovery+upload) flows in the UI
- Starts against mocked components, swaps in Ramya's real ones as they arrive — no rewrite needed

**Ramya's tasks:** hand off finished components as they're ready; never pushes to `index.tsx` herself.

**Exit criteria:** full click-through works for both demo scenarios, no manual restarts.

---

### Phase 9 — Demo Hardening
**Who: Both, jointly**

- Run both live demos repeatedly, fix any breakage under repetition
- Cache/pre-load demo product and upload results so the live run is deterministic
- Record a fallback video for each demo scenario, in case live extraction/search/API calls flake on stage
- Rehearse the pitch, timed, twice — lead with real-world stakes, walk outcome-by-outcome, name the hardest technical problem explicitly

---

## 5. Interface Contract (what actually crosses the boundary)

```python
# Rakshitha's functions — Ramya's code calls these, never edits them:
discover(mpn: str, brand: str, description: str) -> list[Source]
extract_pdf(source: Source) -> list[Field]
extract_html(source: Source) -> list[Field]
extract_image(source: Source) -> list[Field]
enrich(missing_field: Field, corpus) -> ResolvedField | None

# Ramya's functions — Rakshitha's code calls these, never edits them:
merge_sources(discovered: list[Source], uploaded: list[Source]) -> list[Source]
reconcile(fields: list[Field]) -> ResolvedField
validate(field: ResolvedField) -> ResolvedField
```
As long as these signatures hold, either person can freely change what's inside their own functions without touching the other's files.

---

## 6. Git Workflow

- Branches: `rakshitha-dev`, `ramya-dev` — merge to `main` at each phase's sync checkpoint, not continuously
- Pull `main` into your branch before pushing; never merge directly on `main`
- A conflict outside the 3 shared files means someone edited outside their phase's file scope — resolve the cause, not just the diff
- Commit prefix by feature: `[discovery]`, `[reconciliation]`, `[kg]`, `[hitl]`, `[frontend]`

---

## 7. Feature Balance

| | Rakshitha | Ramya |
|---|---|---|
| Backend features | Discovery, Extraction, Enrichment, Data, Batch (5) | Collector, Reconciliation, Validation+HITL, Storage, API (5) |
| Frontend components | 3 | 3 |
| Sole-owned shared file | `index.tsx` | `pipeline.py` |
| Joint file (Phase 0 only) | `schema.py` | `schema.py` |

---

## 8. Scope Discipline

**In (MVP):** discovery agent (web search + catalog fallback), 3 source types (PDF, HTML, image), optional upload merge, all downstream agents, KG output, HITL queue, batch mode across a small catalog — all on the free stack in Section 1.

**Cut (do not build):** model fine-tuning, hosted/production graph database, auth/multi-tenancy, arbitrary document format support, deep agent-framework comparison shopping, anything requiring a paid API tier.
