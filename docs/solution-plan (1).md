# Solution Plan — ProvenIQ
### AI-Powered Product Intelligence for Industrial Commerce

---

## 1. Problem → Solution, one line each

| Problem statement asks for | ProvenIQ delivers |
|---|---|
| **Understand products from limited information** | Product Discovery Agent interprets MPN + brand + short description to form a search strategy for where this product's data would live |
| **Discover and validate relevant information** | Discovery Agent finds manufacturer pages, datasheets, manuals, and distributor sources; a validation step confirms a discovered source is actually about the right product |
| Automate **creation** of product intelligence from limited inputs | Extraction agent (document intelligence + VLM) turns discovered — or optionally uploaded — PDF/HTML/image sources into structured fields |
| Automate **enrichment** | RAG-based enrichment agent fills gaps by retrieving from other product docs, with citation |
| Automate **validation** | Reconciliation + validation agents detect conflicts, score confidence, resolve with reasoning |
| **Traceable outputs** | Every field in the knowledge graph carries source + confidence + justification |
| **Explainability** | HITL queue surfaces exactly what the system is unsure of and why |
| **Scale across catalogs** | Batch orchestration runs the full pipeline across N products |

---

## 2. Solution Overview

ProvenIQ is an **agentic pipeline** that turns minimal product information — a manufacturer part number, brand, and short description — into a structured, source-traceable, commerce-ready product record. By default, the platform works from that minimal input alone: a Product Discovery Agent autonomously finds and retrieves the manufacturer pages, datasheets, manuals, and distributor sources that describe the product. Where an enterprise already holds its own product documentation, those uploads are simply folded into the same evidence pool alongside what the agent discovers — the pipeline downstream (extraction, reconciliation, enrichment, validation) doesn't need to know or care whether a source was found or uploaded.

Autonomous discovery from minimal input is the default behavior; document upload is an optional, additive enhancement, not a separate mode the user has to choose.

```
   USER INPUT
   Manufacturer Part Number + Brand + Short Description
        │
        ▼
   ┌────────────────┐
   │ PRODUCT          │  multi-agent swarm: web-search sub-agent (manufacturer
   │ DISCOVERY AGENT  │  site, datasheets, manuals), catalog sub-agent (trusted
   │                  │  distributor/reference sources) → candidate source list
   └────────┬────────┘
        │
        ▼
   OPTIONAL USER UPLOADS
   PDF datasheet │ product catalog │ image │ manual
        │
        ▼
   ┌────────────────┐
   │ UNIFIED SOURCE   │  merges uploaded docs + discovered sources into a
   │ COLLECTOR        │  single evidence pool; uploads prioritized where
   │                  │  present, public sources still pulled for validation
   └────────┬────────┘
        │
        ▼
   ┌────────────────┐
   │  EXTRACTION      │  doc intelligence (PDF/HTML) + VLM (images)
   │     AGENT        │  → structured fields, tagged by source
   └────────┬────────┘
        │
        ▼
   ┌────────────────┐
   │ RECONCILIATION   │  detects conflicts across sources,
   │     AGENT        │  source-reliability weighted arbitration + reasoning
   └────────┬────────┘
        │
        ▼
   ┌────────────────┐
   │  ENRICHMENT      │  RAG: retrieves from other product docs
   │     AGENT        │  to fill missing fields, cites source
   └────────┬────────┘
        │
        ▼
   ┌────────────────┐
   │  VALIDATION      │  confidence scoring; low-confidence → HITL queue;
   │     AGENT        │  writes final record to knowledge graph
   └────────┬────────┘
        │
        ▼
   Knowledge Graph
   product → attribute → value → source + confidence + reasoning
        │
        ▼
   Commerce-ready Product Profile

   HITL REVIEW QUEUE (flagged fields, human accept/override,
   override adjusts source trust score going forward)
```

**Why an agent-per-stage design:** each stage has a distinct failure mode (discovery = false-positive sources, extraction = parsing errors, reconciliation = conflicting truth, enrichment = hallucination risk, validation = overconfidence) — separating them keeps each one independently debuggable, testable, and demoable, which matters as much for a 5-day build as for the final quality.

---

## 3. Dual Ingestion Workflow

The pipeline supports two ways evidence enters the system, and the user never has to pick one — the system just uses whatever's available.

**Workflow A — Discovery only (primary path):** the user provides minimal input (MPN, brand, short description). The Product Discovery Agent searches manufacturer sites, datasheets, manuals, technical catalogs, and trusted distributor pages, and hands the retrieved PDFs, HTML pages, and images straight into the existing Extraction → Reconciliation → Enrichment → Validation pipeline. This is the default, and the one that most directly answers the hackathon brief's "transform minimal product information" framing.

**Workflow B — Discovery + enterprise uploads:** the user additionally uploads documents the enterprise already holds — internal datasheets, catalogs, manuals, images. These uploads are merged with the Discovery Agent's findings into a single unified evidence pool before extraction begins. Uploaded documents are prioritized where appropriate (they're often the most authoritative, internal, up-to-date source), but the system still searches public sources — not to override the upload, but to validate it, catch discrepancies, and enrich fields the upload doesn't cover.

Logic, in short:
```
if uploads exist:
    evidence_pool = uploaded_docs + discovered_sources
else:
    evidence_pool = discovered_sources
```
Everything downstream of the Unified Source Collector — extraction, reconciliation, enrichment, validation, HITL, knowledge graph — is identical regardless of which workflow produced the evidence pool. This is what keeps the addition of Workflow B free of added scope: it's a new front door, not a new pipeline.

---

## 4. Outcome-by-Outcome Proof Plan

**Outcome 0 — Understand products, discover and validate relevant information**
Demo: give the system only an MPN, brand, and short description → Discovery Agent surfaces the manufacturer datasheet, a distributor page, and a spec image on its own, before any extraction happens.

**Outcome 1 — Generate structured intelligence from limited inputs**
Demo: feed a product with only a datasheet PDF and one image (no webpage) → show full structured record generated anyway, gaps clearly marked as enriched/inferred vs. directly extracted.

**Outcome 2 — Improve data quality and consistency**
Demo: feed a product where datasheet and webpage disagree on a spec → reconciliation agent shows both values, states which it trusts and why, cites the exact source line.

**Outcome 3 — Validate and enrich with traceable outputs**
Demo: click into any field in the knowledge graph → see source, confidence score, one-line justification. For an enriched (not directly extracted) field, show the RAG retrieval it pulled from.

**Outcome 4 — Scale across large catalogs**
Demo: run the full pipeline across a batch of 10-20 products → show a catalog-level consistency report (conflict rate, enrichment rate, HITL flag rate) generated in one pass.

---

## 5. Architecture & Stack

| Layer | Choice | Notes |
|---|---|---|
| Product discovery | Web-search API call + LLM query formulation | Interprets MPN/brand/description into search queries; catalog sub-agent covers a pre-loaded reference corpus as a reliable fallback |
| Document intelligence | pdfplumber / PyMuPDF (PDF), BeautifulSoup (HTML) | Layout-aware, not plain-text scraping |
| Vision-language | Vision-capable LLM API call | For spec images, diagrams, nameplates |
| Agent orchestration | LangGraph or hand-rolled agent loop | Pick whichever ships fastest — don't burn a day comparing frameworks |
| Reconciliation logic | LLM + source-reliability scoring (rule-based, signal-adjusted) | See scoring sketch below |
| Enrichment | RAG over small vector store (Chroma/FAISS) of the manufacturer's own docs | Cited, not hallucinated |
| Knowledge graph | Graph-structured JSON/SQLite (product/attribute/value/source nodes, provenance edges) | Visualized, not a full graph DB — right-sized for 5 days |
| HITL | Review queue UI, accept/override, override updates source trust weight | Simple weighted-average update, not real ML |
| Backend | FastAPI | |
| Frontend | Next.js/React | Pipeline view, conflict/evidence view, KG visualization, HITL queue, batch view |
| LLM | Claude/GPT API | Vision-capable model for the VLM step |

**Source-reliability scoring, in brief:** start rule-based (datasheet > webpage > third-party catalog, configurable by product domain), layer in signal adjustments (recency, specificity, internal consistency), output a numeric confidence + one-sentence justification per field. HITL overrides nudge the source's weight going forward — a small, visible feedback loop worth calling out in the pitch as "the system gets more accurate over time."

---

## 6. Build Plan (5 days, 2 people)

| Day | Focus | Exit criteria |
|---|---|---|
| 1 | Spike doc-intelligence + VLM extraction on real sources; lock data model; stub discovery agent's search call | ≥5 comparable fields extracted from PDF, HTML, and image for one product |
| 2 | Build reconciliation + enrichment agents in parallel | Both working on seeded test cases with visible reasoning/citations |
| 3 | Build validation agent + HITL queue; wire all four agents into one pipeline; start KG storage | Single-product flow works end-to-end, low-confidence cases correctly routed to HITL |
| 4 | Batch run across 10-20 products; KG visualization; frontend build | Catalog-level consistency report generated; full UI functional |
| 5 | Pitch polish, fallback recording, rehearsal, cut anything not load-bearing | Pitch rehearsed twice, fallback video ready |

**Role split:** Person A owns extraction + enrichment (doc intelligence, VLM, RAG, demo data prep). Person B owns reconciliation + validation (source scoring, KG storage, HITL, API). Converge on frontend + orchestration wiring day 4.

**Fallback:** cache demo product results ahead of time; have a recorded backup video in case live extraction/API calls flake on stage.

---

## 7. Demo Flow

**Demo 1 — Discovery-only (primary scenario):** the user enters just an MPN, brand, and short description. The Discovery Agent finds the manufacturer datasheet, a distributor page, and a spec image on its own, live. The pipeline then runs its existing conflict-resolution and evidence-trail flow on what it found. This is the opener — "we gave it three words and it found and reconciled real product data" is the strongest first 30 seconds of the pitch.

**Demo 2 — Discovery + upload:** the user uploads a proprietary internal PDF for the same or a different product. The system merges it with publicly discovered sources into one evidence pool, and shows how the uploaded document raises confidence and fills fields the public sources alone didn't cover — while public sources still catch and flag any discrepancy against the upload.

---

## 8. Scope Discipline

**In (MVP, non-negotiable):** discovery agent (web search + catalog fallback), 3 source types (PDF, HTML, image), optional upload merge, all four downstream agents, KG output, HITL queue, batch mode across a small catalog.

**Stretch (only after MVP is solid, day 4+):** 4th source type (CSV/catalog), richer interactive KG visualization, visible trust-score learning curve across the batch run, category-adaptive schema.

**Cut (do not build):** model fine-tuning, production graph database, auth/multi-tenancy, arbitrary document format support, deep agent-framework comparison shopping.

---

## 9. Pitch Framing

Open with the real-world stakes, not the tech stack: a wrong spec (voltage, load rating) in industrial commerce isn't a UX inconvenience — it can mean equipment damage or a safety issue. That's why traceability and HITL aren't nice-to-haves here, they're the actual product requirement. Then walk the demo: autonomous discovery from three words (Outcome 0) → conflict resolution (Outcome 2) → missing-field recovery via VLM (Outcome 1) → click-into-evidence-trail (Outcome 3) → batch/catalog run (Outcome 4). Name the hard technical problem explicitly during the pitch — judges can't always infer difficulty from a smooth demo alone.
