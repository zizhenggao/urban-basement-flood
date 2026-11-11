// Text is kept exactly as in the design prototype (v2). Parts of it, such as
// "machine learning" and "sample numbers", no longer match the real index and
// are flagged as pending a decision.
export default function About({ onClose }: { onClose: () => void }) {
  return (
    <div className="drawer">
      <div className="dpanel" role="dialog" aria-label="About and limits">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <h2 className="h" style={{ fontSize: 22, flex: 1 }}>About and limits</h2>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
        <p style={{ margin: "0 0 14px", padding: "12px 14px", borderRadius: 8, background: "#0B2545", color: "#fff", fontWeight: 600 }}>
          Risk scores guide where outreach starts. They never decide subsidy eligibility.
        </p>
        <h3 style={{ margin: "0 0 6px", fontSize: 16 }}>How it works</h3>
        <p style={{ margin: "0 0 14px", fontSize: 14 }}>
          A machine learning model ranks Toronto's 25 wards by relative basement flooding risk. The agent reads a
          planner's question, picks the matching rows from the ward table, searches the Basement Flooding Protection
          Program (BFPP) document, and writes one paragraph with its sources. A staff member approves, edits or rejects
          every answer. The agent cannot send, publish or save anything.
        </p>
        <h3 style={{ margin: "0 0 6px", fontSize: 16 }}>Data sources</h3>
        <ul style={{ margin: "0 0 14px", paddingLeft: 20, fontSize: 14 }}>
          <li>City of Toronto open data: sewer pipe age and type, past flood reports, terrain, street trees, ward boundaries</li>
          <li>City of Toronto Basement Flooding Protection Program document</li>
          <li>This prototype uses sample numbers, not model output</li>
        </ul>
        <h3 style={{ margin: "0 0 6px", fontSize: 16 }}>Known limits</h3>
        <ul style={{ margin: "0 0 14px", paddingLeft: 20, fontSize: 14 }}>
          <li>Scores show relative risk between wards, not the chance a home will flood.</li>
          <li>Past flood reports can under-count areas where fewer people report.</li>
          <li>A ward average can hide streets with very different risk.</li>
          <li>The agent can make mistakes, which is why every answer shows its sources and needs approval.</li>
        </ul>
        <h3 style={{ margin: "0 0 6px", fontSize: 16 }}>Give feedback</h3>
        <p style={{ margin: 0, fontSize: 14 }}>
          Spot a wrong ward, number or policy detail? Email the team at [TEAM EMAIL].
        </p>
      </div>
    </div>
  );
}
