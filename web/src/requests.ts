import type { FloodRequests } from "./api";

export type RequestStats = {
  /** Finished flooding requests per ward, all years combined. */
  totals: Map<number, number>;
  /** 1 is the ward with the most requests. */
  ranks: Map<number, number>;
  min: number;
  max: number;
};

// The map is coloured by these totals, and the charts in the ward panel add up to the same number.
export function requestStats(data: FloodRequests): RequestStats {
  const totals = new Map<number, number>();
  for (const [id, table] of Object.entries(data.wards)) {
    let total = 0;
    for (const year of table) for (const season of year) for (const count of season) total += count;
    totals.set(Number(id), total);
  }

  const ordered = [...totals.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0]);
  const ranks = new Map(ordered.map(([id], index) => [id, index + 1]));
  const values = ordered.map(([, total]) => total);
  return { totals, ranks, min: Math.min(...values), max: Math.max(...values) };
}
