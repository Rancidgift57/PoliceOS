import { useEffect, useState } from "react";
import { useGameStore } from "@/store/useGameStore";

export default function Leaderboard() {
  const caseFile = useGameStore((s) => s.caseFile);
  const playerId = useGameStore((s) => s.playerId);
  const caseSolved = useGameStore((s) => s.caseSolved);
  const fetchLeaderboard = useGameStore((s) => s.fetchLeaderboard);
  const fetchPlayerStats = useGameStore((s) => s.fetchPlayerStats);

  const [entries, setEntries] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!caseFile || !playerId) return;
    let cancelled = false;

    (async () => {
      setLoading(true);
      const [board, playerStats] = await Promise.all([
        fetchLeaderboard(caseFile.case_id),
        fetchPlayerStats(playerId),
      ]);
      if (!cancelled) {
        setEntries(board.entries ?? []);
        setStats(playerStats);
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // Re-fetch whenever the case flips to solved, so a fresh solve shows up immediately.
  }, [caseFile, playerId, caseSolved, fetchLeaderboard, fetchPlayerStats]);

  if (!caseFile) {
    return <div style={{ color: "var(--text-dim)" }}>Loading case data…</div>;
  }

  return (
    <div style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 14 }}>
      {stats && (
        <div style={{ display: "flex", gap: 16 }}>
          <div>
            <div style={{ color: "var(--text-dim)", fontSize: 10, textTransform: "uppercase" }}>Streak</div>
            <div style={{ color: "var(--accent-amber)", fontSize: 16 }}>{stats.current_streak}</div>
          </div>
          <div>
            <div style={{ color: "var(--text-dim)", fontSize: 10, textTransform: "uppercase" }}>Best</div>
            <div style={{ fontSize: 16 }}>{stats.longest_streak}</div>
          </div>
          <div>
            <div style={{ color: "var(--text-dim)", fontSize: 10, textTransform: "uppercase" }}>Solved</div>
            <div style={{ fontSize: 16 }}>{stats.total_cases_solved}</div>
          </div>
        </div>
      )}

      <div>
        <div style={{ color: "var(--text-dim)", textTransform: "uppercase", fontSize: 11, marginBottom: 6 }}>
          Today's fastest closes
        </div>
        {loading && <div style={{ color: "var(--text-dim)" }}>Loading…</div>}
        {!loading && entries.length === 0 && (
          <div style={{ color: "var(--text-dim)" }}>No one has closed this case yet.</div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {entries.map((e, i) => (
            <div
              key={`${e.player_id}-${e.solved_at}`}
              style={{
                display: "flex",
                justifyContent: "space-between",
                border: "1px solid var(--panel-border)",
                borderRadius: 2,
                padding: "4px 8px",
                color: e.player_id === playerId ? "var(--accent-amber)" : "var(--text-primary)",
              }}
            >
              <span>
                #{i + 1} {e.player_id === playerId ? "you" : e.player_id.slice(0, 8)}
              </span>
              <span style={{ color: "var(--text-dim)" }}>
                {e.submission_attempts + e.interrogation_attempts} moves
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
