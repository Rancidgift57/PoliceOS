import { useState } from "react";
import { useGameStore } from "@/store/useGameStore";

export default function Login() {
  const login = useGameStore((s) => s.login);
  const register = useGameStore((s) => s.register);

  const [mode, setMode] = useState("login"); // "login" | "register"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(username, password);
      } else {
        await register(username, password, displayName);
      }
    } catch (err) {
      setError(err.message ?? "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-tricolor-rule" />
        <div className="login-header">
          <div className="login-badge-seal">★</div>
          <div className="login-title">Police OS</div>
          <div className="login-subtitle">
            {mode === "login" ? "Officer sign-in" : "New officer enrollment"}
          </div>
        </div>

        <form className="login-body" onSubmit={handleSubmit}>
          <div className="login-field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. inspector_rao"
              required
              minLength={3}
              maxLength={24}
            />
          </div>

          {mode === "register" && (
            <div className="login-field">
              <label htmlFor="displayName">Display name (optional)</label>
              <input
                id="displayName"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="e.g. Insp. Meera Rao"
                maxLength={40}
              />
            </div>
          )}

          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              minLength={6}
              maxLength={128}
            />
          </div>

          {error && <div className="login-error">{error}</div>}

          <button className="login-submit" type="submit" disabled={busy}>
            {busy
              ? "Verifying credentials…"
              : mode === "login"
              ? "Report for duty"
              : "Issue my badge"}
          </button>
        </form>

        <div className="login-toggle">
          {mode === "login" ? (
            <>
              New to the bureau?{" "}
              <button type="button" onClick={() => { setMode("register"); setError(null); }}>
                Enroll here
              </button>
            </>
          ) : (
            <>
              Already have a badge?{" "}
              <button type="button" onClick={() => { setMode("login"); setError(null); }}>
                Sign in
              </button>
            </>
          )}
        </div>

        <div className="login-footnote">
          Your badge number is assigned on enrollment and identifies your case
          progress across every daily file.
        </div>
      </div>
    </div>
  );
}
