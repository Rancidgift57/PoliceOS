import { useEffect, useRef, useState } from "react";
import { useGameStore } from "@/store/useGameStore";
import Window from "@/components/os/Window";
import DatabaseTerminal from "@/components/apps/DatabaseTerminal";
import EvidenceBoard from "@/components/apps/EvidenceBoard";
import SecureMessenger from "@/components/apps/SecureMessenger";
import Leaderboard from "@/components/apps/Leaderboard";
import CaseFiles from "@/components/apps/CaseFiles";

const APP_REGISTRY = {
  terminal: {
    title: "DB_TERMINAL // sandbox",
    component: DatabaseTerminal,
    initial: { x: 40, y: 30, w: 620, h: 440 },
  },
  evidence: {
    title: "EVIDENCE_BOARD",
    component: EvidenceBoard,
    initial: { x: 700, y: 30, w: 420, h: 440 },
  },
  messenger: {
    title: "SECURE_MESSENGER",
    component: SecureMessenger,
    initial: { x: 700, y: 500, w: 420, h: 360 },
  },
  leaderboard: {
    title: "LEADERBOARD",
    component: Leaderboard,
    initial: { x: 40, y: 500, w: 420, h: 320 },
  },
  casefiles: {
    title: "CASE_FILES",
    component: CaseFiles,
    initial: { x: 1140, y: 30, w: 340, h: 560 },
  },
};

export default function PoliceOS({ playerId }) {
  const initSession = useGameStore((s) => s.initSession);
  const fetchCaseBoard = useGameStore((s) => s.fetchCaseBoard);
  const caseFile = useGameStore((s) => s.caseFile);
  const activeWindows = useGameStore((s) => s.activeWindows);
  const focusedWindow = useGameStore((s) => s.focusedWindow);
  const openWindow = useGameStore((s) => s.openWindow);
  const user = useGameStore((s) => s.user);
  const logout = useGameStore((s) => s.logout);

  const [bootstrapped, setBootstrapped] = useState(false);
  const ranOnce = useRef(false);

  useEffect(() => {
    if (ranOnce.current) return;
    ranOnce.current = true;

    (async () => {
      // A brand-new officer (never opened the tutorial case) is walked
      // through Operation Prashikshan first; everyone else lands straight
      // on today's rotating case, same as before login existed.
      const board = await fetchCaseBoard();
      const isFirstTimer = board?.tutorial && !board.tutorial.started;
      await initSession(playerId, isFirstTimer ? board.tutorial.case_id : undefined);
      setBootstrapped(true);
    })();
  }, [playerId, initSession, fetchCaseBoard]);

  if (!bootstrapped) {
    return (
      <div className="police-os" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "var(--text-dim)", fontSize: 12 }}>Pulling your case file…</div>
      </div>
    );
  }

  return (
    <div className="police-os">
      {caseFile && (
        <div style={{ position: "absolute", top: 8, left: 12, fontSize: 11, color: "var(--text-dim)" }}>
          {caseFile.codename ? `${caseFile.codename.toUpperCase()} — ` : ""}
          {caseFile.case_id?.toUpperCase()} — {caseFile.title}
        </div>
      )}

      {user && (
        <div className="officer-chip">
          <span className="badge-number">{user.badge_number}</span>
          <span>{user.display_name || user.username}</span>
          <button onClick={logout}>Sign out</button>
        </div>
      )}

      {activeWindows.map((id) => {
        const app = APP_REGISTRY[id];
        if (!app) return null;
        const AppComponent = app.component;
        return (
          <Window key={id} id={id} title={app.title} initial={app.initial}>
            <AppComponent />
          </Window>
        );
      })}

      <div className="os-taskbar">
        {Object.entries(APP_REGISTRY).map(([id, app]) => (
          <div
            key={id}
            className={`os-taskbar-item${focusedWindow === id ? " active" : ""}`}
            onClick={() => openWindow(id)}
          >
            {app.title.split(" //")[0]}
          </div>
        ))}
      </div>
    </div>
  );
}
