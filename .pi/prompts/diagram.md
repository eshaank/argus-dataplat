---
description: Generate or update project diagrams by scanning actual code — architecture, API, services, infrastructure
argument-hint: <type> [--update]
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Generate Diagram

Scan the actual project and generate/update diagrams based on what exists in code.

**Type:** $ARGUMENTS

Available types:
- `architecture` — System overview: frontend, backend, external APIs, data flow → updates `project-docs/ARCHITECTURE.md`
- `api` — API routes map: all backend endpoints grouped by router → updates `project-docs/ARCHITECTURE.md`
- `services` — External service clients (e.g. Polygon, Massive) and how the backend uses them → updates `project-docs/ARCHITECTURE.md`
- `infrastructure` — Deployment topology: ports, containers (if any) → updates `project-docs/INFRASTRUCTURE.md`
- `all` — Generate all diagram types

If `--update` is passed, replace existing diagrams in-place. Otherwise, show the diagram and ask before writing.

## Diagram Format

**ALL diagrams use ASCII box-drawing characters.** No Mermaid, no SVG. ASCII works in every terminal and markdown renderer.

```
Box characters: ┌ ┐ └ ┘ │ ─ ├ ┤ ┬ ┴ ┼
Arrows: → ← ↑ ↓ ──> <── ───>
```

---

## Type: `architecture`

Scan the project and generate a system overview diagram.

### What to scan:

1. **Frontend** — `frontend/src/` (React/Vite)
   ```bash
   find frontend/src/ -name "*.ts" -o -name "*.tsx" 2>/dev/null | head -50
   ```

2. **Backend entry** — FastAPI app and router registration
   ```bash
   grep -rn "include_router\|FastAPI\|APIRouter" backend/app/ 2>/dev/null
   ```

3. **Backend routes** — FastAPI route decorators
   ```bash
   grep -rn "@router\.\(get\|post\|put\|delete\|patch\)\|@app\.\(get\|post\|put\|delete\|patch\)" backend/app/ 2>/dev/null
   ```

4. **External API usage** — HTTP clients and service modules
   ```bash
   grep -rl "httpx\|requests\|fetch" backend/app/ 2>/dev/null
   ls backend/app/services/ 2>/dev/null
   ```

5. **Frontend API client** — how the frontend calls the backend
   ```bash
   grep -rn "api\.\|fetch\|getPriceChart\|getCompany" frontend/src/ 2>/dev/null
   ```

6. **Config** — ports and env
   - `frontend/vite.config.ts` or package.json scripts (dev port, e.g. 5173)
   - `backend/app/config.py` or main (port 8000)

### Generate the diagram:

Adapt to what exists. Example for this stack (no database):

```
┌─────────────────────────────────────────────────────────────────┐
│                     FINANCE DASHBOARD                             │
│                                                                   │
│   ┌─────────────┐   HTTP (VITE_API_BASE_URL)  ┌─────────────┐    │
│   │   Browser   │────────────────────────────>│  FastAPI    │    │
│   │   (React)   │   GET /api/...               │  :8000      │    │
│   │  :5173      │<────────────────────────────│             │    │
│   └─────────────┘   JSON                      └──────┬──────┘    │
│                                                       │           │
│                                            HTTPS      │           │
│                                    ┌──────────────────┼──────────┐
│                                    ▼                  ▼           │
│                            ┌─────────────┐   ┌─────────────┐     │
│                            │ Polygon.io  │   │ Massive API │     │
│                            │ (price,     │   │ (fundamentals,│   │
│                            │  company)   │   │  short, etc) │     │
│                            └─────────────┘   └─────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### Where to write:

Replace or add a `## System Overview` diagram in `project-docs/ARCHITECTURE.md`. Update service responsibilities and data flow from findings.

---

## Type: `api`

Scan backend route definitions and generate an API routes map.

### What to scan:

```bash
# FastAPI routers — decorators and prefix
grep -rn "@router\.\(get\|post\|put\|delete\|patch\)" backend/app/routers/ 2>/dev/null
grep -rn "include_router\|prefix=" backend/app/main.py 2>/dev/null

# Inline routes on app (if any)
grep -rn "@app\.\(get\|post\|put\|delete\|patch\)" backend/app/ 2>/dev/null
```

### Generate the diagram:

```
API Routes Map (Backend)
========================

  /api/
  ├── market-indices     GET   → routers/market_indices.py
  ├── economic-data      GET   → routers/economic_data.py
  ├── upcoming-events    GET   → routers/upcoming_events.py
  ├── inside-days        GET   ?ticker=  → routers/inside_days.py
  ├── price-chart        GET   ?ticker=&timeframe=  → routers/price_chart.py
  ├── company/details   GET   ?ticker=  → routers/company.py
  ├── fundamentals/...   GET   ?ticker=  → routers/fundamentals.py
  └── health             GET   → main.py (or health router)
```

List actual paths and routers from the scan. Use `/api/` prefix as in [project-docs/ARCHITECTURE.md](project-docs/ARCHITECTURE.md).

### Where to write:

Add/update an `## API Routes` (or similar) section in `project-docs/ARCHITECTURE.md`.

---

## Type: `services`

Map external API clients and how the backend uses them (no database in this project).

### What to scan:

```bash
# Service modules and HTTP calls
ls backend/app/services/ 2>/dev/null
grep -rn "httpx\|requests\|AsyncClient\|get\|post" backend/app/services/ 2>/dev/null

# Which routers use which services
grep -rn "from app.services\|import.*polygon\|import.*massive" backend/app/ 2>/dev/null
```

### Generate the diagram:

```
External Services
==================

  backend/app/services/
  ├── polygon.py    → Polygon.io (company details, OHLC bars)
  ├── massive.py    → Massive API (fundamentals, short interest, float)
  └── (mock_data)   → In-memory mock (market indices, economic data, events)

  Routers → Services:
    price_chart, inside_days, company  → polygon
    fundamentals                       → massive
    market_indices, economic_data, upcoming_events → mock_data
```

### Where to write:

Add/update a `## External Services` or `## Data Sources` section in `project-docs/ARCHITECTURE.md`.

---

## Type: `infrastructure`

Scan deployment and run configuration.

### What to scan:

1. **`.env.example`** — ports, API keys (no values), any deployment vars
2. **`Dockerfile`** (if present) — what is containerized
3. **`docker-compose.yml`** (if present)
4. **`vercel.json`** or other host config (if present)
5. **Ports** — frontend 5173, backend 8000 (from ARCHITECTURE.md or config)

```bash
grep -n "PORT\|5173\|8000\|VITE_API_BASE_URL" .env.example frontend/vite.config.ts backend/app/main.py 2>/dev/null
ls Dockerfile docker-compose.yml vercel.json 2>/dev/null
```

### Generate the diagram:

Adapt to what exists (e.g. local dev only, or Vercel + single backend):

```
Infrastructure
==============

  Local development:
    Frontend:  npm run dev     → http://localhost:5173
    Backend:   uv run uvicorn  → http://localhost:8000

  (If Docker/Vercel: add boxes for containers or serverless.)
```

### Where to write:

Replace or add `## Environment Overview` (or similar) in `project-docs/INFRASTRUCTURE.md`.

---

## Type: `all`

Run in sequence: architecture → api → services → infrastructure.

---

## After Generating

1. Show the generated diagram(s) to the user
2. If `--update` was passed: write directly to the docs
3. If not: ask before writing to `project-docs/`
4. Optionally add a short changelog line with today's date
5. Report what was generated (architecture, api, services, infrastructure) and which files were updated
