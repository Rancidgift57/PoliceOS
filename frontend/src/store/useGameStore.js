import { create } from "zustand";
import { runPlayerSubmission } from "@/lib/pyodideRunner";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// Poisoned datasets are static per case/challenge, so cache them in-module
// once fetched instead of re-fetching on every "Run" click.
const _datasetCache = new Map();
async function fetchPoisonedDataset(caseId, challengeId) {
  const key = `${caseId}:${challengeId}`;
  if (_datasetCache.has(key)) return _datasetCache.get(key);
  const res = await fetch(`${API_BASE}/api/sandbox/dataset/${caseId}/${challengeId}`);
  if (!res.ok) throw new Error(`Failed to load dataset (${res.status})`);
  const dataset = await res.json();
  _datasetCache.set(key, dataset);
  return dataset;
}

/**
 * Single source of truth shared by every Police OS window (IDE, Evidence
 * Board, Messenger, Leaderboard). Keeping this as one store - rather than
 * one per app - is what lets, e.g., a solved coding challenge instantly
 * light up a new pin on the Evidence Board and unlock new dialogue options
 * in the Messenger without any window-to-window message passing.
 */
const AUTH_STORAGE_KEY = "police-os:auth";

export const useGameStore = create((set, get) => ({
  // ---- auth ----------------------------------------------------------------
  authToken: null,
  user: null, // { player_id, username, badge_number, display_name }
  authHydrated: false,

  hydrateAuth: () => {
    try {
      const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
      if (raw) {
        const data = JSON.parse(raw);
        set({ authToken: data.token, user: data });
      }
    } catch {
      // corrupt/blocked storage - just fall through to the login screen
    } finally {
      set({ authHydrated: true });
    }
  },

  register: async (username, password, displayName) => {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, display_name: displayName }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail ?? "Registration failed");
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(data));
    set({ authToken: data.token, user: data });
    return data;
  },
  login: async (username, password) => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail ?? "Login failed");
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(data));
    set({ authToken: data.token, user: data });
    return data;
  },
  logout: () => {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    set({ authToken: null, user: null, playerId: null, caseId: null, caseFile: null });
  },

  playerId: null,
  caseId: null,
  caseFile: null, // { case_id, title, codename, victim, crime_scene, narrative_intro, suspects, evidence, challenges }
  caseBoard: null, // { tutorial, today, new_challenges, pending_challenges }

  unlockedEvidenceIds: [],
  solvedChallengeIds: [],
  suspectAlibis: {}, // suspectId -> current visible alibi/reveal text
  suspectBroken: {}, // suspectId -> bool (fully broken)
  suspectLayerIndex: {}, // suspectId -> current unbroken layer index
  chatHistory: {}, // suspectId -> [{role, content}]
  caseSolved: false,

  rateLimitNotice: null, // { scope, message } - set on a 429, cleared on next successful call

  activeWindows: ["terminal", "evidence", "messenger", "casefiles"],
  focusedWindow: "terminal",

  // ---- bootstrap ---------------------------------------------------------
  // caseId is optional: omit it to load today's rotating daily case, or
  // pass "case_tutorial" / any archived case_id (from the Case Files board)
  // to load that one instead. Each is tracked as independent progress
  // server-side, so switching cases never clobbers another case's state.
  initSession: async (playerId, caseId) => {
    set({ playerId });
    const qs = new URLSearchParams({ player_id: playerId });
    if (caseId) qs.set("case_id", caseId);
    const res = await fetch(`${API_BASE}/api/case/current?${qs.toString()}`);
    const caseFile = await res.json();
    set({
      caseId: caseFile.case_id,
      caseFile,
      unlockedEvidenceIds: caseFile.player_state?.unlocked_evidence_ids ?? [],
      solvedChallengeIds: caseFile.player_state?.solved_challenge_ids ?? [],
      suspectAlibis: caseFile.player_state?.suspect_alibis ?? {},
      suspectBroken: caseFile.player_state?.suspect_broken ?? {},
      suspectLayerIndex: caseFile.player_state?.suspect_layer_index ?? {},
      caseSolved: caseFile.player_state?.case_solved ?? false,
      chatHistory: caseFile.player_state?.chat_history ?? {},
    });
    return caseFile;
  },

  // ---- Case Files board (tutorial / today / new / pending) ---------------
  fetchCaseBoard: async () => {
    const { playerId } = get();
    const res = await fetch(`${API_BASE}/api/case/board?player_id=${playerId}`);
    const board = await res.json();
    set({ caseBoard: board });
    return board;
  },
  switchCase: async (caseId) => {
    const { playerId, initSession } = get();
    return initSession(playerId, caseId);
  },

  // ---- window manager ------------------------------------------------------
  focusWindow: (id) => set({ focusedWindow: id }),
  openWindow: (id) =>
    set((s) => ({
      activeWindows: s.activeWindows.includes(id) ? s.activeWindows : [...s.activeWindows, id],
      focusedWindow: id,
    })),
  closeWindow: (id) =>
    set((s) => ({ activeWindows: s.activeWindows.filter((w) => w !== id) })),

  // ---- sandbox / coding loop ----------------------------------------------
  // Execution happens client-side in the browser via Pyodide (WASM) - no
  // Docker daemon and no hosted code-execution API (e.g. Piston) needed.
  // The backend only grades the {cleaned_count, answer, error} the browser
  // already computed, against unit_tests it never sends to the client.
  runSubmission: async (challengeId, sourceCode) => {
    const { playerId, caseId } = get();

    let dataset;
    try {
      dataset = await fetchPoisonedDataset(caseId, challengeId);
    } catch (err) {
      return { status: "runtime_error", stderr: err.message ?? String(err) };
    }

    const { cleaned_count, answer, error, runtime_ms } = await runPlayerSubmission(
      sourceCode,
      dataset
    );

    const res = await fetch(`${API_BASE}/api/sandbox/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_id: playerId,
        case_id: caseId,
        challenge_id: challengeId,
        source_code: sourceCode,
        cleaned_count,
        answer,
        error,
        client_runtime_ms: runtime_ms,
      }),
    });

    if (res.status === 429) {
      const detail = (await res.json().catch(() => ({}))).detail ?? "Slow down - too many runs.";
      set({ rateLimitNotice: { scope: "sandbox", message: detail } });
      return { status: "rate_limited", stdout: detail };
    }
    set({ rateLimitNotice: null });

    const result = await res.json();
    if (result.status === "passed") {
      set((s) => ({
        solvedChallengeIds: [...new Set([...s.solvedChallengeIds, challengeId])],
        unlockedEvidenceIds: result.unlocked_evidence_id
          ? [...new Set([...s.unlockedEvidenceIds, result.unlocked_evidence_id])]
          : s.unlockedEvidenceIds,
      }));
    }
    return result;
  },

  // ---- CRAG interrogation (SSE streaming) ---------------------------------
  /**
   * Streams the suspect's reply token-by-token from /api/interrogation/message/stream.
   * `onToken` is called with each chunk so the UI can render it live; the
   * function resolves once the `done` frame arrives with the full metadata
   * (trap_successful, unlocked evidence, etc).
   */
  streamInterrogationMessage: async (suspectId, message, onToken) => {
    const { playerId, caseId } = get();

    set((s) => ({
      chatHistory: {
        ...s.chatHistory,
        [suspectId]: [...(s.chatHistory[suspectId] ?? []), { role: "player", content: message }],
      },
    }));

    const res = await fetch(`${API_BASE}/api/interrogation/message/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: playerId, suspect_id: suspectId, message, case_id: caseId }),
    });

    if (res.status === 429) {
      const detail = (await res.json().catch(() => ({}))).detail ?? "Slow down - too many messages.";
      set({ rateLimitNotice: { scope: "interrogation", message: detail } });
      return null;
    }
    set({ rateLimitNotice: null });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let donePayload = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line; parse whole frames only.
      let frameEnd;
      while ((frameEnd = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, frameEnd);
        buffer = buffer.slice(frameEnd + 2);

        const eventMatch = frame.match(/^event: (.+)$/m);
        const dataMatch = frame.match(/^data: (.+)$/m);
        if (!eventMatch || !dataMatch) continue;

        const eventName = eventMatch[1];
        const data = JSON.parse(dataMatch[1]);

        if (eventName === "token") {
          onToken?.(data.text);
        } else if (eventName === "done") {
          donePayload = data;
        }
      }
    }

    if (!donePayload) return null;

    set((s) => ({
      chatHistory: {
        ...s.chatHistory,
        [suspectId]: [...s.chatHistory[suspectId], { role: "suspect", content: donePayload.suspect_reply }],
      },
      suspectAlibis: { ...s.suspectAlibis, [suspectId]: donePayload.updated_alibi },
      suspectBroken: { ...s.suspectBroken, [suspectId]: donePayload.suspect_broken },
      suspectLayerIndex: { ...s.suspectLayerIndex, [suspectId]: donePayload.current_layer_index },
      unlockedEvidenceIds: [
        ...new Set([...s.unlockedEvidenceIds, ...(donePayload.newly_unlocked_evidence ?? [])]),
      ],
      caseSolved: s.caseFile
        ? Object.keys({ ...s.suspectBroken, [suspectId]: donePayload.suspect_broken }).length ===
            s.caseFile.suspects.length &&
          s.caseFile.suspects.every(
            (sus) => ({ ...s.suspectBroken, [suspectId]: donePayload.suspect_broken })[sus.id]
          )
        : s.caseSolved,
    }));

    return donePayload;
  },

  // ---- leaderboard / streaks ----------------------------------------------
  fetchLeaderboard: async (caseId) => {
    const res = await fetch(`${API_BASE}/api/leaderboard/${caseId}`);
    return res.json();
  },
  fetchPlayerStats: async (playerId) => {
    const res = await fetch(`${API_BASE}/api/players/${playerId}/stats`);
    return res.json();
  },

  // ---- hints ---------------------------------------------------------------
  fetchHint: async (suspectId) => {
    const { playerId, caseId } = get();
    const res = await fetch(`${API_BASE}/api/interrogation/hint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: playerId, suspect_id: suspectId, case_id: caseId }),
    });
    if (res.status === 429) {
      const detail = (await res.json().catch(() => ({}))).detail ?? "Slow down on hint requests.";
      set({ rateLimitNotice: { scope: "hint", message: detail } });
      return { available: false, hint: null, attempts_made: 0, attempts_until_hint: 0 };
    }
    return res.json();
  },
}));
