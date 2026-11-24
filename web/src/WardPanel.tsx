import { useMemo, useState } from "react";
import type { FloodRequests, Ward } from "./api";
import { colorForValue, textColorForValue } from "./colors";
import type { RequestStats } from "./requests";

// The same six colours as the notebook charts, in the order of the request types.
const TYPE_COLORS = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2"];
const SEASON_SHORT = ["W", "Sp", "Su", "F"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const n = (value: number) => value.toLocaleString("en-CA");

// Round numbers for the vertical axis, so the top tick is just above the tallest bar.
function niceTicks(max: number, target = 4): number[] {
  if (max <= 0) return [0, 1];
  const rough = max / target;
  const power = Math.pow(10, Math.floor(Math.log10(rough)));
  const f = rough / power;
  const step = Math.max(1, (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * power);
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(Math.round(v));
  return ticks;
}

// Top tick of the axis for a given maximum, e.g. 1,740 becomes 2,000.
const axisTop = (max: number) => niceTicks(max).slice(-1)[0];

// The tallest bar of each chart over all wards, for the shared scale.
function commonMaxima(data: FloodRequests): { season: number; year: number } {
  let season = 0;
  let year = 0;
  for (const table of Object.values(data.wards)) {
    for (let s = 0; s < data.seasons.length; s++) {
      let acrossYears = 0;
      for (const y of table) {
        const total = y[s].reduce((a, v) => a + v, 0);
        acrossYears += total;
        if (total > year) year = total;
      }
      if (acrossYears > season) season = acrossYears;
    }
  }
  return { season, year };
}

type Scale = "ward" | "all";

type Bar = { label: string; values: number[] };
type Group = { label: string; sub?: string; size: number };

type ChartProps = {
  bars: Bar[];
  types: string[];
  width: number;
  height: number;
  ariaLabel: string;
  xLabel: (index: number) => string;
  xFont: number;
  groups?: Group[];
  maxValue?: number;
};

// One bar per entry, stacked by request type. The vertical scale fits these bars,
// unless maxValue is given (the shared scale for all wards).
function StackedBars({ bars, types, width, height, ariaLabel, xLabel, xFont, groups, maxValue }: ChartProps) {
  const [hovered, setHovered] = useState<number | null>(null);
  const margin = { left: 44, right: 8, top: 8, bottom: groups ? 46 : 26 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const slot = plotW / bars.length;
  const barW = slot * (groups ? 0.74 : 0.62);

  const totals = bars.map((b) => b.values.reduce((a, v) => a + v, 0));
  const ticks = niceTicks(maxValue ?? Math.max(...totals));
  const topTick = ticks[ticks.length - 1];
  const y = (v: number) => margin.top + plotH - (v / topTick) * plotH;

  // The box sits in the corner away from the hovered bar, so it never covers it.
  const tipOnRight = hovered != null && hovered < bars.length / 2;
  const tipRows =
    hovered != null
      ? bars[hovered].values
          .map((v, t) => ({ v, t }))
          .filter((row) => row.v > 0)
          .sort((a, b) => b.v - a.v)
      : [];

  return (
    <div style={{ position: "relative" }}>
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={ariaLabel} style={{ display: "block" }}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={margin.left} x2={width - margin.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "#7F93A3" : "#E3EAEF"} strokeWidth={1} />
          <text x={margin.left - 6} y={y(t) + 3.5} textAnchor="end" fontSize={10} fill="#4B5D6F">
            {n(t)}
          </text>
        </g>
      ))}

      {groups &&
        groups.slice(1).reduce<JSX.Element[]>((lines, _, k) => {
          const index = groups.slice(0, k + 1).reduce((a, g) => a + g.size, 0);
          const x = margin.left + index * slot;
          lines.push(<line key={k} x1={x} x2={x} y1={margin.top} y2={margin.top + plotH} stroke="#C6D2DB" strokeWidth={0.8} />);
          return lines;
        }, [])}

      {bars.map((bar, i) => {
        const x0 = margin.left + i * slot;
        let acc = 0;
        return (
          <g
            key={i}
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered((h) => (h === i ? null : h))}
            onClick={() => setHovered((h) => (h === i ? null : i))}
          >
            <rect x={x0} y={margin.top} width={slot} height={plotH} fill={hovered === i ? "rgba(11,37,69,0.08)" : "transparent"} />
            {bar.values.map((v, t) => {
              const yBottom = y(acc);
              acc += v;
              const yTop = y(acc);
              return v > 0 ? (
                <rect key={t} x={x0 + (slot - barW) / 2} y={yTop} width={barW} height={yBottom - yTop} fill={TYPE_COLORS[t]} />
              ) : null;
            })}
            <text x={x0 + slot / 2} y={margin.top + plotH + 4 + xFont} textAnchor="middle" fontSize={xFont} fill="#12263A">
              {xLabel(i)}
            </text>
          </g>
        );
      })}

      {groups &&
        groups.map((g, k) => {
          const before = groups.slice(0, k).reduce((a, x) => a + x.size, 0);
          const cx = margin.left + (before + g.size / 2) * slot;
          const base = margin.top + plotH + 4 + xFont;
          return (
            <g key={g.label}>
              <text x={cx} y={base + 13} textAnchor="middle" fontSize={11} fontWeight={600} fill="#12263A">
                {g.label}
              </text>
              {g.sub && (
                <text x={cx} y={base + 24} textAnchor="middle" fontSize={9} fill="#4B5D6F">
                  {g.sub}
                </text>
              )}
            </g>
          );
        })}
    </svg>
    {hovered != null && (
      <div
        role="status"
        style={{
          position: "absolute",
          top: 6,
          ...(tipOnRight ? { right: 8 } : { left: margin.left + 8 }),
          maxWidth: "62%",
          padding: "8px 10px",
          background: "#fff",
          border: "1px solid #C6D2DB",
          borderRadius: 8,
          boxShadow: "0 2px 10px rgba(11,37,69,.18)",
          fontSize: 12,
          lineHeight: 1.35,
          pointerEvents: "none",
        }}
      >
        <div style={{ fontWeight: 700 }}>{bars[hovered].label}</div>
        <div style={{ marginBottom: 4 }}>{n(totals[hovered])} requests</div>
        {tipRows.map(({ v, t }) => (
          <div key={t} style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
            <span aria-hidden="true" style={{ flex: "none", width: 10, height: 10, marginTop: 3, borderRadius: 2, background: TYPE_COLORS[t] }} />
            <span style={{ flex: 1 }}>{types[t]}</span>
            <span style={{ fontWeight: 600 }}>{n(v)}</span>
          </div>
        ))}
      </div>
    )}
    </div>
  );
}

function Legend({ types }: { types: string[] }) {
  return (
    <ul style={{ listStyle: "none", margin: "6px 0 0", padding: 0, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px", fontSize: 12 }}>
      {types.map((type, t) => (
        <li key={type} style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
          <span aria-hidden="true" style={{ flex: "none", width: 12, height: 12, marginTop: 2, borderRadius: 2, background: TYPE_COLORS[t] }} />
          <span>{type}</span>
        </li>
      ))}
    </ul>
  );
}

function Note({ data }: { data: FloodRequests }) {
  const through = new Date(`${data.through}T00:00:00`).toLocaleDateString("en-CA", { dateStyle: "medium" });
  return (
    <p className="note" style={{ margin: "10px 0 0" }}>
      {data.filter}. Data through {through}. Source: {data.source}.
    </p>
  );
}

type Props = {
  ward: Ward | undefined;
  wardCount: number;
  data: FloodRequests | null;
  stats: RequestStats | null;
  error: string | null;
};

export default function WardPanel({ ward, wardCount, data, stats, error }: Props) {
  // Kept here, and the panel stays mounted, so the choice survives clicking another ward.
  const [scale, setScale] = useState<Scale>("ward");
  const common = useMemo(() => (data ? commonMaxima(data) : null), [data]);
  let body: JSX.Element;

  if (error) {
    body = <div className="errbox">{error}</div>;
  } else if (!data) {
    body = <div className="note">Loading flooding requests…</div>;
  } else if (!ward) {
    body = (
      <>
        <p style={{ margin: "0 0 8px", fontSize: 15 }}>
          Click a ward on the map to see its flooding requests by season and by year.
        </p>
        <div className="lab">Request types</div>
        <Legend types={data.types} />
        <Note data={data} />
      </>
    );
  } else {
    const table = data.wards[String(ward.ward_id)];
    const first = data.years[0];
    const last = data.years[data.years.length - 1];

    const bySeason: Bar[] = data.seasons.map((season, s) => ({
      label: season,
      values: data.types.map((_, t) => table.reduce((acc, year) => acc + year[s][t], 0)),
    }));
    const byYear: Bar[] = data.years.flatMap((year, i) =>
      data.seasons.map((season, s) => ({ label: `${season} ${year}`, values: table[i][s] })),
    );

    const month = Number(data.through.slice(5, 7));
    const lastIsPartial = month < 12;
    const groups: Group[] = data.years.map((year, i) => ({
      label: String(year),
      sub: lastIsPartial && i === data.years.length - 1 ? `Jan–${MONTHS[month - 1]}` : undefined,
      size: data.seasons.length,
    }));

    const seasonSummary = bySeason.map((b) => `${b.label} ${b.values.reduce((a, v) => a + v, 0)}`).join(", ");
    const yearSummary = data.years
      .map((year, i) => `${year} ${table[i].reduce((a, season) => a + season.reduce((x, v) => x + v, 0), 0)}`)
      .join(", ");
    const name = `Ward ${ward.ward_id} ${ward.ward_name}`;

    const shared = scale === "all" && common ? common : null;
    const hint = shared
      ? `Same axis for all ${Object.keys(data.wards).length} wards, so wards can be compared (up to ${n(axisTop(shared.season))} and ${n(axisTop(shared.year))}).`
      : "Each chart fits this ward's own numbers.";

    body = (
      <>
        <div className="seg-row">
          <span className="lab" id="scale-label">Scale</span>
          <div className="seg" role="group" aria-labelledby="scale-label">
            <button type="button" aria-pressed={scale === "ward"} onClick={() => setScale("ward")}>This ward</button>
            <button type="button" aria-pressed={scale === "all"} onClick={() => setScale("all")}>All wards</button>
          </div>
        </div>
        <p className="note" style={{ margin: "0 0 10px" }}>{hint}</p>
        <h3 className="h" style={{ fontSize: 15, margin: "0 0 2px" }}>By season, {first}–{last} combined</h3>
        <StackedBars
          bars={bySeason}
          types={data.types}
          width={480}
          height={210}
          xFont={11}
          xLabel={(i) => bySeason[i].label}
          maxValue={shared?.season}
          ariaLabel={`Finished flooding requests in ${name} by season, ${first} to ${last} combined: ${seasonSummary}.`}
        />
        <h3 className="h" style={{ fontSize: 15, margin: "16px 0 2px" }}>By season and year</h3>
        <StackedBars
          bars={byYear}
          types={data.types}
          width={480}
          height={200}
          xFont={9}
          xLabel={(i) => SEASON_SHORT[i % data.seasons.length]}
          groups={groups}
          maxValue={shared?.year}
          ariaLabel={`Finished flooding requests in ${name} by season and year. Yearly totals: ${yearSummary}.`}
        />
        <div className="note" style={{ marginTop: 2 }}>W winter, Sp spring, Su summer, F fall</div>
        <div className="lab" style={{ marginTop: 12 }}>Request types</div>
        <Legend types={data.types} />
        <Note data={data} />
      </>
    );
  }

  const total = ward && stats ? stats.totals.get(ward.ward_id) : undefined;
  const rank = ward && stats ? stats.ranks.get(ward.ward_id) : undefined;
  const firstYear = data?.years[0];
  const lastYear = data ? data.years[data.years.length - 1] : undefined;

  return (
    <aside className="wardpanel" aria-label="Flooding requests by ward">
      <div className="wardpanel-inner">
        {ward ? (
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
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
                background: stats && total != null ? colorForValue(total, stats.min, stats.max) : "#DDE4EA",
                color: stats && total != null ? textColorForValue(total, stats.min, stats.max) : "#0B2545",
                border: "1px solid #C6D2DB",
              }}
            >
              {rank != null ? `#${rank}` : "–"}
            </span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 16, lineHeight: 1.2 }}>
                Ward {ward.ward_id} {ward.ward_name}
              </div>
              <div style={{ fontSize: 13, color: "#4B5D6F" }}>
                {total != null
                  ? `${n(total)} requests, ${firstYear}–${lastYear} · #${rank} of ${wardCount}`
                  : "Loading flooding requests…"}
              </div>
            </div>
          </div>
        ) : (
          <h2 className="h" style={{ fontSize: 17, margin: "0 0 10px" }}>Flooding requests by ward</h2>
        )}
        {body}
      </div>
    </aside>
  );
}
