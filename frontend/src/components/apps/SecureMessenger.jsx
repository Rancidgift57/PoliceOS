import { useState } from "react";
import { useGameStore } from "@/store/useGameStore";

export default function SecureMessenger() {
  const caseFile = useGameStore((s) => s.caseFile);
  const chatHistory = useGameStore((s) => s.chatHistory);
  const suspectBroken = useGameStore((s) => s.suspectBroken);
  const suspectLayerIndex = useGameStore((s) => s.suspectLayerIndex);
  const streamInterrogationMessage = useGameStore((s) => s.streamInterrogationMessage);
  const fetchHint = useGameStore((s) => s.fetchHint);
  const rateLimitNotice = useGameStore((s) => s.rateLimitNotice);

  const [activeSuspectId, setActiveSuspectId] = useState(caseFile?.suspects?.[0]?.id ?? null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [liveReply, setLiveReply] = useState(""); // partial suspect reply as it streams in
  const [hintState, setHintState] = useState(null); // { loading, available, hint, attempts_until_hint }

  if (!caseFile) {
    return <div style={{ color: "var(--text-dim)" }}>Loading case data…</div>;
  }

  const suspectId = activeSuspectId ?? caseFile.suspects[0]?.id;
  const suspect = caseFile.suspects.find((s) => s.id === suspectId);
  const history = chatHistory[suspectId] ?? [];
  const layerIndex = suspectLayerIndex[suspectId] ?? 0;
  const totalLayers = suspect?.alibi_layers?.length ?? 1;

  const handleSend = async () => {
    if (!draft.trim() || sending) return;
    const message = draft;
    setDraft("");
    setSending(true);
    setLiveReply("");
    setHintState(null);
    try {
      await streamInterrogationMessage(suspectId, message, (chunk) => {
        setLiveReply((prev) => prev + chunk);
      });
    } finally {
      setSending(false);
      setLiveReply("");
    }
  };

  const handleHint = async () => {
    setHintState({ loading: true });
    const result = await fetchHint(suspectId);
    setHintState({ loading: false, ...result });
  };

  const handleSelectSuspect = (id) => {
    setActiveSuspectId(id);
    setHintState(null);
  };

  return (
    <div style={{ display: "flex", height: "100%", fontSize: 12 }}>
      <div style={{ width: 110, borderRight: "1px solid var(--panel-border)", paddingRight: 8 }}>
        {caseFile.suspects.map((s) => {
          const broken = suspectBroken[s.id];
          const layer = suspectLayerIndex[s.id] ?? 0;
          return (
            <div
              key={s.id}
              onClick={() => handleSelectSuspect(s.id)}
              style={{
                padding: "6px 4px",
                cursor: "pointer",
                color: s.id === suspectId ? "var(--accent-amber)" : "var(--text-dim)",
              }}
            >
              {s.name}
              <div style={{ fontSize: 10, color: broken ? "var(--accent-red)" : "var(--text-dim)" }}>
                {broken ? "broken" : `layer ${layer + 1}/${s.alibi_layers?.length ?? 1}`}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", paddingLeft: 10 }}>
        {!suspectBroken[suspectId] && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ color: "var(--text-dim)", fontSize: 10 }}>
              Story layer {layerIndex + 1} of {totalLayers}
            </span>
            <button
              onClick={handleHint}
              disabled={hintState?.loading}
              style={{
                background: "transparent",
                color: "var(--accent-blue)",
                border: "1px solid var(--panel-border)",
                borderRadius: 2,
                padding: "2px 8px",
                fontSize: 10,
                cursor: hintState?.loading ? "default" : "pointer",
              }}
            >
              {hintState?.loading ? "…" : "Request hint"}
            </button>
          </div>
        )}

        {hintState && !hintState.loading && (
          <div
            style={{
              fontSize: 11,
              marginBottom: 6,
              padding: "5px 8px",
              border: `1px solid ${hintState.available ? "var(--accent-blue)" : "var(--panel-border)"}`,
              borderRadius: 2,
              color: hintState.available ? "var(--text-primary)" : "var(--text-dim)",
            }}
          >
            {hintState.available
              ? hintState.hint
              : `Keep at it — ${hintState.attempts_until_hint} more attempt${
                  hintState.attempts_until_hint === 1 ? "" : "s"
                } before a hint unlocks.`}
          </div>
        )}

        <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
          {history.map((msg, i) => (
            <div
              key={i}
              style={{
                alignSelf: msg.role === "player" ? "flex-end" : "flex-start",
                maxWidth: "85%",
                background: msg.role === "player" ? "rgba(212,160,23,0.1)" : "var(--panel-header)",
                border: "1px solid var(--panel-border)",
                borderRadius: 3,
                padding: "6px 8px",
                lineHeight: 1.4,
              }}
            >
              {msg.content}
            </div>
          ))}

          {sending && liveReply && (
            <div
              style={{
                alignSelf: "flex-start",
                maxWidth: "85%",
                background: "var(--panel-header)",
                border: "1px solid var(--accent-amber-dim)",
                borderRadius: 3,
                padding: "6px 8px",
                lineHeight: 1.4,
              }}
            >
              {liveReply}
              <span style={{ opacity: 0.5 }}>▌</span>
            </div>
          )}

          {history.length === 0 && !sending && (
            <div style={{ color: "var(--text-dim)" }}>
              No messages yet. Ask {suspect?.name} about their whereabouts.
            </div>
          )}
        </div>

        {rateLimitNotice && (
          <div style={{ color: "var(--accent-red)", fontSize: 11, marginBottom: 4 }}>
            {rateLimitNotice.message}
          </div>
        )}

        <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Type your question…"
            disabled={sending}
            style={{
              flex: 1,
              background: "var(--os-bg)",
              border: "1px solid var(--panel-border)",
              color: "var(--text-primary)",
              padding: "6px 8px",
              borderRadius: 2,
              fontFamily: "var(--mono-font)",
              fontSize: 12,
            }}
          />
          <button
            onClick={handleSend}
            disabled={sending}
            style={{
              background: "var(--accent-amber-dim)",
              color: "var(--accent-amber)",
              border: "1px solid var(--accent-amber-dim)",
              borderRadius: 2,
              padding: "6px 12px",
              cursor: sending ? "default" : "pointer",
            }}
          >
            {sending ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
