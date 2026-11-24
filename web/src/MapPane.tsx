import { useState } from "react";
import geo from "./geo.json";
import type { Ward } from "./api";
import { colorForValue } from "./colors";
import type { RequestStats } from "./requests";

type Props = {
  wards: Ward[];
  // null while the flooding-request data is loading or missing.
  stats: RequestStats | null;
  pinned: number | null;
  onPin: (id: number | null) => void;
};

const NO_DATA_FILL = "#DDE4EA";
const n = (value: number) => value.toLocaleString("en-CA");

export default function MapPane({ wards, stats, pinned, onPin }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const byId = new Map(wards.map((w) => [w.ward_id, w]));
  const pinnedShape = geo.wards.find((g) => g.id === pinned);
  const hoverShape = geo.wards.find((g) => g.id === hover);

  return (
    <section className="mapcol" aria-label="Flooding service requests map">
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "8px 20px" }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <h1 className="h" style={{ fontSize: 22 }}>Flooding service requests by ward</h1>
          <div style={{ fontSize: 14, color: "#4B5D6F" }}>
            Finished 311 flooding requests in Toronto's 25 wards, 2019 to October 2026. Colour shows the total; the label is
            the ward number. Click or tap a ward to see its requests by season and year.
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
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13, fontWeight: 600, marginTop: 3 }}>
            <span>
              Highest service requests
              {stats && <span style={{ display: "block", fontWeight: 400 }}>{n(stats.max)}</span>}
            </span>
            <span style={{ textAlign: "right" }}>
              Lowest service requests
              {stats && <span style={{ display: "block", fontWeight: 400 }}>{n(stats.min)}</span>}
            </span>
          </div>
          <div className="note" style={{ marginTop: 4 }}>
            {stats ? "More requests does not mean more risk: some wards report less." : "Loading flooding requests…"}
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
            aria-label="Toronto wards coloured from red for the most flooding service requests to blue for the fewest. Each ward is labelled with its ward number."
            style={{ display: "block", overflow: "visible" }}
          >
            <path d={geo.lake} fill="#DCEEF3" aria-hidden="true" />
            {geo.wards.map((g) => {
              const w = byId.get(g.id);
              if (!w) return null;
              const total = stats?.totals.get(g.id);
              const rank = stats?.ranks.get(g.id);
              return (
                <path
                  key={g.id}
                  className="m"
                  d={g.d}
                  fill={stats && total != null ? colorForValue(total, stats.min, stats.max) : NO_DATA_FILL}
                  onClick={() => onPin(pinned === g.id ? null : g.id)}
                  onMouseEnter={() => setHover(g.id)}
                  onMouseLeave={() => setHover(null)}
                >
                  <title>
                    {total != null
                      ? `Ward ${w.ward_id} ${w.ward_name}, ${n(total)} flooding requests, #${rank} of ${wards.length}`
                      : `Ward ${w.ward_id} ${w.ward_name}`}
                  </title>
                </path>
              );
            })}
            {hoverShape && hoverShape !== pinnedShape && <path className="mhov mhov-hover" d={hoverShape.d} />}
            {pinnedShape && <path className="mhov" d={pinnedShape.d} />}
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
      </div>
    </section>
  );
}
