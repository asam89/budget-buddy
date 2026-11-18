/**
 * Tailwind text color for a variance (actual minus expected/budget).
 *
 * Income: earning more than expected is good, so positive is bright green
 * and negative (short of expected) is red.
 * Expenses: spending more than budget is bad, so positive is red.
 * Zero (on target) is the normal green either way.
 */
export function varianceColor(kind: "income" | "expense", variance: number): string {
  if (Math.abs(variance) < 0.005) return "text-emerald-400";
  const good = kind === "income" ? variance > 0 : variance < 0;
  if (kind === "income") return good ? "text-green-400 font-semibold" : "text-red-400";
  return good ? "text-emerald-400" : "text-red-400";
}
