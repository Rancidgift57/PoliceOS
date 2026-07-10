import { create } from "zustand";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

/**
 * Single source of truth shared by every Police OS window (IDE, Evidence
 * Board, Messenger, Leaderboard). Keeping this as one store - rather than
 * one per app - is what lets, e.g., a solved coding challenge instantly
 * light up a new pin on the Evidence Board and unlock new dialogue options
 * in the Messenger without any window-to-window message passing.
 */
export const useGameStore = create((set, get) => ({
  playerId: null,
  caseId: null,
  caseFile: null, // { case_id, title, victim, crime_scene, narrative_intro, suspects, evidence, challenges }

  unlockedEvidenceIds: [],
  solvedChallengeIds: [],
  suspectAlibis: {}, // suspectId -> current visible alibi/reveal text
  suspectBroken: {}, // suspectId -> bool (fully broken)
  suspectLayerIndex: {}, // suspectId -> current unbroken layer index
  chatHistory: {}, // suspectId -> [{role, content}]
  caseSolved: false,

  rateLimitNotice: null, // { scope, message } - set on a 429, cleared on next successful call

  activeWindows: ["terminal", "evidence", "messenger"],
  focusedWindow: "terminal",

  // ---- bootstrap ---------------------------------------------------------
  initSession: async (playerId) => {
    set({ playerId });
    const res = await fetch(`${API_BASE}/api/case/current?player_id=${playerId}`);
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
    });
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
  runSubmission: async (challengeId, sourceCode) => {
    const { playerId, caseId } = get();
    const res = await fetch(`${API_BASE}/api/sandbox/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_id: playerId,
        case_id: caseId,
        challenge_id: challengeId,
        source_code: sourceCode,
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
    const { playerId } = get();

    set((s) => ({
      chatHistory: {
        ...s.chatHistory,
        [suspectId]: [...(s.chatHistory[suspectId] ?? []), { role: "player", content: message }],
      },
    }));

    const res = await fetch(`${API_BASE}/api/interrogation/message/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: playerId, suspect_id: suspectId, message }),
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
    const { playerId } = get();
    const res = await fetch(`${API_BASE}/api/interrogation/hint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: playerId, suspect_id: suspectId }),
    });
    if (res.status === 429) {
      const detail = (await res.json().catch(() => ({}))).detail ?? "Slow down on hint requests.";
      set({ rateLimitNotice: { scope: "hint", message: detail } });
      return { available: false, hint: null, attempts_made: 0, attempts_until_hint: 0 };
    }
    return res.json();
  },
}));
