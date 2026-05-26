# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Backend — run dev server (hot reload)
uvicorn server.main:app --reload --host 0.0.0.0 --port 8000

# Backend — install dependencies
pip install -r requirements.txt

# Frontend — dev server (port 5173, proxies /api to :8000)
cd web && npm run dev

# Frontend — build production dist
cd web && npm run build

# Frontend — install dependencies
cd web && npm install

# Frontend — build when changing .env.production (updates VITE_API_URL)
cd web && npm run build

# Backend — PyInstaller single-file exe packaging
pyinstaller Tender.spec

# Docs — serve docsify documentation site (standalone, not via main app)
docsify serve docs

# Windows — one-click start
run.bat

# macOS/Linux — one-click start
bash start.sh
```

## Architecture

Monorepo with two main directories: `server/` (Python FastAPI) and `web/` (Vue 3 + Vite). The frontend is built to `web/dist/` and served by the FastAPI backend as static files. No separate frontend server in production.

### Backend (`server/`)

```
server/
├── main.py          # FastAPI app, lifespan, SPA fallback, tray/restart
├── config.py        # pydantic-settings (reads .env), get_settings()
├── models.py        # Pydantic request/response models
├── api/             # Route handlers (one file per domain)
│   ├── auth.py      # JWT login/logout/me
│   ├── kb.py        # Knowledge base CRUD, upload, folder scan
│   ├── rag.py       # RAG query endpoint
│   ├── bid.py       # Bid parse/generate/stream/match/plagiarism/violation (largest file)
│   ├── admin.py     # User management, config, stats, model switch, restart
│   ├── price.py     # Price formula analysis and calculation
│   └── checklist.py # Bid material checklist generation
├── core/
│   ├── generator/llm.py     # LLM abstraction (get_generator) — DeepSeek/DashScope/OpenAI/MiniMax/Ollama/Mock
│   ├── embedder/embedder.py # Embedding abstraction (get_embedder) — Ollama/DashScope/BGE/M3E/Mock
│   ├── chunker/chunker.py   # Text chunking (by chars / paragraphs)
│   ├── parser/              # File parsing (PDF/DOCX/XLSX/PPTX/MD/TXT)
│   ├── retriever/           # ChromaDB vector retrieval
│   ├── reviewer/            # Bid quality review
│   └── glossary.py          # Built-in bidding glossary (injected into ChromaDB at startup)
├── data/
│   └── glossary_data.py     # 44 glossary terms (loaded by glossary.py at startup)
├── db/
│   ├── sqlite.py     # SQLite tables (users, documents, chunks, bid_versions, etc.)
│   ├── chromadb.py   # ChromaDB vector store helpers
│   └── violation_db.py # Disqualification rules DB
└── tools/
    ├── bid_analyzer.py       # Historical bid analysis
    ├── plagiarism_checker.py # Bid content plagiarism detection
    └── violation_checker.py  # Bid disqualification rule checking
```

**Key patterns:**
- **LLM providers** use a factory (`get_generator()` in `core/generator/llm.py`), chosen by `LLM_PROVIDER` env var. All expose `generate()` and optionally `generate_stream()`.
- **Embedding providers** use the same factory pattern (`get_embedder()` in `core/embedder/embedder.py`), chosen by `EMBED_PROVIDER` env var.
- **Settings** via pydantic-settings (`config.py`), loaded from `.env` at project root. `update_env()` persists runtime config changes to `.env`.
- **Dual DB**: SQLite for metadata (documents, chunks, users, bid versions), ChromaDB for vector search. Chunks are stored in both (text+metadata in SQLite, vectors in ChromaDB).
- **Startup lifecycle**: `main.py` lifespan initializes SQLite, violation DB, built-in bid templates, and glossary (embeds 44 industry terms into ChromaDB).
- **PyInstaller support**: `main.py` handles `sys.frozen`/`_MEIPASS` for packaged exe deployment. `runtime_hook.py` finds the real Python site-packages at runtime; `sitecustomize.py` patches chromadb to avoid triggering `sentence_transformers` imports. Windows tray icon (pystray) for background operation.
- **SSE streaming**: `bid.py`'s `/api/bid/generate/stream` uses `StreamingResponse` (text/event-stream) for token-by-token bid generation; the frontend consumes it via a fetch reader loop.

### Frontend (`web/`)

```
web/src/
├── main.js          # App entry — Vue 3 + Pinia + Element Plus + Router
├── router/index.js  # Routes: /login (guest), / (auth required) with children:
│                    #   /dashboard, /kb, /bid, /bid-analyze, /price, /settings
├── api/index.js     # Axios instance with named API modules (auth, kb, rag, bid, admin, price, checklist)
├── pages/           # One Vue file per route
│   ├── Login.vue
│   ├── Dashboard.vue
│   ├── KnowledgeBase.vue
│   ├── BidGenerate.vue       # Largest page (~85KB) — bid creation workflow
│   ├── BidAnalyze.vue
│   ├── PriceAnalyze.vue
│   └── Settings.vue
├── components/      # Shared components (BidChecklistDialog.vue)
├── layouts/         # MainLayout.vue (sidebar + header + router-view)
└── stores/          # Pinia stores (auth.js + kb.js for token/user and KB state)
```

- **Vite dev server** (port 5173) proxies `/api` to `localhost:8000`. Production uses `VITE_API_URL` from `.env.production`.
- **SPA routing**: All non-API, non-asset paths fall back to `index.html` via `main.py`'s `spa_fallback`. The `docs/` directory (Docsify documentation site) is also served as static files.
- **Auth**: JWT token stored in Pinia + localStorage. Axios interceptor redirects to `/login` on 401.

### Configuration

All configuration is via `.env` at project root. Key vars:

| Var | Default | Purpose |
|-----|---------|---------|
| `LLM_PROVIDER` | `ollama` | LLM backend: ollama/dashscope/openai/minimax/deepseek/mock |
| `EMBED_PROVIDER` | `ollama` | Embedding backend: ollama/dashscope/bge/m3e/mock |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DEBUG` | `true` | Debug mode |
| `SECRET_KEY` | `tender-secret-key-...` | JWT signing key |
| `OLLAMA_MODEL` | `qwen3:4b` | Local LLM model (in .env) |
| `OLLAMA_EMBED_MODEL` | (same as OLLAMA_MODEL) | Local embedding model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama service URL |
| `DASHSCOPE_MODEL` | `qwen-turbo` | DashScope LLM model |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model |
| `MINIMAX_MODEL` | `MiniMax-Text-01` | MiniMax model |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek model |
| `MAX_FILE_SIZE` | `50` | Upload file size limit (MB) |
| `COMPANY_NAME` | `投标单位名称` | Company name on bid covers |

### API Routes

All under `/api/`:
- `/api/auth/*` — Login, logout, current user
- `/api/kb/*` — Knowledge base document CRUD, upload, folder scan, chunks
- `/api/rag/query` — RAG question answering (POST)
- `/api/bid/*` — Parse bid requirements, generate bid document (streaming and batch), match check, plagiarism check, violation check, historical section analysis
- `/api/admin/*` — User CRUD, stats, config, model config, restart
- `/api/price/*` — Parse scoring formula, calculate optimal price, save/history
- `/api/checklist/*` — Generate material checklist, CRUD items, export
