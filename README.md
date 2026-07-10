# Police OS — Daily Detective Coding Game

A daily "Wordle-style" detective game. Every day a fresh case is generated:
a crime, a set of suspects with layered alibis, and coding challenges where
the player cleans a poisoned dataset and runs an algorithm over it to
recover evidence. Cracking a suspect's story means citing real, unlocked
evidence against them in an LLM-powered interrogation chat (CRAG: retrieve
→ grade → generate in character).

It runs as a little in-browser "OS" with four draggable windows: a coding
terminal, an evidence board, an interrogation messenger, and a leaderboard.

---

## Quickstart

```bash
# 1. Backend — from the PROJECT ROOT (the folder containing backend/ and frontend/)
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in OPENROUTER_API_KEY (or HF_TOKEN)
cd ..
uvicorn backend.main:app --reload
```

> ⚠️ That last command must be run from the **project root**, not from
> inside `backend/`. See [Troubleshooting](#troubleshooting) if you hit
> `ModuleNotFoundError: No module named 'backend'`.

```bash
# 2. Generate the first case (backend must already be running)
curl -X POST http://localhost:8000/api/admin/generate-daily-case
```

```bash
# 3. Frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. You should see the desktop with four windows
already populated from today's case.

---

## Project structure

```
backend/
  main.py                      FastAPI app entrypoint, wires all routers together
  case.py                      GET /api/case/current — public read endpoint the frontend
                                 loads on startup (case file + this player's progress)
  schemas.py                   Shared Pydantic contracts (CaseFile, PlayerState,
                                 layered Suspect, CRAG, sandbox, leaderboard)
  cache.py                     Redis-or-in-memory cache/counter abstraction
  state_store.py               Case/player persistence + leaderboard & streak tracking
  rate_limit.py                Fixed-window rate limiter dependency for LLM/compute endpoints
  leaderboard.py               GET /api/leaderboard/{case_id}, GET /api/players/{player_id}/stats
  llm_client.py                Shared OpenRouter/HF client: structured JSON output + streaming
  crag/
    evaluator.py                Step 1+2: retrieval + strict grading LLM (temp=0), cached
    generator.py                 Step 3: persona LLM (temp=0.7) — full-response + streaming
    interrogation.py             Orchestrates evaluator → generator → alibi layers → leaderboard
    hints.py                     Softens the evaluator's reasoning into a player-safe nudge
  sandbox/
    executor.py                  FastAPI routes: serves the poisoned dataset, grades results
                                   the browser already computed, rate-limited
  generation/
    daily_case.py                 Template injection + programmatic layered-suspect construction
    dataset_generators.py        Deterministic (non-LLM) poisoned dataset generation

frontend/
  jsconfig.json                 Enables the "@/..." import alias used throughout src/
  pages/
    _app.js                      Next.js app shell — this is where global CSS must be imported
    index.js                     Generates/persists a player_id, mounts PoliceOS client-only
  src/
    store/useGameStore.js         Zustand store: SSE streaming, layered-alibi state, leaderboard
    lib/pyodideRunner.js          Runs player Python in-browser via Pyodide (WASM)
    components/os/
      PoliceOS.jsx                 Window manager shell + taskbar (4 apps)
      Window.jsx                   Draggable/focusable window chrome
    components/apps/
      DatabaseTerminal.jsx         Monaco-based coding sandbox (App 1)
      EvidenceBoard.jsx            Dynamic evidence/suspect/layer board (App 2)
      SecureMessenger.jsx          CRAG-backed interrogation chat, live token streaming (App 3)
      Leaderboard.jsx              Daily leaderboard + player streak (App 4)
    styles/theme.css               Dark case-file OS theme (CSS variables)
```

See also: **DEPLOYMENT.md** (how to ship this) and **IMPROVEMENTS.md**
(what to build next).

---

## How code execution works (important if you're extending this)

Player code runs **entirely in the browser**, not on the server. There is
no Docker daemon and no third-party code-execution API (e.g. Piston)
anywhere in this project.

1. `DatabaseTerminal.jsx` preloads Pyodide (CPython compiled to
   WebAssembly) as soon as the terminal window opens.
2. On "Run", `useGameStore.runSubmission` fetches the challenge's poisoned
   dataset from `GET /api/sandbox/dataset/{case_id}/{challenge_id}` and
   hands it, along with the player's source, to
   `frontend/src/lib/pyodideRunner.js`.
3. `pyodideRunner.js` executes the player's `clean_data(records)` and
   `solve(cleaned)` functions inside the WASM sandbox — isolated by the
   browser itself, with a 10s client-side timeout — and returns
   `{cleaned_count, answer, error}`.
4. The frontend POSTs **only that result** (never the secret answer key)
   to `POST /api/sandbox/execute`. `backend/sandbox/executor.py` grades it
   against the case file's `unit_tests`, which never leave the server.

This means: no server compute cost for running player code, no API keys
to manage for it, no network latency while it executes, and the backend
can deploy anywhere that runs a plain ASGI app (see DEPLOYMENT.md).

---

## LLM provider

All LLM calls go through `backend/llm_client.py`, which talks to
**OpenRouter** by default (one key, access to Claude/Llama/Gemini/etc. via
an OpenAI-compatible endpoint). **Hugging Face Inference Providers** works
as a drop-in alternative — swap two lines in `.env` (`LLM_BASE_URL` + the
token var), nothing else changes. Per-role models (`EVALUATOR_MODEL`,
`GENERATOR_MODEL`, `NARRATIVE_MODEL`) are independently configurable,
since the strict grader and the in-character dialogue model want
different cost/quality tradeoffs. See `.env.example`.

---

## Key architectural decisions

- **CRAG is two LLM calls, not one.** The evaluator runs at
  `temperature=0.0` with a forced Pydantic schema and only ever sees
  evidence the player has actually unlocked — it can't be argued into
  crediting invented evidence. The persona generator is a separate call
  at `temperature=0.7`, and its system prompt is entirely rebuilt from the
  evaluator's verdict, so it can't "go easy" on the player out of
  narrative sympathy.

- **Data-poisoning datasets are deterministic code, not LLM output.**
  `dataset_generators.py` is the single source of truth for both the
  poisoned records *and* the `expected_cleaned_count` / `expected_answer`
  values in the challenge's unit tests, so the two can never drift apart.
  Only the crime narrative wrapped around the fixed template is
  LLM-generated in `daily_case.py`.

- **Sandbox isolation via the browser, not the server.** See "How code
  execution works" above.

- **One Zustand store, three-plus windows.** `useGameStore` is the single
  source of truth for case state, unlocked evidence, solved challenges,
  and chat history. This is what makes solving a coding challenge in the
  Terminal instantly light up a new pin on the Evidence Board and unlock
  new leverage in the Messenger, with no direct window-to-window wiring.

---

## Environment variables (`backend/.env`)

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Required | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes (or `HF_TOKEN`) | From https://openrouter.ai/keys |
| `LLM_BASE_URL` | Yes | `https://openrouter.ai/api/v1` by default |
| `HF_TOKEN` | Alt. to OpenRouter | From https://huggingface.co/settings/tokens |
| `EVALUATOR_MODEL` | No | Defaults to a small/cheap model — this call is strict grading, not creative |
| `GENERATOR_MODEL` | No | Used for case/narrative generation |
| `NARRATIVE_MODEL` | No | Used for in-character suspect dialogue |
| `FALLBACK_MODEL` | No | Used if the primary model call fails |
| `APP_URL` | No | Your deployed frontend URL (sent as a header to some providers) |
| `REDIS_URL` | No locally, **yes** on serverless | Without it, state is in-memory and resets on restart/redeploy |

Frontend (`frontend/.env.local`, optional):

| Variable | Required | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | No | Defaults to `http://localhost:8000`; set this to your deployed backend URL in production |

---

## Running locally, step by step

```bash
# From the project root
cd backend
pip install -r requirements.txt
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY (or HF_TOKEN)

cd ..
uvicorn backend.main:app --reload
```

Leave that running, then in a second terminal:

```bash
curl -X POST http://localhost:8000/api/admin/generate-daily-case
```

You should get back a JSON case file. Then:

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000`. The Database Terminal will show "Loading
Python runtime…" for a couple of seconds on first load (Pyodide is
downloading its WASM runtime from a CDN) before the Run button becomes
clickable.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'backend'` on `uvicorn` startup**
You're running uvicorn from inside the `backend/` folder. `main.py` uses
absolute imports (`from backend.crag...`), which only resolve if your
working directory is the project root. Fix:
```bash
cd <project-root>          # the folder that CONTAINS backend/ and frontend/
uvicorn backend.main:app --reload
```

**Vercel: `Couldn't find any 'pages' or 'app' directory`**
Already fixed in this version — `frontend/pages/_app.js` and
`frontend/pages/index.js` are included. If you still see this, double
check your Vercel project's "Root Directory" setting is `frontend`, not
the repo root.

**Vercel/webpack: `Global CSS cannot be imported from files other than
your Custom <App>`**
Already fixed — `theme.css` is imported in `pages/_app.js`, not in a
regular component. If you add more global stylesheets later, they must
also be imported there (or converted to CSS Modules, e.g.
`Window.module.css`, which *can* be imported from any component).

**Frontend stuck on "Loading case data…" forever**
Almost always means `GET /api/case/current` returned an error. Common
causes:
- No case has been generated yet — run the `curl -X POST
  .../api/admin/generate-daily-case` step above.
- `NEXT_PUBLIC_API_BASE` isn't pointing at your backend (check browser
  devtools → Network tab for the failing request).
- CORS: `backend/main.py`'s `allow_origins` needs to include your actual
  frontend origin in production (see DEPLOYMENT.md).

**"Loading Python runtime…" never finishes / Run button stays disabled**
Pyodide loads from `cdn.jsdelivr.net` at runtime — check that the CDN
isn't blocked by a network policy, ad blocker, or restrictive CSP.

**429 / "Slow down" messages**
Rate limiting is intentional (`backend/rate_limit.py`) to bound LLM and
submission-grading cost per player. Not a bug.

---

## Not yet wired (left as clearly-marked seams)

- Real persistence — `state_store.py` is in-memory by default; swap in
  Redis (session state) + Postgres (case archive) without touching
  callers. **Required** if you deploy the backend to a serverless
  platform (see DEPLOYMENT.md).
- Cron scheduling for `generate_daily_case` — currently a manual admin
  trigger; wire to APScheduler/Celery beat/cloud scheduler in prod.
- Auth / real player identity — `player_id` is currently a random UUID
  generated client-side and stored in `localStorage`
  (`frontend/pages/index.js`). Fine for an anonymous daily-puzzle game;
  swap for real auth if you need cross-device progress.
