import { useEffect, useRef, useState } from "react";
import { ask, type AskResponse, type Excerpt } from "./api";

const STARTERS = [
  "What does the subsidy cover?",
  "Where are the oldest pipes?",
  "Where should we focus outreach first?",
  "Which wards have the lowest subsidy participation?",
  "Is 25 Main Street eligible for the subsidy?",
];

// Same idea as the prototype: eligibility questions are never answered from risk scores.
const ELIGIBILITY =
  /eligib|qualif|deny|denied|reject (the|an|their)|approve (the|their|an) (application|subsidy)|who should get|should .* get the subsidy/i;

type Phase = "working" | "review" | "approved" | "rejected" | "guard" | "error" | "info";

type UserMsg = { id: number; role: "user"; text: string };
type BotMsg = {
  id: number;
  role: "bot";
  phase: Phase;
  text: string;
  original: string;
  response?: AskResponse;
  chk: boolean;
  editing: boolean;
  when?: string;
  copied: boolean;
  modelNote?: string;
};
type Msg = UserMsg | BotMsg;

const STATUS: Record<Phase, { label: string; style: React.CSSProperties }> = {
  working: { label: "Working", style: { background: "#E7ECF0", color: "#12263A" } },
  review: { label: "Draft · needs review", style: { background: "#FFD978", color: "#0B2545" } },
  approved: { label: "Approved", style: { background: "#0B6B74", color: "#fff" } },
  rejected: { label: "Rejected", style: { background: "#B2182B", color: "#fff" } },
  guard: { label: "Guardrail", style: { background: "#0B2545", color: "#fff" } },
  error: { label: "Error", style: { background: "#B2182B", color: "#fff" } },
  info: { label: "Help", style: { background: "#E7ECF0", color: "#12263A" } },
};

function shortSource(source: string): string {
  if (source.startsWith("2026 CAPITAL")) return "2026 Capital Budget Briefing Note";
  if (source.includes("Status Update")) return "BFPP Status Update";
  if (source.includes("Summary")) return "BFPP Ward Profile Summary";
  return source.replace(/\.pdf$/i, "");
}

// Shown when the local model did not answer. No answer is invented from the data.
const NO_MODEL_TEXT =
  "The local model is off, so no answer was written. " +
  "The ward rows and program passages the search found are listed in “How this answer was made”.";

type Props = { injected: { q: string; n: number } | null };

export default function Chat({ injected }: Props) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const lastInjected = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);

  const patch = (id: number, change: Partial<BotMsg>) =>
    setMsgs((all) => all.map((m) => (m.id === id && m.role === "bot" ? { ...m, ...change } : m)));

  async function send(raw: string) {
    const question = raw.trim();
    if (question.length < 3 || busy) return;
    const userId = nextId.current++;
    const botId = nextId.current++;
    const user: UserMsg = { id: userId, role: "user", text: question };
    setPrompt("");

    if (ELIGIBILITY.test(question)) {
      const text =
        "I can't decide or suggest who is eligible for the subsidy, and risk scores must never be used for that. " +
        "Program staff decide eligibility under the program rules.";
      setMsgs((all) => [
        ...all,
        user,
        { id: botId, role: "bot", phase: "guard", text, original: text, chk: false, editing: false, copied: false },
      ]);
      return;
    }

    setBusy(true);
    setMsgs((all) => [
      ...all,
      user,
      { id: botId, role: "bot", phase: "working", text: "", original: "", chk: false, editing: false, copied: false },
    ]);
    try {
      const response = await ask(question);
      const answered = Boolean(response.llm_available && response.answer);
      const text = answered ? (response.answer as string) : NO_MODEL_TEXT;
      const modelNote = answered
        ? `Written by a small local model (${response.model}), which can misread numbers. Check it against the table in “How this answer was made”.`
        : `Start Ollama with \`ollama serve\` and install ${response.model} with \`ollama pull ${response.model}\`.`;
      // Without a model answer there is nothing for staff to approve.
      patch(botId, { phase: answered ? "review" : "info", text, original: text, response, modelNote });
    } catch (err) {
      const reason = err instanceof TypeError ? "Could not reach the API. Is it running on port 8000?" : (err as Error).message;
      patch(botId, { phase: "error", text: reason, original: reason });
    } finally {
      setBusy(false);
    }
  }

  // The "Ask the agent about this ward" button on the map sends a question from outside.
  useEffect(() => {
    if (injected && injected.n !== lastInjected.current) {
      lastInjected.current = injected.n;
      void send(injected.q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [injected]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs]);

  return (
    <section className="chatcol" aria-label="Outreach agent">
      <div style={{ padding: "14px 18px", borderBottom: "1px solid #E7ECF0" }}>
        <h2 className="h" style={{ fontSize: 20 }}>Outreach agent</h2>
        <div style={{ fontSize: 14, color: "#4B5D6F" }}>
          Answers from the ward risk table and the BFPP program document. Staff review every answer before it is used.
        </div>
      </div>

      <div className="msgs" aria-live="polite">
        {msgs.length === 0 && (
          <>
            <div className="lab">Try asking</div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
              {STARTERS.map((t) => (
                <button key={t} className="chip" onClick={() => void send(t)}>{t}</button>
              ))}
            </div>
          </>
        )}

        {msgs.map((m) =>
          m.role === "user" ? (
            <div
              key={m.id}
              style={{ alignSelf: "flex-end", maxWidth: "88%", padding: "9px 13px", borderRadius: "12px 12px 3px 12px", background: "#0B2545", color: "#fff" }}
            >
              {m.text}
            </div>
          ) : (
            <BotCard key={m.id} m={m} patch={patch} />
          ),
        )}
        <div ref={endRef} />
      </div>

      <div style={{ padding: "12px 18px", borderTop: "1px solid #E7ECF0" }}>
        <label className="lab" htmlFor="ask" style={{ display: "block", marginBottom: 4 }}>Ask about outreach</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            id="ask"
            className="inp"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void send(prompt); }}
            placeholder="e.g. Where should we focus outreach on old sewers?"
            autoComplete="off"
          />
          <button className="btn btnp" disabled={prompt.trim().length < 3 || busy} onClick={() => void send(prompt)}>Send</button>
        </div>
        <div className="note" style={{ marginTop: 8 }}>
          The agent never sends anything; staff approve and copy. Approval is not saved yet.
        </div>
      </div>
    </section>
  );
}

function BotCard({ m, patch }: { m: BotMsg; patch: (id: number, c: Partial<BotMsg>) => void }) {
  const st = STATUS[m.phase];
  const r = m.response;
  const passages: Excerpt[] = r ? r.passages : [];
  const canReview = m.phase === "review";

  return (
    <div className="card" style={{ alignSelf: "stretch", padding: "14px 16px", borderColor: m.phase === "approved" ? "#0E7C86" : undefined }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "6px 10px", marginBottom: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>Agent</span>
        <span className="pill" style={st.style}>{st.label}</span>
      </div>

      {m.phase === "working" && (
        <div style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 14 }}>
          <svg className="spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0B6B74" strokeWidth="3" aria-hidden="true">
            <path d="M12 3a9 9 0 1 0 9 9" />
          </svg>
          Selecting wards, searching the program documents and writing the answer. This can take up to a minute…
        </div>
      )}

      {m.phase === "error" && <div className="errbox">{m.text}</div>}

      {m.phase !== "working" && m.phase !== "error" && (
        <>
          {m.editing && canReview ? (
            <textarea className="ta" aria-label="Edit the answer" value={m.text} onChange={(e) => patch(m.id, { text: e.target.value })} />
          ) : (
            <p style={{ margin: 0, whiteSpace: "pre-line" }}>{m.text}</p>
          )}

          {m.modelNote && <div className="warnbox">{m.modelNote}</div>}

          {r && (
            <details style={{ marginTop: 10, borderTop: "1px solid #E7ECF0" }}>
              <summary>How this answer was made</summary>
              {r.wards.length > 0 && (
              <>
              <p style={{ margin: "4px 0 10px", fontSize: 13 }}><strong>Criterion used.</strong> {r.basis}.</p>
              <div className="lab" style={{ marginBottom: 2 }}>[1] Ward rows used</div>
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr><th>Priority</th><th>Ward</th><th>Failure rank</th><th>Report rank</th><th>Old pipes</th><th>Combined sewer</th><th>With device</th><th>Without</th><th>Flood reports</th></tr>
                  </thead>
                  <tbody>
                    {r.wards.map((w) => (
                      <tr key={w.ward_id}>
                        <td>#{w.priority_rank}</td>
                        <td>{w.ward_id} {w.ward_name}</td>
                        <td>{w.failure_rank}</td>
                        <td>{w.low_report_rank}</td>
                        <td>{w.old_pipe_pct.toFixed(1)}%</td>
                        <td>{w.combined_sewer_pct.toFixed(1)}%</td>
                        <td>{(w.subsidy_participation * 100).toFixed(1)}%</td>
                        <td>{w.properties_without_fpd.toLocaleString("en-CA")}</td>
                        <td>{w.flood_reports_2019_2022}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="note" style={{ marginTop: 4 }}>
                Failure rank 1 = highest sewage-failure pressure. Report rank 1 = fewest flood reports per eligible home.
                Old pipes and combined sewer are shares of the ward's sewer network. Flood reports are 2019–2022.
                The table lists only the wards the search picked, not all 25.
              </div>
              </>
              )}
              {passages.length > 0 && (
                <>
                  <div className="lab" style={{ margin: "10px 0 4px" }}>[2] Program document passages</div>
                  {passages.map((x) => (
                    <div className="excerpt" key={`${x.source}-${x.page}-${x.text.slice(0, 20)}`}>
                      <div style={{ fontWeight: 600 }}>{shortSource(x.source)} · page {x.page}</div>
                      <div style={{ whiteSpace: "pre-line" }}>{x.text.length > 400 ? `${x.text.slice(0, 400)}…` : x.text}</div>
                    </div>
                  ))}
                  <div className="note" style={{ marginBottom: 8 }}>
                    Passages are cut automatically from the PDFs and found by meaning, so the best one may not be first.
                    Text from maps may not read well.
                  </div>
                </>
              )}
            </details>
          )}

          {canReview && (
            <div style={{ marginTop: 10, padding: 12, borderRadius: 8, background: "#FDF1D3", border: "1px solid #C9A227" }}>
              <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 6 }}>Staff review needed before this is used</div>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start", fontSize: 14, cursor: "pointer", minHeight: 44 }}>
                <input type="checkbox" checked={m.chk} onChange={() => patch(m.id, { chk: !m.chk })} style={{ width: 20, height: 20, margin: "1px 0 0", flex: "none", accentColor: "#0B6B74" }} />
                <span>I checked the wards and numbers against the map and sources, and this is not used to decide eligibility.</span>
              </label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                <button
                  className="btn btnp"
                  disabled={!m.chk}
                  onClick={() => patch(m.id, { phase: "approved", editing: false, when: new Date().toLocaleString("en-CA", { dateStyle: "medium", timeStyle: "short" }) })}
                >
                  Approve
                </button>
                <button className="btn" onClick={() => patch(m.id, { editing: !m.editing })}>{m.editing ? "Done editing" : "Edit"}</button>
                <button className="btn btnr" onClick={() => patch(m.id, { phase: "rejected", editing: false })}>Reject</button>
              </div>
            </div>
          )}

          {m.phase === "approved" && (
            <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, padding: "10px 12px", borderRadius: 8, background: "#E1F2F3" }}>
              <span style={{ flex: 1, minWidth: 180, fontSize: 14 }}>
                <strong>Approved by staff</strong> · {m.when}{m.text !== m.original ? " · edited by staff" : ""}
              </span>
              <button
                className="btn"
                style={{ minHeight: 40 }}
                onClick={() => {
                  try { void navigator.clipboard.writeText(m.text); } catch { /* clipboard may be blocked */ }
                  patch(m.id, { copied: true });
                }}
              >
                {m.copied ? "Copied" : "Copy text"}
              </button>
            </div>
          )}

          {m.phase === "rejected" && (
            <div className="errbox" style={{ marginTop: 10 }}>
              <strong>Rejected.</strong> This answer will not be used. Rephrase the question to try again.
            </div>
          )}

          {m.phase === "guard" && (
            <div style={{ marginTop: 10, padding: "10px 12px", borderRadius: 8, background: "#EEF3F7", fontSize: 14 }}>
              <strong>Guardrail:</strong> risk scores never decide who gets the subsidy. Eligibility is decided by program staff under the program rules.
            </div>
          )}
        </>
      )}
    </div>
  );
}
