import { useState, useMemo } from "react";
import Editor from "@monaco-editor/react";
import { useGameStore } from "@/store/useGameStore";

const STARTER_TEMPLATE = `def clean_data(records):
    """Return only the valid records.
    A valid record has a positive integer timestamp, a numeric amount,
    and a unique record_id."""
    seen_ids = set()
    cleaned = []
    for r in records:
        if r["timestamp"] <= 0:
            continue
        if not isinstance(r["amount"], (int, float)):
            continue
        if r["record_id"] in seen_ids:
            continue
        seen_ids.add(r["record_id"])
        cleaned.append(r)
    return cleaned


def solve(cleaned_records):
    """Binary search the cleaned, timestamp-sorted records for the
    transaction tied to the crime. Return its record_id."""
    records = sorted(cleaned_records, key=lambda r: r["timestamp"])
    target_ts = records[0]["timestamp"] + 500 * 37  # threshold from the case brief

    lo, hi = 0, len(records) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if records[mid]["timestamp"] < target_ts:
            lo = mid + 1
        else:
            hi = mid - 1
    return records[lo]["record_id"]
`;

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
  const [code, setCode] = useState(STARTER_TEMPLATE);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

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
          disabled={running}
          style={{
            background: "var(--accent-amber-dim)",
            color: "var(--accent-amber)",
            border: "1px solid var(--accent-amber-dim)",
            padding: "6px 14px",
            borderRadius: 2,
            cursor: running ? "default" : "pointer",
            fontFamily: "var(--mono-font)",
            fontSize: 12,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          {running ? "Running…" : "Run against evidence"}
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
