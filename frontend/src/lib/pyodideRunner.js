/**
 * Runs player-submitted Python entirely in the browser using Pyodide
 * (CPython compiled to WebAssembly). This replaces the old backend
 * Docker/Piston sandbox: no server-side execution, no API keys, no
 * per-run infrastructure cost, and no network round trip while the code
 * itself is running.
 *
 * Contract mirrors the old docker_runner/piston_runner harness exactly, so
 * nothing about grading changes: the player writes clean_data(records) and
 * solve(cleaned); this returns {cleaned_count, answer, error}. The backend
 * (backend/sandbox/executor.py) still holds the secret unit_tests and does
 * the actual pass/fail grading - this module never sees expected answers,
 * so results can't be spoofed just by reading client bundle code.
 */

const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.2/full/pyodide.js";
const RUN_TIMEOUT_MS = 10_000;

let pyodideReadyPromise = null;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });
}

/** Idempotent: safe to call from multiple components, only loads once. */
export function preloadPyodide() {
  if (typeof window === "undefined") return Promise.resolve(null);

  if (!pyodideReadyPromise) {
    pyodideReadyPromise = (async () => {
      await loadScript(PYODIDE_CDN);
      const pyodide = await window.loadPyodide({
        indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.2/full/",
      });
      return pyodide;
    })();
  }
  return pyodideReadyPromise;
}

function buildHarness(playerSource) {
  const indented = playerSource
    .split("\n")
    .map((line) => "    " + line)
    .join("\n");

  // Same shape as the old docker_runner/piston_runner _build_run_script:
  // load the dataset, run the player's clean_data/solve, emit one
  // parseable __RESULT__ line. `poisoned_json` is injected as a Python
  // global below rather than read from a file, since there's no
  // filesystem here.
  return `
import json, traceback

result = {"cleaned_count": None, "answer": None, "error": None}

try:
    raw_records = json.loads(poisoned_json)

${indented}

    cleaned = clean_data(raw_records)
    result["cleaned_count"] = len(cleaned)

    answer = solve(cleaned)
    result["answer"] = answer
except Exception:
    result["error"] = traceback.format_exc()

result
`;
}

/**
 * @param {string} playerSource - the player's Python (clean_data + solve)
 * @param {any[]} poisonedDataset - the case's poisoned dataset (JSON array)
 * @returns {Promise<{cleaned_count: number|null, answer: any, error: string|null, runtime_ms: number}>}
 */
export async function runPlayerSubmission(playerSource, poisonedDataset) {
  const pyodide = await preloadPyodide();
  const start = performance.now();

  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error("__TIMEOUT__")), RUN_TIMEOUT_MS)
  );

  try {
    pyodide.globals.set("poisoned_json", JSON.stringify(poisonedDataset));

    const resultProxy = await Promise.race([
      pyodide.runPythonAsync(buildHarness(playerSource)),
      timeout,
    ]);

    // Pyodide returns a PyProxy for the dict; convert to a plain JS object.
    const result = resultProxy.toJs
      ? resultProxy.toJs({ dict_converter: Object.fromEntries })
      : resultProxy;
    if (resultProxy.destroy) resultProxy.destroy();

    return {
      cleaned_count: result.cleaned_count ?? null,
      answer: result.answer ?? null,
      error: result.error ?? null,
      runtime_ms: Math.round(performance.now() - start),
    };
  } catch (err) {
    if (err && err.message === "__TIMEOUT__") {
      return {
        cleaned_count: null,
        answer: null,
        error: `Execution exceeded the ${RUN_TIMEOUT_MS / 1000}s time limit.`,
        runtime_ms: RUN_TIMEOUT_MS,
      };
    }
    // Syntax errors etc. surface here rather than inside the try/except
    // in the harness (that one only catches runtime errors in the
    // player's functions once they're already defined).
    return {
      cleaned_count: null,
      answer: null,
      error: err?.message ?? String(err),
      runtime_ms: Math.round(performance.now() - start),
    };
  }
}
