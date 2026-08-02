# ProvenIQ
### AI-Powered Product Intelligence for Industrial Commerce

> Turn a manufacturer part number, brand, and short description into a fully structured, source-traceable, commerce-ready product record — autonomously.

---

## Architecture

```
User Input (MPN + Brand + Description)
        │
        ▼
  Discovery Agent  →  PDF / HTML / Image sources
        │
        ▼
  Unified Source Collector  (+ optional user uploads)
        │
        ▼
  Extraction Agent  (pdfplumber · BeautifulSoup · Groq Vision)
        │
        ▼
  Reconciliation Agent  (conflict detection + Groq LLM arbitration)
        │
        ▼
  Enrichment Agent  (RAG · sentence-transformers · Chroma)
        │
        ▼
  Validation Agent  (confidence scoring · HITL routing)
        │
        ▼
  Knowledge Graph (SQLite)  →  Commerce-ready Product Profile
        │
        ▼
  HITL Review Queue  (accept / override → adjusts trust scores)
```

---

## Quick Start

### 1. Clone & activate the virtual environment

```powershell
git clone <repo-url>
cd proveniq

# Create venv (already done if you see `uni/`)
python -m venv uni
.\uni\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Set up environment variables

```powershell
Copy-Item .env.example .env
# Edit .env and add your GROQ_API_KEY
```

Get a free Groq API key at https://console.groq.com

### 3. Run the smoke test (Phase 0 / 0.5 stubs)

```powershell
python smoke_test.py
```

You should see all stub pipeline stages fire and report `✅ Smoke test passed`.

### 4. Start the backend (Phase 5+)

```powershell
uvicorn backend.api.main:app --reload --port 8000
```

### 5. Start the frontend (Phase 7+)

```powershell
cd frontend
npm install
npm run dev
```

---

## Project Structure

```
provenIQ/
├── backend/
│   ├── schema.py              ← Shared data types (LOCKED after Phase 0)
│   ├── pipeline.py            ← Ramya only — pipeline orchestration
│   ├── discovery/             ← Rakshitha
│   ├── collector/             ← Ramya
│   ├── extraction/            ← Rakshitha
│   ├── reconciliation/        ← Ramya
│   ├── enrichment/            ← Rakshitha
│   ├── validation/            ← Ramya
│   ├── hitl/                  ← Ramya
│   ├── storage/               ← Ramya
│   ├── batch/                 ← Rakshitha
│   └── api/                   ← Ramya
├── frontend/
│   ├── components/
│   └── pages/
├── data/
│   ├── real/
│   └── synthetic/
├── smoke_test.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Tech Stack (100% free tier)

| Layer | Choice |
|---|---|
| LLM / VLM | Groq API — Llama 3.3 70B + Llama 3.2 Vision |
| PDF parsing | pdfplumber / PyMuPDF |
| HTML parsing | BeautifulSoup |
| Web search | duckduckgo-search (no API key needed) |
| Embeddings | sentence-transformers (local, no cost) |
| Vector store | ChromaDB (local embedded) |
| Knowledge graph | SQLite |
| Orchestration | LangGraph |
| Backend | FastAPI |
| Frontend | Next.js / React |

---

## Git Workflow

- Branches: `rakshitha-dev`, `ramya-dev` → merge to `main` at each phase sync
- Commit prefix: `[discovery]`, `[extraction]`, `[reconciliation]`, `[kg]`, `[hitl]`, `[frontend]`
- **Never** merge directly on `main`
- A conflict outside your own folder = you've drifted out of scope — resolve the cause
