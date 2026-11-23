// Writes web/public/wards.json from outputs/ward_index.csv.
// Same fields as flood_rag.service.ward_table, so the published map matches the API.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const csvPath = join(root, "outputs", "ward_index.csv");

const FACTORS = {
  pct_old_pipe: ["Older pipe", (v) => `${pyRound(v * 100)}% of sewer pipe is past the old-pipe age`],
  pct_combined_sewer: ["Combined sewers", (v) => `${pyRound(v * 100)}% of pipe carries sewage and stormwater together`],
  avg_pipe_age: ["Pipe age", (v) => `average pipe age is ${pyRound(v)} years`],
  pipe_share_in_root_zone: ["Tree roots over pipe", (v) => `${pyRound(v * 100)}% of pipe lies in a tree-root zone`],
  avg_residential_usage: ["Water use", (v) => `average residential water use is ${pyRound(v)}`],
  backup_per_1000: ["Sewer backups", (v) => `${fixed(v, 1)} sewer-backup calls per 1,000 eligible homes`],
  manhole_per_1000: ["Manhole overflows", (v) => `${fixed(v, 1)} manhole-overflow calls per 1,000 eligible homes`],
  flood_per_1000: ["Few flood reports", (v) => `${fixed(v, 1)} basement-flood requests per year per 1,000 eligible homes`],
  subsidy_participation: ["Few homes with a device", (v) => `only ${fixed(v * 100, 1)}% of eligible homes have a subsidized device`],
};
const LOW_IS_A_FACTOR = new Set(["flood_per_1000", "subsidy_participation"]);
const FACTOR_MIN_Z = 0.5;

function pyRound(x) {
  const down = Math.floor(x);
  const frac = x - down;
  if (Math.abs(frac - 0.5) < 1e-9) return down % 2 === 0 ? down : down + 1;
  return Math.round(x);
}

function fixed(x, digits) {
  const scale = 10 ** digits;
  return (pyRound(x * scale) / scale).toFixed(digits);
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else quoted = false;
      } else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      field = "";
      if (row.some((cell) => cell !== "")) rows.push(row);
      row = [];
    } else field += c;
  }
  if (field.length || row.length) {
    row.push(field);
    if (row.some((cell) => cell !== "")) rows.push(row);
  }
  const [header, ...body] = rows;
  return body.map((cells) => Object.fromEntries(header.map((name, i) => [name, cells[i] ?? ""])));
}

function num(row, col) {
  return Number(row[col]);
}

const records = parseCsv(readFileSync(csvPath, "utf8"));
const n = records.length;
const z = {};
for (const col of Object.keys(FACTORS)) {
  const values = records.map((row) => num(row, col));
  const mean = values.reduce((sum, value) => sum + value, 0) / n;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / n;
  const std = Math.sqrt(variance);
  z[col] = values.map((value) => {
    const score = std ? (value - mean) / std : 0;
    return LOW_IS_A_FACTOR.has(col) ? -score : score;
  });
}

const wards = records
  .map((row, idx) => {
    const rank = Number(row.low_intake_rank);
    const score = n <= 1 ? 100 : pyRound((100 * (n - rank)) / (n - 1));
    const top = Object.keys(FACTORS)
      .filter((col) => z[col][idx] >= FACTOR_MIN_Z)
      .sort((a, b) => z[b][idx] - z[a][idx])
      .slice(0, 3);
    return {
      ward_id: Number(row.ward_id),
      ward_name: row.ward_name,
      priority_rank: rank,
      score,
      level: score >= 70 ? "High" : score >= 40 ? "Medium" : "Low",
      top_factors: top.map((col) => ({ label: FACTORS[col][0], detail: FACTORS[col][1](num(row, col)) })),
      failure_rank: Number(row.failure_rank),
      low_report_rank: Number(row.low_report_rank),
      subsidy_participation: num(row, "subsidy_participation"),
      eligible_homes: Number(row.eligible_homes),
      properties_without_fpd: Number(row.properties_without_fpd),
      flood_reports_2019_2022: Number(row.flood_reports_2019_2022),
    };
  })
  .sort((a, b) => a.priority_rank - b.priority_rank || a.ward_id - b.ward_id);

const out = join(root, "web", "public", "wards.json");
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(wards));
console.log(`Wrote ${wards.length} wards to ${out}`);
