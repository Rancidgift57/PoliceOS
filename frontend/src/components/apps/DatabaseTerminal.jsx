import { useState, useMemo, useEffect } from "react";
import Editor from "@monaco-editor/react";
import { useGameStore } from "@/store/useGameStore";
import { preloadPyodide } from "@/lib/pyodideRunner";

function buildStarterTemplate(challenge) {
  // Field names differ per case (this project's dataset templates use
  // different shapes - transaction records, cell pings, this tutorial's
  // duty log, or whatever an LLM-generated daily case invents) so there's
  // no one hardcoded set of field names that's correct for every
  // challenge. The player's actual field names come from the prompt /
  // cleaning spec shown above the editor; this skeleton just gets the
  // clean_data/solve function contract right and echoes that spec back as
  // a reminder, rather than guessing field names that would silently be
  // wrong (and throw a runtime KeyError) for most challenges.
  const cleaningSpec = challenge?.cleaning_spec ?? "See the cleaning rule above.";
  const algorithmSpec = challenge?.algorithm_spec ?? "See the algorithm spec above.";
  return `def clean_data(records):
    """Cleaning rule:
    ${cleaningSpec}
    """
    cleaned = []
    for r in records:
        # TODO: keep only the records that satisfy the cleaning rule above
        cleaned.append(r)
    return cleaned


def solve(cleaned_records):
    """Algorithm:
    ${algorithmSpec}
    """
    # TODO: compute and return the answer described above
    return len(cleaned_records)
`;
}

const STATUS_LABEL = {
  passed: "MATCH FOUND",
  failed_cleaning: "CLEANING FAILED",
  failed_algorithm: "ALGORITHM FAILED",
  runtime_error: "RUNTIME ERROR",
  timeout: "TIMED OUT",
};

export default function DatabaseTerminal() {
  const caseFile = useGameStore((s) => s.caseFile);
  const runSubmission = useGameStore((s) => s.runSubmission);
  const solvedChallengeIds = useGameStore((s) => s.solvedChallengeIds);

  const challenge = caseFile?.challenges?.[0];
  const [code, setCode] = useState(() => buildStarterTemplate(challenge));
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [pyodideReady, setPyodideReady] = useState(false);

  // Reset to a fresh starter whenever the player switches to a different
  // challenge (e.g. tutorial -> today's case) - otherwise code written for
  // one dataset's fields would silently carry over and throw a runtime
  // KeyError against the next case's differently-shaped records.
  useEffect(() => {
    setCode(buildStarterTemplate(challenge));
    setResult(null);
  }, [challenge?.id]);

  // Kick off the Python runtime download as soon as the terminal opens,
  // so it's warm by the time the player hits "Run" instead of eating the
  // ~a few seconds first-load cost on their first submission.
  useEffect(() => {
    let cancelled = false;
    preloadPyodide().then(() => {
      if (!cancelled) setPyodideReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const solved = useMemo(
    () => (challenge ? solvedChallengeIds.includes(challenge.id) : false),
    [challenge, solvedChallengeIds]
  );

  const handleRun = async () => {
    if (!challenge) return;
    setRunning(true);
    setResult(null);
    try {
      const res = await runSubmission(challenge.id, code);
      setResult(res);
    } finally {
      setRunning(false);
    }
  };

  if (!challenge) {
    return <div style={{ color: "var(--text-dim)" }}>Loading case data…</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8 }}>
      <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}>
        <strong style={{ color: "var(--accent-amber)" }}>{challenge.title}</strong>
        {solved && <span style={{ color: "var(--accent-amber)" }}> — SOLVED</span>}
        <div>{challenge.prompt}</div>
      </div>

      <div style={{ flex: 1, border: "1px solid var(--panel-border)", borderRadius: 2, overflow: "hidden" }}>
        <Editor
          height="100%"
          defaultLanguage="python"
          theme="vs-dark"
          value={code}
          onChange={(v) => setCode(v ?? "")}
          options={{ fontSize: 13, minimap: { enabled: false }, fontFamily: "var(--mono-font)" }}
        />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button
          onClick={handleRun}
          disabled={running || !pyodideReady}
          style={{
            background: "var(--accent-amber-dim)",
            color: "var(--accent-amber)",
            border: "1px solid var(--accent-amber-dim)",
            padding: "6px 14px",
            borderRadius: 2,
            cursor: running || !pyodideReady ? "default" : "pointer",
            fontFamily: "var(--mono-font)",
            fontSize: 12,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            opacity: pyodideReady ? 1 : 0.5,
          }}
        >
          {!pyodideReady ? "Loading Python runtime…" : running ? "Running…" : "Run against evidence"}
        </button>

        {result && (
          <span style={{ fontSize: 12, color: result.status === "passed" ? "var(--accent-amber)" : "var(--accent-red)" }}>
            {STATUS_LABEL[result.status] || result.status}
            {result.status !== "passed" && result.stdout ? ` — ${result.stdout}` : ""}
          </span>
        )}
      </div>
    </div>
  );
}
