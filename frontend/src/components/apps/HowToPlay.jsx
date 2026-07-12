const SECTION_TITLE = {
  color: "var(--text-dim)",
  textTransform: "uppercase",
  fontSize: 11,
  letterSpacing: "0.05em",
  marginBottom: 6,
};

const BODY = { lineHeight: 1.6, color: "var(--text-primary)" };
const CODE = {
  fontFamily: "var(--mono-font)",
  background: "var(--os-bg)",
  border: "1px solid var(--panel-border)",
  borderRadius: 2,
  padding: "8px 10px",
  whiteSpace: "pre",
  overflowX: "auto",
  fontSize: 11.5,
  lineHeight: 1.6,
};

function Section({ title, children }) {
  return (
    <div>
      <div style={SECTION_TITLE}>{title}</div>
      <div style={BODY}>{children}</div>
    </div>
  );
}

export default function HowToPlay() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, fontSize: 12 }}>
      <Section title="The loop, in one sentence">
        Clean a poisoned dataset and run an algorithm in <b>DB_TERMINAL</b> to unlock evidence,
        then use that evidence in <b>SECURE_MESSENGER</b> to break a suspect's story — repeat
        until every suspect is fully broken and the case closes itself.
      </Section>

      <Section title="The windows">
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div>
            <b>DB_TERMINAL</b> — where you write Python. Every challenge gives you a poisoned
            dataset (some records are corrupted on purpose) and asks for two functions: one that
            filters out the bad records, one that computes an answer from the good ones. Read the
            <i> Scene Briefing</i> in EVIDENCE_BOARD and the prompt above the editor for what
            "corrupted" and "the answer" mean for this specific case.
          </div>
          <div>
            <b>EVIDENCE_BOARD</b> — the victim, crime scene, a riddle-style scene briefing, your
            unlocked evidence, and every suspect's current alibi-layer status. Locked evidence
            shows as blacked-out text until you earn it.
          </div>
          <div>
            <b>SECURE_MESSENGER</b> — where you interrogate suspects. Click a suspect on the
            Evidence Board (or use the tabs here) to open a chat with them. This is a real
            back-and-forth: vague accusations get denied, but citing the *specific content* of a
            piece of evidence you've actually unlocked breaks their story.
          </div>
          <div>
            <b>CASE_FILES</b> — your training file, today's case, brand-new challenges you haven't
            opened yet, and any case you started but didn't finish before it rotated out
            (your personal backlog — nothing is ever lost, just filed for later).
          </div>
          <div>
            <b>LEADERBOARD</b> — how you stack up on the current case, plus your solve streak
            across days.
          </div>
        </div>
      </Section>

      <Section title="Reading the Scene Briefing riddle">
        Every case includes a short, cryptic riddle about the crime scene — it's not decoration.
        It's written to point toward which suspect or which piece of evidence actually matters,
        without spelling it out. Re-read it after you unlock each new piece of evidence; lines
        that seemed abstract at first usually click once you know what they're pointing at.
      </Section>

      <Section title="Writing clean_data and solve">
        Every DB_TERMINAL challenge always wants exactly these two functions — the field names
        change per case, but the shape never does:
        <div style={{ ...CODE, marginTop: 8 }}>
{`def clean_data(records):
    # records is a list of dicts. Some are corrupted on purpose -
    # the prompt above tells you exactly what "corrupted" means here.
    # Return only the valid ones.
    cleaned = []
    for r in records:
        if <record is valid>:
            cleaned.append(r)
    return cleaned


def solve(cleaned_records):
    # cleaned_records is whatever clean_data returned.
    # Compute and return the answer the prompt asks for -
    # often a count, an id, or a specific record's field.
    return <the answer>`}
        </div>
      </Section>

      <Section title="New to Python? Start here">
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div>
            • A <code>dict</code> is a record: <code>r["badge"]</code> reads its "badge" field.
          </div>
          <div>
            • <code>isinstance(x, int)</code> checks if <code>x</code> is a whole number —
            useful for spotting a field that's secretly a string like <code>"unknown"</code>.
          </div>
          <div>
            • <code>if r["field"] is None: continue</code> skips a record inside a loop without
            adding it to your cleaned list.
          </div>
          <div>
            • <code>len(some_list)</code> counts items — often literally the answer a challenge
            wants.
          </div>
          <div>
            • Run your code often. A wrong-but-running attempt against real evidence teaches you
            more than staring at a blank editor.
          </div>
        </div>
      </Section>

      <Section title="Interrogating suspects">
        Don't just accuse — <i>cite</i>. "I think you're lying" never works. "Explain why your
        badge shows you at Fort Chowki when the log says otherwise" works, once you've actually
        unlocked the evidence that says so. If you're stuck on a suspect for a few messages in a
        row, a <b>Request hint</b> button appears in SECURE_MESSENGER with a nudge — it won't hand
        you the answer, just point you toward what you're missing.
      </Section>

      <Section title="Start with the training file">
        If you haven't yet, open <b>CASE_FILES → Training File → Operation Prashikshan</b> first.
        It's a small, fixed case built to teach exactly this loop before you touch a real,
        randomly-generated one.
      </Section>
    </div>
  );
}
