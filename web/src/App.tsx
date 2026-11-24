import { useEffect, useMemo, useState } from "react";
import { getFloodRequests, getWards, type FloodRequests, type Ward } from "./api";
import MapPane from "./MapPane";
import WardPanel from "./WardPanel";
import { requestStats } from "./requests";
import Chat from "./Chat";
import About from "./About";

type Tab = "map" | "agent";

export default function App() {
  const [wards, setWards] = useState<Ward[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const [about, setAbout] = useState(false);
  const [tab, setTab] = useState<Tab>("map");
  const [flood, setFlood] = useState<FloodRequests | null>(null);
  const [floodError, setFloodError] = useState<string | null>(null);

  useEffect(() => {
    getWards()
      .then(setWards)
      .catch((err: Error) =>
        setError(err instanceof TypeError ? "Could not reach the API. Start it with: python -m uvicorn api.main:app" : err.message),
      );
  }, []);

  useEffect(() => {
    getFloodRequests()
      .then(setFlood)
      .catch((err: Error) => setFloodError(err.message));
  }, []);

  const stats = useMemo(() => (flood ? requestStats(flood) : null), [flood]);
  const selected = pinned != null ? wards?.find((w) => w.ward_id === pinned) : undefined;

  return (
    <div className="app">
      <header className="top">
        <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 200 }}>
          <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M16 3C16 3 6 14 6 20a10 10 0 0 0 20 0C26 14 16 3 16 3Z" fill="#35C3CC" />
            <path d="M6 20h20" stroke="#0B2545" strokeWidth="2.5" />
          </svg>
          <span className="h" style={{ color: "#fff", fontSize: 20 }}>Stop the Flood</span>
          <span className="hidesm" style={{ color: "#C9D8E4", fontSize: 14 }}>Basement flooding outreach assistant</span>
        </div>
        <div className="tabs" role="tablist" aria-label="Sections">
          <button
            className="tab"
            role="tab"
            id="tab-map"
            aria-selected={tab === "map"}
            aria-controls="panel-map"
            onClick={() => setTab("map")}
          >
            Map
          </button>
          <button
            className="tab"
            role="tab"
            id="tab-agent"
            aria-selected={tab === "agent"}
            aria-controls="panel-agent"
            onClick={() => setTab("agent")}
          >
            Outreach agent
          </button>
        </div>
        <span className="pill" style={{ background: "#FFD978", color: "#0B2545" }}>PRELIMINARY</span>
        <button className="btn" style={{ minHeight: 40, background: "transparent", color: "#fff", borderColor: "#6F8FAF" }} onClick={() => setAbout(true)}>
          About and limits
        </button>
      </header>

      <main className="body">
        <div className="tabpanel" id="panel-map" role="tabpanel" aria-labelledby="tab-map" hidden={tab !== "map"}>
          {wards ? (
            <MapPane wards={wards} stats={stats} pinned={pinned} onPin={setPinned} />
          ) : (
            <section className="mapcol" aria-label="Flood risk priority map">
              {error ? <div className="errbox">{error}</div> : <div className="note">Loading wards…</div>}
            </section>
          )}
          <WardPanel ward={selected} wardCount={wards?.length ?? 25} data={flood} stats={stats} error={floodError} />
        </div>
        {/* The chat stays mounted while hidden, so the conversation is not lost when switching tabs. */}
        <div className="tabpanel agentview" id="panel-agent" role="tabpanel" aria-labelledby="tab-agent" hidden={tab !== "agent"}>
          <Chat />
        </div>
      </main>

      {about && <About onClose={() => setAbout(false)} />}
    </div>
  );
}
