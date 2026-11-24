// Same red-to-blue scale as the design prototype. Red is one end, blue the other.
const STOPS = ["#B2182B", "#EF8A62", "#FDDBC7", "#F2F2F2", "#D1E5F0", "#67A9CF", "#2166AC"];

function hex(h: string): number[] {
  return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
}

// t runs from 0 (red) to 1 (blue).
function colorAt(t: number): string {
  const pos = Math.min(1, Math.max(0, t)) * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(pos));
  const f = pos - i;
  const a = hex(STOPS[i]);
  const b = hex(STOPS[i + 1]);
  return "rgb(" + a.map((v, j) => Math.round(v + (b[j] - v) * f)).join(",") + ")";
}

// White text on the dark ends of the scale, dark text in the pale middle.
const textAt = (t: number) => (t <= 0.17 || t >= 0.83 ? "#fff" : "#0B2545");

// Colour by rank: rank 1 is red, the last rank is blue. Kept for colouring by priority.
export function colorFor(rank: number, total = 25): string {
  return colorAt((rank - 1) / (total - 1));
}

export function badgeTextColor(rank: number, total = 25): string {
  return textAt((rank - 1) / (total - 1));
}

// Colour by amount: the largest value is red, the smallest is blue, linear in between.
function fraction(value: number, min: number, max: number): number {
  return max === min ? 0.5 : 1 - (value - min) / (max - min);
}

export function colorForValue(value: number, min: number, max: number): string {
  return colorAt(fraction(value, min, max));
}

export function textColorForValue(value: number, min: number, max: number): string {
  return textAt(fraction(value, min, max));
}
