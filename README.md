# Police OS — Daily Detective Coding Game

## Structure

```
backend/
  schemas.py                  Shared Pydantic contracts (CaseFile, PlayerState, layered Suspect, CRAG, sandbox, leaderboard)
  cache.py                     Redis-or-in-memory cache/counter abstraction (state, eval cache, rate limits)
  state_store.py               Case/player persistence + leaderboard & streak tracking, built on cache.py
  rate_limit.py                Fixed-window rate limiter dependency for the LLM/compute-costing endpoints
  leaderboard.py               GET /api/leaderboard/{case_id}, GET /api/players/{player_id}/stats
  llm_client.py                Shared OpenRouter/HF client: structured JSON output + streaming, with model fallback
  main.py                      FastAPI app, wires all routers together
  crag/
    evaluator.py               Step 1+2: retrieval + strict grading LLM (temp=0), response-cached
    generator.py                Step 3: persona LLM (temp=0.7) - full-response and streaming variants
    interrogation.py            Orchestrates evaluator -> generator -> layered alibi progression -> leaderboard -> hints
    hints.py                     Softens the evaluator's internal reasoning into a player-safe nudge
  sandbox/
    docker_runner.py            Self-managed Docker execution backend (lazy client init)
    piston_runner.py            Alternative: hosted Piston code-execution API, no Docker dependency
    executor.py                  FastAPI route: picks a backend via SANDBOX_BACKEND, grades tests, rate-limited
    Dockerfile.sandbox          Locked-down image used for every player code run (docker backend only)
  generation/
    daily_case.py                Template injection (2 templates) + programmatic layered-suspect construction
    dataset_generators.py       Deterministic (non-LLM) poisoned dataset generation for both templates

frontend/src/
  store/useGameStore.js         Zustand store: SSE streaming, layered-alibi state, rate-limit notices, leaderboard fetch
  components/os/
    PoliceOS.jsx                 Window manager shell + taskbar (4 apps)
    Window.jsx                   Draggable/focusable window chrome
  components/apps/
    DatabaseTerminal.jsx         Monaco-based coding sandbox (App 1)
    EvidenceBoard.jsx            Dynamic evidence/suspect/layer board (App 2)
    SecureMessenger.jsx          CRAG-backed interrogation chat with live token streaming (App 3)
    Leaderboard.jsx              Daily leaderboard + player streak (App 4)
  styles/theme.css               Dark case-file OS theme (CSS variables)
```

See also: **DEPLOYMENT.md** (how to ship this) and **IMPROVEMENTS.md** (what to build next).

## LLM provider

All LLM calls go through `backend/llm_client.py`, which talks to
**OpenRouter** by default (one key, access to Claude/Llama/Gemini/etc.,
OpenAI-compatible endpoint). **Hugging Face Inference Providers** works as a
drop-in alternative — swap two lines in `.env` (`LLM_BASE_URL` + token var),
nothing else changes. Per-role models (`EVALUATOR_MODEL`, `GENERATOR_MODEL`,
`NARRATIVE_MODEL`) are independently configurable, since the strict grader
and the in-character dialogue model want different tradeoffs. See
`.env.example`.

## Key architectural decisions

- **CRAG is two LLM calls, not one.** The evaluator runs at `temperature=0.0`
  with a forced Pydantic schema and only ever sees evidence the player has
  actually unlocked — it can't be argued into crediting invented evidence.
  The persona generator is a separate call at `temperature=0.7`, and its
  system prompt is entirely rebuilt from the evaluator's verdict, so it
  can't "go easy" on the player out of narrative sympathy.

- **Data-poisoning datasets are deterministic code, not LLM output.**
  `dataset_generators.py` is the single source of truth for both the
  poisoned records *and* the `expected_cleaned_count` / `expected_answer`
  values in the challenge's unit tests, so the two can never drift apart.
  Only the crime narrative wrapped around the fixed template is
  LLM-generated in `daily_case.py`.

- **Sandbox isolation.** Every submission gets its own container: no
  network, read-only rootfs, memory/PID/CPU limits, and `remove=True` so
  nothing persists between runs. The player only writes two functions
  (`clean_data`, `solve`); the harness in `docker_runner.py` handles all
  file I/O and result serialization so there's no path for the player's
  code to reach outside `/data`.

- **One Zustand store, three windows.** `useGameStore` is the single
  source of truth for case state, unlocked evidence, solved challenges,
  and chat history. This is what makes solving a coding challenge in the
  Terminal instantly light up a new pin on the Evidence Board and unlock
  new leverage in the Messenger, with no direct window-to-window wiring.

## Running locally

```bash
# Backend
cd backend
pip install -r requirements.txt
docker build -f sandbox/Dockerfile.sandbox -t police-os-sandbox:python3.11 .
cp .env.example .env   # fill in OPENROUTER_API_KEY (or HF_TOKEN); optionally set REDIS_URL
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Trigger the first case before opening the OS:

```bash
curl -X POST http://localhost:8000/api/admin/generate-daily-case
```

## Not yet wired (left as clearly-marked seams)

- `GET /api/case/current` (used by `useGameStore.initSession`) — a thin
  read endpoint over `state_store.get_case_file` / `get_player_state` that
  merges them into the shape the frontend expects. Straightforward to add
  once you decide how `player_id` is issued (auth, anonymous session, etc).
- Real persistence — `state_store.py` is in-memory on purpose; swap in
  Redis (session state) + Postgres (case archive) without touching callers.
- Cron scheduling for `generate_daily_case` — currently a manual admin
  trigger; wire to APScheduler/Celery beat/cloud scheduler in prod.
