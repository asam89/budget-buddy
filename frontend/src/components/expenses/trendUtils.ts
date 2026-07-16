import { ActualLine } from "../../api/client";

export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
export const MONTHS_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

export function ym(year: number, monthIdx: number) {
  return `${year}-${String(monthIdx + 1).padStart(2, "0")}`;
}

/** Last calendar day of a month, as YYYY-MM-DD. */
export function lastDay(year: number, monthIdx: number) {
  const d = new Date(year, monthIdx + 1, 0);
  return ym(year, monthIdx) + `-${String(d.getDate()).padStart(2, "0")}`;
}

export function expenseLines(lines: ActualLine[]): ActualLine[] {
  return lines.filter((l) => l.kind === "expense");
}

export function linesOfKind(lines: ActualLine[], kind: string): ActualLine[] {
  return lines.filter((l) => l.kind === kind);
}
