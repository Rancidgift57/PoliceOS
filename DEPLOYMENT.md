# Deployment Guide

## The one constraint that shapes everything

`sandbox/docker_runner.py` spins up a **real Docker container per code
submission**. That means the backend needs a host with an actual Docker
daemon it controls. Pure serverless platforms (Vercel functions, AWS
Lambda, Cloudflare Workers) don't give you that, so the backend can't live
there. The frontend has no such constraint and deploys anywhere that hosts
Next.js.

Two paths, pick one:

- **Path A (recommended to start): a VPS with Docker.** Simplest mental
  model, full control, cheapest at low traffic.
- **Path B: swap the sandbox for a hosted code-execution API** (Piston is
  wired up already - `sandbox/piston_runner.py`). Set `SANDBOX_BACKEND=piston`
  in `.env` and the backend has no Docker dependency at all, so it can run
  on serverless/edge platforms. Trade-off: you're on the public Piston
  instance's shared queue/limits unless you self-host it (Piston ships its
  own Docker image, so "self-host Piston" is really Path A one layer down -
  you get the isolation guarantees back without babysitting per-submission
  containers yourself).

This guide covers Path A in depth, then Path B as a variant at the end.

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

---

## 2. Backend → a VPS with Docker

Any VPS works (DigitalOcean, Hetzner, Linode). Rough steps on a fresh
Ubuntu 22.04+ box:

```bash
# 1. Install Docker + Compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# 2. Get the code onto the box
git clone <your-repo-url> police-os && cd police-os/backend

# 3. Configure secrets
cp .env.example .env
nano .env   # fill in OPENROUTER_API_KEY (or HF_TOKEN), model choices, APP_URL

# 4. Build the sandbox image + start the API
docker compose up -d --build

# 5. Sanity check
curl http://localhost:8000/api/health
```

`docker-compose.yml` mounts `/var/run/docker.sock` into the API container
(docker-outside-of-docker) so `docker_runner.py` can launch sibling sandbox
containers on the host daemon — this is why `Dockerfile.api` also installs
the `docker` CLI.

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

- A $12–24/mo VPS (2 vCPU / 4GB RAM) comfortably handles the API plus a
  handful of concurrent sandbox containers. Each sandbox run is capped at
  256MB RAM / 0.5 CPU / 10s (see `docker_runner.py`), so containers are
  cheap — the limit you'll hit first is concurrent request volume, not
  memory.
- LLM cost is the other real line item. OpenRouter/HF bill per token
  regardless of where you host; `EVALUATOR_MODEL`/`GENERATOR_MODEL` in
  `.env` let you dial cost vs. quality independently for the grading call
  vs. the dialogue call (see IMPROVEMENTS.md for caching ideas to cut this
  further).
- State is in-memory (`state_store.py`) — restarting the container wipes
  active sessions. Fine for a prototype; swap for Redis before real
  traffic (see IMPROVEMENTS.md).

---

## 4. Path B — serverless backend via Piston (no Docker)

With `SANDBOX_BACKEND=piston` set, `backend/sandbox/executor.py` never
imports `docker_runner.py` at all — the only dependency is `httpx` making a
plain HTTPS call to Piston. That means the backend can deploy anywhere that
runs a Python ASGI app, including serverless platforms:

```bash
# .env
SANDBOX_BACKEND=piston
REDIS_URL=redis://<your-managed-redis>:6379/0   # required now - no local disk to fall back to
```

A few things change with this path:

- **Use a managed Redis**, not the in-memory fallback — serverless
  invocations don't share memory between requests, so `cache.py` would
  otherwise "forget" every player's state on the very next call. Any
  managed Redis works (Upstash, Redis Cloud, provider-native).
- **Datasets need to live somewhere fetchable**, not on local disk —
  `generation/daily_case.py` currently writes poisoned datasets to
  `backend/generation/datasets/`, which won't persist or be shared across
  serverless invocations. Swap that write (and `executor._load_poisoned_dataset`)
  for a small object-storage read/write (S3, R2, etc.) before using this
  path in production — this is the one real code change Path B still needs.
- Deploy the FastAPI app itself with any ASGI-compatible serverless adapter
  for your platform of choice (e.g. Mangum for AWS Lambda, or a platform's
  native Python/ASGI support) — no Dockerfile required.
- You lose the strict resource caps (`mem_limit`, `pids_limit`, etc.) that
  `docker_runner.py` enforces per submission — Piston's public instance
  enforces its own limits instead, which are less tunable. Self-hosting
  Piston gets you back to fully custom limits without hand-rolling the
  container orchestration yourself.
