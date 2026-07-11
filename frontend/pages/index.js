import { useEffect } from "react";
import dynamic from "next/dynamic";
import { useGameStore } from "@/store/useGameStore";
import Login from "@/components/auth/Login";

// PoliceOS touches window/localStorage-adjacent browser APIs (Monaco editor,
// Pyodide) via its child components, so it's loaded client-only to avoid
// Next.js trying to server-render any of that.
const PoliceOS = dynamic(() => import("@/components/os/PoliceOS"), { ssr: false });

export default function Home() {
  const user = useGameStore((s) => s.user);
  const authHydrated = useGameStore((s) => s.authHydrated);
  const hydrateAuth = useGameStore((s) => s.hydrateAuth);

  useEffect(() => {
    hydrateAuth();
  }, [hydrateAuth]);

  if (!authHydrated) return null; // avoid a login-screen flash while we check localStorage
  if (!user) return <Login />;

  return <PoliceOS playerId={user.player_id} />;
}
