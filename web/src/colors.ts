// Same red-to-blue scale as the design prototype. Rank 1 is red, rank 25 is blue.
const STOPS = ["#B2182B", "#EF8A62", "#FDDBC7", "#F2F2F2", "#D1E5F0", "#67A9CF", "#2166AC"];

function hex(h: string): number[] {
  return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
}

export function colorFor(rank: number, total = 25): string {
  const t = ((rank - 1) / (total - 1)) * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(t));
  const f = t - i;
  const a = hex(STOPS[i]);
  const b = hex(STOPS[i + 1]);
  return "rgb(" + a.map((v, j) => Math.round(v + (b[j] - v) * f)).join(",") + ")";
}

export function badgeTextColor(rank: number): string {
  return rank <= 5 || rank >= 21 ? "#fff" : "#0B2545";
}
