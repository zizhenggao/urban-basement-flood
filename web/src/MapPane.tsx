import { useState } from "react";
import geo from "./geo.json";
import type { Ward } from "./api";
import { badgeTextColor, colorFor } from "./colors";

type Props = {
  wards: Ward[];
  pinned: number | null;
  onPin: (id: number | null) => void;
  onAskAbout: (ward: Ward) => void;
};

export default function MapPane({ wards, pinned, onPin, onAskAbout }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const byId = new Map(wards.map((w) => [w.ward_id, w]));
  const currentId = hover ?? pinned;
  const current = currentId != null ? byId.get(currentId) : undefined;
  const currentShape = geo.wards.find((g) => g.id === currentId);

  return (
    <section className="mapcol" aria-label="Flood risk priority map">
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "8px 20px" }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <h1 className="h" style={{ fontSize: 22 }}>Flood risk priority by ward</h1>
          <div style={{ fontSize: 14, color: "#4B5D6F" }}>
            Toronto's 25 wards. Colour shows priority; the label is the ward number. Hover or tap a ward for details.
          </div>
        </div>
        <div style={{ width: 280, maxWidth: "100%" }}>
          <div
            style={{
              height: 14,
              borderRadius: 4,
              background: "linear-gradient(90deg, #B2182B, #EF8A62, #FDDBC7, #F2F2F2, #D1E5F0, #67A9CF, #2166AC)",
            }}
            aria-hidden="true"
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 600, marginTop: 3 }}>
            <span>#1 highest risk</span>
            <span>#25 lowest</span>
          </div>
        </div>
      </div>

      <div className="pane">
        <div className="stage">
          <svg
            viewBox="0 0 1000 776"
            width="100%"
            height="100%"
            role="img"
            aria-label="Toronto wards coloured from red for priority 1 to blue for priority 25. Each ward is labelled with its ward number."
            style={{ display: "block", overflow: "visible" }}
          >
            <path d={geo.lake} fill="#DCEEF3" aria-hidden="true" />
            {geo.wards.map((g) => {
              const w = byId.get(g.id);
              if (!w) return null;
              return (
                <path
                  key={g.id}
                  className="m"
                  d={g.d}
                  fill={colorFor(w.priority_rank, wards.length)}
                  onClick={() => onPin(pinned === g.id ? null : g.id)}
                  onMouseEnter={() => setHover(g.id)}
                  onMouseLeave={() => setHover(null)}
                >
                  <title>{`Ward ${w.ward_id} ${w.ward_name}, priority ${w.priority_rank} of ${wards.length}`}</title>
                </path>
              );
            })}
            {currentShape && <path className="mhov" d={currentShape.d} />}
          </svg>
          {geo.wards.map((g) => {
            const w = byId.get(g.id);
            if (!w) return null;
            return (
              <span key={g.id} className="lblh" style={{ left: `${g.x / 10}%`, top: `${g.y / 7.76}%` }}>
                W{w.ward_id}
              </span>
            );
          })}
        </div>

        <div
          className="card info"
          style={{
            position: "absolute",
            right: 0,
            bottom: 0,
            width: "min(330px, 100%)",
            padding: "14px 16px",
            boxShadow: "0 2px 10px rgba(11,37,69,.15)",
          }}
        >
          {!current ? (
            <>
              <div className="lab">Ward details</div>
              <div style={{ fontSize: 14, marginTop: 4 }}>
                Hover over or tap a ward to see its priority, risk and top factors.
              </div>
            </>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span
                  style={{
                    flex: "none",
                    minWidth: 46,
                    height: 46,
                    borderRadius: 10,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 700,
                    fontSize: 17,
                    background: colorFor(current.priority_rank, wards.length),
                    color: badgeTextColor(current.priority_rank),
                    border: "1px solid #C6D2DB",
                  }}
                >
                  #{current.priority_rank}
                </span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 16, lineHeight: 1.2 }}>
                    Ward {current.ward_id} {current.ward_name}
                  </div>
                  <div style={{ fontSize: 13, color: "#4B5D6F" }}>
                    Priority {current.priority_rank} of {wards.length} · {current.level} risk · score {current.score}
                  </div>
                </div>
              </div>
              <div className="lab" style={{ margin: "10px 0 4px" }}>Top factors</div>
              {current.top_factors.length > 0 ? (
                <ol style={{ margin: 0, paddingLeft: 20, fontSize: 14, display: "flex", flexDirection: "column", gap: 3 }}>
                  {current.top_factors.map((f) => (
                    <li key={f.label}>
                      <strong>{f.label}</strong>: {f.detail}
                    </li>
                  ))}
                </ol>
              ) : (
                <div style={{ fontSize: 14 }}>No single factor is clearly above the city average.</div>
              )}
              <div style={{ fontSize: 13, color: "#4B5D6F", marginTop: 8 }}>
                Relative risk, not a guarantee. Never used to decide eligibility.
              </div>
              {pinned === current.ward_id && (
                <button className="btn" style={{ width: "100%", marginTop: 10 }} onClick={() => onAskAbout(current)}>
                  Ask the agent about this ward
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
