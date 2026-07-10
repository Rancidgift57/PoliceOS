import { useEffect, useState } from "react";
import dynamic from "next/dynamic";

// PoliceOS touches window/localStorage-adjacent browser APIs (Monaco editor,
// Pyodide) via its child components, so it's loaded client-only to avoid
// Next.js trying to server-render any of that.
const PoliceOS = dynamic(() => import("@/components/os/PoliceOS"), { ssr: false });

const PLAYER_ID_KEY = "police-os:player-id";

function getOrCreatePlayerId() {
  let id = window.localStorage.getItem(PLAYER_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    window.localStorage.setItem(PLAYER_ID_KEY, id);
  }
  return id;
}

export default function Home() {
  const [playerId, setPlayerId] = useState(null);

  useEffect(() => {
    setPlayerId(getOrCreatePlayerId());
  }, []);

  if (!playerId) return null;

  return <PoliceOS playerId={playerId} />;
}
