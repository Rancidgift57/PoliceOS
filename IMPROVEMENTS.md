# Improvement Ideas — Status

Everything from both prior passes is now implemented. What's left is called
out explicitly at the bottom, with why it's still a real judgment call
rather than a quick add.

## Implemented

1. **Redis-backed state store, with in-memory fallback.** `backend/cache.py`
   picks Redis automatically when `REDIS_URL` is set, otherwise runs a
   process-local in-memory store - `state_store.py` and `rate_limit.py`
   both go through it. Player state carries a 3-day TTL in Redis.

2. **Evaluator response caching.** `crag/evaluator.py` hashes
   `(unlocked_evidence_ids, alibi_text, player_message)` and caches the
   verdict for 10 minutes - a pure cost win since the evaluator is
   temperature-0 and fully deterministic given the same inputs.

3. **Streaming suspect replies.** `POST /api/interrogation/message/stream`
   (SSE) + `useGameStore.streamInterrogationMessage` + `SecureMessenger.jsx`
   render tokens live with a blinking cursor instead of a loading spinner.

4. **Rate limiting.** `backend/rate_limit.py`, a fixed-window counter on the
   shared cache, applied to `/api/interrogation/message(/stream)` (20/min),
   `/api/sandbox/execute` (15/min), and now `/api/interrogation/hint`
   (10/min). All return 429s the frontend surfaces via `rateLimitNotice`.

5. **Multi-stage suspects.** `Suspect.alibi_layers` - two layers per
   suspect, the first breaking on coding-challenge evidence and
   auto-unlocking a "slip" that's required to break the second. Built
   programmatically in `daily_case.py` from LLM-written narrative text
   rather than asking the LLM to invent evidence ids it can't know about.

6. **A second verified template.** `_transactions_template` (clean +
   binary search) and `_cell_pings_template` (clean + two-pointer loitering
   scan), picked deterministically per `case_id`.

7. **Leaderboard + streaks.** `backend/leaderboard.py`,
   `components/apps/Leaderboard.jsx`, ranked by total attempts.

8. **Moving off self-managed Docker.** `backend/sandbox/piston_runner.py`
   is a full alternative sandbox backend using the hosted Piston
   code-execution API instead of a Docker daemon - same harness contract
   (`clean_data`/`solve`), same return shape, selected at runtime via
   `SANDBOX_BACKEND=piston` in `.env` with zero changes to
   `executor.py`'s grading logic. See DEPLOYMENT.md Path B for what
   changes operationally (managed Redis becomes mandatory; dataset storage
   needs to move off local disk).

9. **Hint system using the evaluator's `reasoning` field.**
   `crag/hints.py` + `POST /api/interrogation/hint`. The evaluator's
   internal `reasoning` (previously computed every turn but only logged)
   now gets surfaced as a softened, in-world nudge once a player has failed
   `HINT_THRESHOLD` (3) consecutive attempts at their CURRENT layer. Two
   distinct hint modes: "you're missing evidence" (if the layer's required
   evidence isn't unlocked yet - never reveals what it is) vs. "you have it,
   be more direct" (references the evidence's label, never its exact
   detail text). Resets per layer, not just once per suspect, so later
   layers aren't trivialized by an early hint.

10. **Real calendar-aware streak logic.** `state_store._case_date` parses
    the `YYYYMMDD` embedded in `case_id` (format `case_20260710_a1b2c3`)
    and `record_case_solved` diffs actual calendar dates: exactly 1 day
    apart continues the streak, same day leaves it unchanged (handles a
    regenerated case), anything else resets to 1. Unit-verified with a
    4-case sequence (consecutive day, a gap, and a same-day repeat).

## Still not done (and why these are genuinely judgment calls, not oversights)

- **Object storage for datasets.** Called out explicitly in DEPLOYMENT.md
  Path B - the one real blocker to actually running Path B in production,
  since local-disk dataset writes don't survive across serverless
  invocations. Left undone because the right choice (S3 vs. R2 vs.
  provider-native) depends on which platform you deploy to, which wasn't
  specified.
- **A third+ coding template.** The template list is built to extend
  (`_TEMPLATES` in `daily_case.py`) - adding more is mechanical at this
  point (a `_*_template()` function + matching `dataset_generators`
  function) but each one is a design decision about what algorithm/flavor
  to add, not an infrastructure gap.
- **Piston resource limits.** Path B trades `docker_runner.py`'s explicit
  `mem_limit`/`pids_limit`/CPU quota for whatever the Piston instance
  enforces. Self-hosting Piston restores that control; using the public
  instance doesn't. This is an inherent trade-off of the approach, not
  something more code fixes.
