import { useGameStore } from "@/store/useGameStore";

export default function EvidenceBoard() {
  const caseFile = useGameStore((s) => s.caseFile);
  const unlockedEvidenceIds = useGameStore((s) => s.unlockedEvidenceIds);
  const suspectBroken = useGameStore((s) => s.suspectBroken);
  const suspectLayerIndex = useGameStore((s) => s.suspectLayerIndex);
  const openWindow = useGameStore((s) => s.openWindow);

  if (!caseFile) {
    return <div style={{ color: "var(--text-dim)" }}>Loading case data…</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, fontSize: 12 }}>
      <div>
        <div style={{ color: "var(--text-dim)", textTransform: "uppercase", fontSize: 11, marginBottom: 6 }}>
          Victim / Scene
        </div>
        <div style={{ lineHeight: 1.5 }}>
          {caseFile.victim} — {caseFile.crime_scene}
        </div>
      </div>

      {caseFile.scene_riddle && (
        <div>
          <div style={{ color: "var(--text-dim)", textTransform: "uppercase", fontSize: 11, marginBottom: 6 }}>
            Scene Briefing
          </div>
          <div
            style={{
              lineHeight: 1.6,
              fontStyle: "italic",
              color: "var(--accent-amber)",
              whiteSpace: "pre-line",
              border: "1px solid var(--panel-border)",
              borderRadius: 2,
              padding: "8px 10px",
              background: "rgba(212,160,23,0.04)",
            }}
          >
            {caseFile.scene_riddle}
          </div>
        </div>
      )}

      <div>
        <div style={{ color: "var(--text-dim)", textTransform: "uppercase", fontSize: 11, marginBottom: 6 }}>
          Evidence ({unlockedEvidenceIds.length}/{caseFile.evidence.length} unlocked)
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {caseFile.evidence.map((ev) => {
            const unlocked = unlockedEvidenceIds.includes(ev.id);
            return (
              <div
                key={ev.id}
                style={{
                  border: `1px solid ${unlocked ? "var(--accent-amber-dim)" : "var(--panel-border)"}`,
                  borderRadius: 2,
                  padding: "6px 8px",
                  color: unlocked ? "var(--text-primary)" : "var(--text-dim)",
                  background: unlocked ? "rgba(212,160,23,0.06)" : "transparent",
                }}
              >
                {unlocked ? ev.label : "█████████████ [LOCKED]"}
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <div style={{ color: "var(--text-dim)", textTransform: "uppercase", fontSize: 11, marginBottom: 6 }}>
          Suspects
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {caseFile.suspects.map((sus) => {
            const broken = suspectBroken[sus.id];
            const layer = suspectLayerIndex[sus.id] ?? 0;
            const totalLayers = sus.alibi_layers?.length ?? 1;
            return (
              <div
                key={sus.id}
                onClick={() => openWindow("messenger")}
                style={{
                  cursor: "pointer",
                  border: "1px solid var(--panel-border)",
                  borderRadius: 2,
                  padding: "6px 8px",
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <span>{sus.name}</span>
                <span style={{ color: broken ? "var(--accent-red)" : "var(--text-dim)" }}>
                  {broken ? "FULLY BROKEN" : `LAYER ${layer + 1}/${totalLayers} HOLDING`}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
