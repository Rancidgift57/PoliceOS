import { useEffect, useState } from "react";
import { useGameStore } from "@/store/useGameStore";

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function CaseTile({ summary, active, onOpen, tag }) {
  return (
    <div className={`case-tile${active ? " is-active" : ""}`} onClick={() => onOpen(summary.case_id)}>
      <div className="case-tile-codename">{summary.codename || "Operation Unknown"}</div>
      <div className="case-tile-title">
        {summary.title}
        {tag}
      </div>
      <div className="case-tile-meta">{formatDate(summary.generated_at)}</div>
    </div>
  );
}

export default function CaseFiles() {
  const playerId = useGameStore((s) => s.playerId);
  const caseId = useGameStore((s) => s.caseId);
  const fetchCaseBoard = useGameStore((s) => s.fetchCaseBoard);
  const switchCase = useGameStore((s) => s.switchCase);

  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);

  async function reload() {
    if (!playerId) return;
    setLoading(true);
    const data = await fetchCaseBoard();
    setBoard(data);
    setLoading(false);
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerId]);

  async function open(id) {
    await switchCase(id);
    reload();
  }

  if (loading && !board) {
    return <div style={{ color: "var(--text-dim)" }}>Pulling case files…</div>;
  }
  if (!board) return null;

  return (
    <div className="case-board">
      {board.tutorial && (
        <div>
          <div className="case-board-section-title">Training file</div>
          <CaseTile
            summary={board.tutorial}
            active={caseId === board.tutorial.case_id}
            onOpen={open}
            tag={
              <span className="case-tile-tag tutorial">
                {board.tutorial.solved ? "completed" : "start here"}
              </span>
            }
          />
        </div>
      )}

      {board.today && (
        <div>
          <div className="case-board-section-title">Today's case</div>
          <CaseTile
            summary={board.today}
            active={caseId === board.today.case_id}
            onOpen={open}
            tag={board.today.solved ? <span className="case-tile-tag solved">closed</span> : null}
          />
        </div>
      )}

      <div>
        <div className="case-board-section-title">New challenges</div>
        {board.new_challenges.length === 0 && (
          <div className="case-board-empty">Nothing new yet — check back after midnight IST.</div>
        )}
        {board.new_challenges.map((c) => (
          <CaseTile
            key={c.case_id}
            summary={c}
            active={caseId === c.case_id}
            onOpen={open}
            tag={<span className="case-tile-tag new">new</span>}
          />
        ))}
      </div>

      <div>
        <div className="case-board-section-title">Pending challenges</div>
        {board.pending_challenges.length === 0 && (
          <div className="case-board-empty">No unfinished cases in your backlog.</div>
        )}
        {board.pending_challenges.map((c) => (
          <CaseTile
            key={c.case_id}
            summary={c}
            active={caseId === c.case_id}
            onOpen={open}
            tag={<span className="case-tile-tag pending">unsolved</span>}
          />
        ))}
      </div>
    </div>
  );
}
