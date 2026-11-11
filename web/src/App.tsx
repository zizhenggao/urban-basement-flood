import { useEffect, useState } from "react";
import { getWards, type Ward } from "./api";
import MapPane from "./MapPane";
import Chat from "./Chat";
import About from "./About";

export default function App() {
  const [wards, setWards] = useState<Ward[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);
  const [about, setAbout] = useState(false);
  const [injected, setInjected] = useState<{ q: string; n: number } | null>(null);

  useEffect(() => {
    getWards()
      .then(setWards)
      .catch((err: Error) =>
        setError(err instanceof TypeError ? "Could not reach the API. Start it with: python -m uvicorn api.main:app" : err.message),
      );
  }, []);

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
        <span className="pill" style={{ background: "#FFD978", color: "#0B2545" }}>PRELIMINARY</span>
        <button className="btn" style={{ minHeight: 40, background: "transparent", color: "#fff", borderColor: "#6F8FAF" }} onClick={() => setAbout(true)}>
          About and limits
        </button>
      </header>

      <main className="body">
        {wards ? (
          <MapPane
            wards={wards}
            pinned={pinned}
            onPin={setPinned}
            onAskAbout={(w) =>
              setInjected((prev) => ({ q: `What should we tell residents in Ward ${w.ward_id} ${w.ward_name}?`, n: (prev?.n ?? 0) + 1 }))
            }
          />
        ) : (
          <section className="mapcol" aria-label="Flood risk priority map">
            {error ? <div className="errbox">{error}</div> : <div className="note">Loading wards…</div>}
          </section>
        )}
        <Chat injected={injected} />
      </main>

      {about && <About onClose={() => setAbout(false)} />}
    </div>
  );
}
