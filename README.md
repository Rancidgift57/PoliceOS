```
██████╗  ██████╗ ██╗     ██╗ ██████╗███████╗       ██████╗ ███████╗
██╔══██╗██╔═══██╗██║     ██║██╔════╝██╔════╝      ██╔═══██╗██╔════╝
██████╔╝██║   ██║██║     ██║██║     █████╗  █████╗██║   ██║███████╗
██╔═══╝ ██║   ██║██║     ██║██║     ██╔══╝  ╚════╝██║   ██║╚════██║
██║     ╚██████╔╝███████╗██║╚██████╗███████╗      ╚██████╔╝███████║
╚═╝      ╚═════╝ ╚══════╝╚═╝ ╚═════╝╚══════╝       ╚═════╝ ╚══════╝
      एक जांच रोज़ाना · A NEW CASE FILE EVERY MIDNIGHT, IST
```

<div align="center">

**Clean poisoned data. Break real alibis. Solve the case before midnight.**

A browser-native detective OS where every case is a real coding challenge — you write
Python, it runs, and only *correct* evidence is admissible in interrogation. No shortcuts,
no server-side execution, no LLM you can out-argue.

`FastAPI` · `Next.js` · `Pyodide (WASM)` · `Turso (libSQL)` · `OpenRouter` · `Zustand`

</div>

---

## Table of Contents

1. [What is this](#what-is-this)
2. [What it looks like](#what-it-looks-like)
3. [Features](#features)
4. [Quickstart](#quickstart)
5. [How a day in the game actually works](#how-a-day-in-the-game-actually-works)
6. [Architecture deep dive](#architecture-deep-dive)
7. [Project structure](#project-structure)
8. [Environment variables](#environment-variables)
9. [Key design decisions](#key-design-decisions)
10. [Troubleshooting](#troubleshooting)
11. [Roadmap / not yet wired](#roadmap--not-yet-wired)

---

## What is this

**Police OS** is a daily, Wordle-style detective game disguised as a retro investigation
terminal. Every day at **midnight IST**, a fresh case is generated: a victim, a crime
scene, a short riddle about the environment, two suspects with layered alibis, and a
data-cleaning coding challenge standing between you and the evidence that breaks them.

You don't click through a story — you **earn** every line of dialogue:

```
   clean_data(records)  →  solve(cleaned)  →  🔓 evidence unlocked
            │
            ▼
   cite that evidence, by name, to a suspect
            │
            ▼
   their alibi layer breaks → next layer, or full confession
            │
            ▼
   every suspect broken  →  CASE CLOSED
```

Vague accusations get denied. Evidence you haven't unlocked yet doesn't exist as far as
the suspect is concerned. There is no dialogue tree to click through — you have to
actually be right.

---

## What it looks like

The whole game lives inside one in-browser "OS" — draggable, focusable windows over a
dark, monospace, case-file aesthetic with a thin saffron–white–green rule as the only
nod to where its heart is:

```
┌─ OPERATION PRASHIKSHAN — CASE_TUTORIAL ───────────────────────────  MH-DET-7801  Nikhil  [Sign out]

┌─ DB_TERMINAL // SANDBOX ──────────┐ ┌─ EVIDENCE_BOARD ─────────┐ ┌─ CASE_FILES ─────────┐
│ Pehchaan 1: Clean the Duty Log    │ │ SCENE BRIEFING           │ │ TRAINING FILE         │
│                                    │ │ Seven names stand watch  │ │  ▶ Operation          │
│ 1  def clean_data(records):       │ │ on paper, but only five  │ │    Prashikshan        │
│ 2      cleaned = []               │ │ stood watch in fact...   │ │    [START HERE]       │
│ 3      for r in records:          │ │                          │ │                       │
│ 4          if not isinstance(...) │ │ EVIDENCE (1/1 unlocked)  │ │ NEW CHALLENGES        │
│ 5              continue           │ │  ☑ Cleaned duty log      │ │  Operation Bijli      │
│ ...                                │ │                          │ │  Operation Trinetra   │
│                                    │ │ SUSPECTS                 │ │                       │
│ [ RUN AGAINST EVIDENCE ]  ✔ PASSED│ │  Head Constable Bhonsle  │ │ PENDING CHALLENGES    │
└────────────────────────────────────┘ │  FULLY BROKEN            │ │  No unfinished cases  │
                                        └──────────────────────────┘ └───────────────────────┘
┌─ SECURE_MESSENGER ─────────────────────────────────┐ ┌─ LEADERBOARD ─────────────────────┐
│ Head Constable Bhonsle          Story layer 1/1     │ │ #1  MH-DET-7801     2 attempts     │
│ "...Fine. The Fort Chowki night entry was padded.   │ │ #2  RJ-DET-3816     4 attempts     │
│  I just didn't want it on record the post was empty."│ └────────────────────────────────────┘
└──────────────────────────────────────────────────────┘
[ DB_TERMINAL ] [ EVIDENCE_BOARD ] [ SECURE_MESSENGER ] [ LEADERBOARD ] [ CASE_FILES ] [ HOW_TO_PLAY ]
```

---

## Features

**🔍 A real coding challenge behind every case**
Every case ships a poisoned dataset and asks for two functions — `clean_data(records)`
and `solve(cleaned_records)`. Runs live in the browser via **Pyodide** (CPython → WASM),
graded server-side against secret unit tests that never ship to the client.

**🗝️ Evidence-gated interrogation (CRAG)**
Retrieve → grade → generate. A suspect's alibi has multiple layers; each one only breaks
when you cite the *specific* piece of evidence it requires. Bluffing, guessing, and vague
accusations are all rejected — even if you're right by accident.

**⚡ Zero LLM calls during actual gameplay**
The expensive part — writing suspect dialogue, hints, and grading criteria — happens
**once**, in a single batched call, the moment a case is generated. Everything is stored
as a `DialogueBank` and served straight from the cache/DB at play time. No player message
ever reaches an LLM provider: nothing to rate-limit, nothing to leak, nothing to sniff.

**🕵️ A scene riddle worth reading twice**
Every case includes a short, cryptic 2–4 line riddle about the crime scene — written to
point toward the right suspect or evidence without naming it outright.

**🎓 A real tutorial, not a wall of text**
*Operation Prashikshan* is a fixed, hand-authored, always-available first case — same
mechanics as a real one, small enough to finish in minutes — paired with an in-app
**How to Play** guide covering every window and the exact shape of `clean_data`/`solve`.

**🌙 Midnight rotation with a memory**
At 00:00 IST, a new case is generated automatically. Anything you had open but hadn't
solved doesn't vanish — it's filed into your personal **pending backlog**, visible
alongside brand-new challenges in the Case Files board.

**🪪 Real accounts, not a throwaway UUID**
Sign in with a username/password backed by **Turso** (edge-hosted libSQL). Your progress
follows your badge number across devices and sessions, with a local SQLite fallback for
zero-setup local dev.

**🇮🇳 Indian-themed, top to bottom**
Every case gets an "Operation `<Codename>`" callsign (Bijli, Trinetra, Chakravyuh...),
challenge slots are labeled *Chunauti*/*Pehchaan*/*Sabut*, badge numbers follow real
state-police numbering conventions, and rotation runs on IST because that's the operator's
clock, not the server's.

---

## Quickstart

```bash
# 1. Backend — from the PROJECT ROOT (the folder containing backend/ and frontend/)
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in OPENROUTER_API_KEY (or HF_TOKEN), TURSO_*, JWT_SECRET
cd ..
uvicorn backend.main:app --reload
```

> ⚠️ Run this from the **project root**, not from inside `backend/` — see
> [Troubleshooting](#troubleshooting) if you hit `ModuleNotFoundError: No module named
> 'backend'`.

On startup the backend connects to Turso (or falls back to a local
`backend/local_users.db` SQLite file), seeds the fixed tutorial case + its dialogue bank,
and starts the midnight (00:00 IST) rotation scheduler.

```bash
# 2. Generate the first daily case (backend must already be running)
curl -X POST http://localhost:8000/api/admin/generate-daily-case
```

```bash
# 3. Frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Enroll a badge (username + password), and you'll be walked
straight into **Operation Prashikshan** with the How-To-Play guide open beside it. Once
that's solved, the Case Files window is your hub for today's case, anything new, and
anything still pending.

### Turso setup (login accounts)

1. Create a database at [turso.tech](https://turso.tech) (free tier is plenty).
2. `turso db show <db-name> --url` → `TURSO_DATABASE_URL`
3. `turso db tokens create <db-name>` → `TURSO_AUTH_TOKEN`
4. Set a long random `JWT_SECRET`.

Without these, accounts still work locally via a SQLite file — just without durability
across machines/redeploys.

### CORS

`FRONTEND_ORIGINS` in `.env` is a comma-separated list of your deployed frontend URL(s).
`localhost`/`127.0.0.1` on any port is always allowed, so local dev needs no extra config;
set this before deploying so the browser doesn't block requests from production.

---

## How a day in the game actually works

**00:00 IST — rotation.** `backend/scheduler.py` fires. `generate_daily_case()` writes a
poisoned dataset, generates the narrative (victim, suspects, scene riddle) in one LLM
call, then generates the entire day's `DialogueBank` (every denial line, every hint,
every evidence trigger phrase) in one more. Only after *both* succeed does the case go
live — a failure here leaves yesterday's case standing instead of publishing something
unsolvable. Anyone with yesterday's case still open and unsolved gets it filed into their
personal pending backlog.

**You open the app.** `GET /api/case/board` returns your tutorial status, today's case,
anything new you haven't touched, and your pending backlog. `GET /api/case/current` loads
whichever one you pick, merged with your progress against *that specific case* — tutorial
progress, today's progress, and each pending case's progress are all tracked
independently, so switching between them never clobbers anything.

**You write code.** `DatabaseTerminal.jsx` runs your `clean_data`/`solve` functions
entirely client-side via Pyodide. Only the *result* — not your source, not the answer —
gets POSTed to `/api/sandbox/execute`, which grades it against secret unit tests and
unlocks evidence server-side.

**You interrogate.** `SecureMessenger.jsx` sends your message to `/api/interrogation/message`.
The evaluator normalizes it and checks it against that suspect's current-layer evidence
trigger phrases — no LLM call, just string matching with fuzzy tolerance for rewording.
A hit breaks the layer and serves the suspect's authored confession line; a miss serves a
rotating pre-written denial. Three misses in a row earns a hint, also pulled from the bank.

**You solve it.** Every suspect broken → case closed, streak updated, leaderboard entry
recorded.

---

## Architecture deep dive

### The dialogue bank: how gameplay avoids live LLM calls

```
CASE GENERATION (once, per case)              GAMEPLAY (every player, every message)
─────────────────────────────────             ───────────────────────────────────────
① narrative LLM call                          ① player sends a message
   → title, victim, suspects,                  ② evaluator.py: normalize + check against
     scene riddle, evidence                        pre-generated trigger phrases  (no LLM)
② dialogue-bank LLM call                       ③ generator.py: pick a pre-written denial
   → denial lines, hints,                          line or the authored confession text
     evidence trigger phrases                                                    (no LLM)
③ both saved to the cache/DB                   ④ hints.py: look up the pre-written hint
   alongside the case file                                                       (no LLM)
```

This is the difference between "an LLM call for every message, every player, every day"
and "two LLM calls per case, ever." It also means there's no live prompt containing case
secrets going out over the network during play — nothing for traffic inspection to catch
mid-interrogation.

### CRAG: retrieval → grading → generation, kept honest

The evaluator only ever sees evidence the player has **actually unlocked** — locked
evidence isn't part of its context at all, so there's no way to be credited for
evidence you haven't earned, even by accident. Grading (does this message cite the
right evidence?) and generation (what does the suspect say back?) are fully separate
steps, so a "yes, that broke them" verdict and "how do they react" are never blended
into one fuzzy judgment.

### Code execution: your browser, not the server

Player code never runs anywhere near the backend. `DatabaseTerminal.jsx` loads Pyodide
(CPython compiled to WebAssembly) the moment its window opens; "Run" executes your
functions in-browser with a client-side timeout, and only the resulting
`{cleaned_count, answer, error}` gets sent to the server for grading against secret unit
tests. Zero server compute cost for arbitrary player code, zero sandbox-escape surface
on the backend.

### Per-case, per-player state — not just per-player

Tutorial progress, today's case, and every case in your pending backlog are each tracked
under their own key (`player:{player_id}:{case_id}`), so opening the tutorial can never
overwrite your progress on today's real case, and vice versa.

---

## Project structure

```
backend/
  main.py                       FastAPI entrypoint: CORS, routers, startup (DB init,
                                  tutorial seed, scheduler)
  auth.py                        Register/login/me — Turso-backed accounts, bcrypt, badge numbers
  db.py                          Turso (libSQL) client, HTTP transport, local SQLite fallback
  tokens.py                      Dependency-free HS256 session tokens (avoids the jwt/PyJWT
                                  package-name collision)
  paths.py                       __file__-anchored path constants (CWD-independent)
  case.py                        GET /api/case/current, GET /api/case/board
  schemas.py                     Every shared Pydantic contract (CaseFile, PlayerState,
                                  DialogueBank, CRAG, sandbox, leaderboard)
  cache.py                       Redis-or-in-memory cache/counter abstraction
  state_store.py                 Case/player/dialogue-bank persistence, archive, pending backlog
  rate_limit.py                  Fixed-window limiter for LLM/compute endpoints
  scheduler.py                   Midnight (IST) rotation via APScheduler
  leaderboard.py                 GET /api/leaderboard/{case_id}, GET /api/players/{id}/stats
  llm_client.py                  Shared OpenRouter/HF client: structured JSON + streaming
  crag/
    dialogue_bank.py              ONE batched LLM call → denial lines, hints, trigger phrases
    evaluator.py                  Rule-based grading against the dialogue bank (no LLM)
    generator.py                  Rule-based reply selection against the dialogue bank (no LLM)
    hints.py                      Rule-based hint lookup against the dialogue bank (no LLM)
    interrogation.py              Orchestrates the above + alibi layers + leaderboard
  generation/
    daily_case.py                  Narrative + dialogue-bank generation, template injection
    tutorial_case.py                Fixed, hand-authored Operation Prashikshan + its dialogue bank
    indian_theme.py                 Operation codenames, Chunauti/Pehchaan/Sabut labels
    dataset_generators.py           Deterministic (non-LLM) poisoned dataset generation
  sandbox/
    executor.py                     Serves poisoned datasets, grades client-executed results

frontend/
  pages/
    _app.js                        Next.js app shell — global CSS import lives here
    index.js                       Hydrates session, gates Login vs PoliceOS
  src/
    store/useGameStore.js           Zustand: auth, session, SSE streaming, case board
    lib/pyodideRunner.js            Runs player Python in-browser via Pyodide (WASM)
    components/auth/
      Login.jsx                     Sign-in / enrollment screen
    components/os/
      PoliceOS.jsx                   Window manager, taskbar, first-timer bootstrap
      Window.jsx                     Draggable/focusable window chrome
    components/apps/
      DatabaseTerminal.jsx           Monaco-based coding sandbox
      EvidenceBoard.jsx              Scene riddle, evidence, suspect/layer status
      SecureMessenger.jsx            CRAG-backed interrogation chat, live streaming
      CaseFiles.jsx                  Tutorial / today / new / pending challenge board
      HowToPlay.jsx                  Onboarding guide: windows, code contract, Python basics
      Leaderboard.jsx                Daily leaderboard + player streak
    styles/theme.css                 Dark case-file OS theme + tricolor accents
```

---

## Environment variables

`backend/.env` (copy from `backend/.env.example`):

| Variable | Required | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes (or `HF_TOKEN`) | From https://openrouter.ai/keys |
| `LLM_BASE_URL` | No | `https://openrouter.ai/api/v1` by default |
| `HF_TOKEN` | Alt. to OpenRouter | From https://huggingface.co/settings/tokens |
| `EVALUATOR_MODEL` / `GENERATOR_MODEL` / `NARRATIVE_MODEL` | No | Per-role model overrides |
| `FALLBACK_MODEL` | No | Used if the primary model call fails |
| `TURSO_DATABASE_URL` | No | From `turso db show <name> --url`; falls back to local SQLite |
| `TURSO_AUTH_TOKEN` | No | From `turso db tokens create <name>` |
| `JWT_SECRET` | Yes in production | Long random string; signs session tokens |
| `FRONTEND_ORIGINS` | Yes in production | Comma-separated deployed frontend URL(s) |
| `REDIS_URL` | No locally, **yes** on serverless | Without it, state is in-memory and resets on redeploy |
| `APP_URL` | No | Sent as a header to some LLM providers |

`frontend/.env.local` (optional):

| Variable | Required | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | No | Defaults to `http://localhost:8000` |

---

## Key design decisions

- **Two LLM calls per case, not per message.** The narrative call and the dialogue-bank
  call both happen once, at generation time. Everything a player does afterward — every
  message, every hint request, every grading decision — is a lookup against what those
  two calls already produced.
- **The dialogue bank is generated *before* the case goes live.** If it fails, the whole
  generation fails atomically and the previous case stays "latest" — never a live case
  with no working evidence triggers.
- **Evaluator grading never sees locked evidence.** Not filtered after the fact — it's
  simply never in scope, so there's no path to being credited for something unearned.
- **State is keyed per `(player, case)`, not per player.** Tutorial, today's case, and
  every pending backlog case carry fully independent progress.
- **Code execution lives in the browser.** No Docker daemon, no code-execution API, no
  server-side sandbox-escape surface — Pyodide (WASM) plus a client-side timeout, graded
  server-side against unit tests that never ship to the client.
- **Session tokens are hand-rolled HS256**, not PyJWT — PyPI has two unrelated packages
  that both install a top-level `jwt` module (`PyJWT` and a different package literally
  named `jwt`), so `import jwt` is genuinely ambiguous depending on install order. A
  ~40-line HMAC-SHA256 implementation sidesteps it entirely.
- **All filesystem paths are anchored to `__file__`**, not the current working directory —
  so nothing breaks depending on which folder you happen to launch `uvicorn` from.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'backend'`**
You're running uvicorn from inside `backend/`. Fix:
```bash
cd <project-root>          # the folder that CONTAINS backend/ and frontend/
uvicorn backend.main:app --reload
```

**`sqlite3.OperationalError: unable to open database file`**
Fixed by anchoring the local DB path to `backend/paths.py` — if you still see this, you're
on an older copy; grab the latest `backend/db.py`.

**Turso: `WSServerHandshakeError: 400` on startup**
The WebSocket (`libsql://`/`wss://`) transport in this version of `libsql-client` doesn't
play well with newer `aiohttp`. `backend/db.py` normalizes to the plain HTTP transport
(`https://`) instead — no persistent connection, no handshake to fail.

**`ExecutionStatus.RUNTIME_ERROR` on every submission**
Your code needs to define exactly `clean_data(records)` and `solve(cleaned_records)` —
see the How to Play guide in-app, or the template `DatabaseTerminal.jsx` scaffolds for you.

**CORS errors in the browser console**
Set `FRONTEND_ORIGINS` in `backend/.env` to your deployed frontend's exact origin, then
redeploy the backend. `localhost`/`127.0.0.1` on any port always works without config.

**Render: build installs the wrong/old dependencies**
Check your Build Command actually points at `backend/requirements.txt` — if your Start
Command is `uvicorn backend.main:app` (Root Directory = repo root), a bare
`pip install -r requirements.txt` may resolve to a stale file at the repo root instead.

**Frontend stuck on "Pulling your case file…"**
Almost always `GET /api/case/board` or `/api/case/current` erroring — check the Network
tab. Common causes: no daily case generated yet (`POST /api/admin/generate-daily-case`),
`NEXT_PUBLIC_API_BASE` not pointing at your backend, or the CORS issue above.

**429 / "Slow down" messages**
Intentional (`backend/rate_limit.py`), bounding submission/interrogation cost per player —
not a bug.

---

## Roadmap / not yet wired

- **External cron for rotation** — `scheduler.py`'s in-process APScheduler is fine for a
  single instance; on a multi-instance deploy, trigger `/api/admin/generate-daily-case`
  from an external scheduler instead so it doesn't fire twice.
- **Multiplayer/social features** — leaderboards exist per-case; head-to-head or
  friend-group leaderboards don't yet.
- **More coding-challenge templates** — currently two deterministic templates
  (transaction-log binary search, cell-ping loitering scan); the pattern in
  `dataset_generators.py` is built to add more.

---

## Contact
 - **Email** - nnair7598@gmail.com
 - **LinkedIn** - https://www.linkedin.com/in/nikhil-nair-809248286

## Thank You
