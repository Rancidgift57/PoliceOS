# Deployment Guide

## The constraint that used to shape everything is gone

Earlier versions of this backend ran player code server-side, either in a
self-managed Docker container per submission or via a hosted
code-execution API (Piston). That's no longer the case: player code now
runs entirely **client-side in the browser**, via Pyodide (CPython
compiled to WebAssembly) - see `frontend/src/lib/pyodideRunner.js`. The
backend never executes `source_code`; it just grades the
`{cleaned_count, answer, error}` the browser already computed against the
case file's `unit_tests`, which never leave the server.

Practically, that means:

- **No Docker daemon needed anywhere in production.** The backend is a
  plain FastAPI/ASGI app.
- **No third-party code-execution API dependency, no API keys for it, no
  per-run infrastructure cost for it** - execution happens on the
  player's own CPU, for free, with no network round trip while it runs.
- **The backend can run on basically anything that hosts an ASGI app**,
  including serverless/edge platforms, since there's no long-lived daemon
  or container orchestration to manage.

---

## 1. Frontend → Vercel

```bash
cd frontend
npm install -g vercel
vercel login
vercel --prod
```

In the Vercel dashboard, set the environment variable:

```
NEXT_PUBLIC_API_BASE=https://your-backend-domain.com
```

That's it — Next.js + Vercel is a native fit, no further changes needed.
Pyodide itself loads lazily from a CDN (`cdn.jsdelivr.net/pyodide`) the
first time a player opens the Database Terminal, so there's nothing extra
to bundle or host for it.

---

## 2. Backend → anywhere that runs an ASGI app

Since there's no Docker daemon requirement, pick whatever's simplest:

### Option A: a small VPS (DigitalOcean, Hetzner, Linode, …)

```bash
# 1. Get the code onto the box
git clone <your-repo-url> police-os && cd police-os/backend

# 2. Configure secrets
cp .env.example .env
nano .env   # fill in OPENROUTER_API_KEY (or HF_TOKEN), model choices, APP_URL

# 3. Build + start the API
docker compose up -d --build

# 4. Sanity check
curl http://localhost:8000/api/health
```

`docker-compose.yml` here just builds `Dockerfile.api` - a plain Python
image, no docker-outside-of-docker socket mounting, since there's no
sandbox container to launch anymore.

### Option B: a serverless/PaaS platform

Deploy the FastAPI app with any ASGI-compatible adapter for your platform
of choice (e.g. Mangum for AWS Lambda, or a platform's native Python/ASGI
support, or Render/Fly.io's standard Python app support) - no Dockerfile
required at all if the platform builds from `requirements.txt` directly.

One thing to change for this path: **use a managed Redis**, not the
in-memory fallback - serverless invocations don't share memory between
requests, so `cache.py` would otherwise "forget" every player's state on
the next call:

```bash
# .env
REDIS_URL=redis://<your-managed-redis>:6379/0   # Upstash, Redis Cloud, provider-native, etc.
```

Datasets currently get written to local disk in
`generation/daily_case.py` (`backend/generation/datasets/`) and read back
by `backend/sandbox/executor.py`'s `/dataset/{case_id}/{challenge_id}`
endpoint. That won't persist or be shared across serverless invocations -
swap it for a small object-storage read/write (S3, R2, etc.) before using
this path in production.

### Put it behind HTTPS

Easiest option is [Caddy](https://caddyserver.com/) — automatic Let's
Encrypt certs, no manual nginx/certbot dance:

```bash
sudo apt install -y caddy
sudo tee /etc/caddy/Caddyfile <<'EOF'
your-backend-domain.com {
    reverse_proxy localhost:8000
}
EOF
sudo systemctl restart caddy
```

Point your domain's A record at the VPS IP first, then run the above.

### Update CORS

In `backend/main.py`, change `allow_origins` from the Next.js dev URL to
your real Vercel domain:

```python
allow_origins=["https://your-frontend.vercel.app"],
```

### Kick off the first case

```bash
curl -X POST https://your-backend-domain.com/api/admin/generate-daily-case
```

Automate this with a daily cron entry on the same box:

```bash
crontab -e
# 0 6 * * *  curl -s -X POST http://localhost:8000/api/admin/generate-daily-case
```

---

## 3. Sizing / cost notes

- Since code execution is client-side, the backend's job is just serving
  case data, grading small JSON payloads, and running the CRAG
  interrogation LLM calls - it's light. A $6–12/mo VPS or a small
  serverless plan comfortably handles this; you're not sizing for
  concurrent sandbox containers anymore.
- LLM cost is the real line item. OpenRouter/HF bill per token regardless
  of where you host; `EVALUATOR_MODEL`/`GENERATOR_MODEL` in `.env` let you
  dial cost vs. quality independently for the grading call vs. the
  dialogue call (see IMPROVEMENTS.md for caching ideas to cut this
  further).
- State is in-memory (`state_store.py`) by default — restarting the
  process wipes active sessions. Fine for a prototype; swap for Redis
  before real traffic, and mandatory if you deploy serverless (see
  Option B above).
- Pyodide's first load is the one real client-side cost worth knowing
  about: it pulls down several MB of WASM runtime the first time a player
  opens the terminal (cached by the browser after that). The frontend
  kicks this off as soon as the Database Terminal window opens, so it's
  usually warm before the player finishes reading the challenge prompt.
