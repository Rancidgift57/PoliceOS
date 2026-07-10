import { useEffect } from "react";
import { useGameStore } from "@/store/useGameStore";
import Window from "@/components/os/Window";
import DatabaseTerminal from "@/components/apps/DatabaseTerminal";
import EvidenceBoard from "@/components/apps/EvidenceBoard";
import SecureMessenger from "@/components/apps/SecureMessenger";
import Leaderboard from "@/components/apps/Leaderboard";

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
};

export default function PoliceOS({ playerId }) {
  const initSession = useGameStore((s) => s.initSession);
  const caseFile = useGameStore((s) => s.caseFile);
  const activeWindows = useGameStore((s) => s.activeWindows);
  const focusedWindow = useGameStore((s) => s.focusedWindow);
  const openWindow = useGameStore((s) => s.openWindow);

  useEffect(() => {
    initSession(playerId);
  }, [playerId, initSession]);

  return (
    <div className="police-os">
      {caseFile && (
        <div style={{ position: "absolute", top: 8, left: 12, fontSize: 11, color: "var(--text-dim)" }}>
          {caseFile.case_id?.toUpperCase()} — {caseFile.title}
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
