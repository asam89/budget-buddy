import { useEffect, useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid,
} from "recharts";
import { ActualLine, getActualsYear } from "../../api/client";
import { MONTHS_SHORT, fmt } from "./trendUtils";

const COLORS = [
  "#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
];

interface Props {
  year: number;
  lines: ActualLine[]; // expense lines of the current year
}

function monthlyTotals(lines: ActualLine[]): number[] {
  return MONTHS_SHORT.map((_, m) => lines.reduce((s, l) => s + (l.cells[m].effective ?? 0), 0));
}

export default function TrendOverlay({ year, lines }: Props) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [showAvg, setShowAvg] = useState(false);
  const [showMoM, setShowMoM] = useState(false);
  const [showYoY, setShowYoY] = useState(false);
  const [prevTotals, setPrevTotals] = useState<number[] | null>(null);

  const rankedLines = useMemo(
    () =>
      [...lines]
        .filter((l) => l.cells.some((c) => (c.effective ?? 0) !== 0))
        .sort(
          (a, b) =>
            b.cells.reduce((s, c) => s + (c.effective ?? 0), 0) -
            a.cells.reduce((s, c) => s + (c.effective ?? 0), 0),
        ),
    [lines],
  );

  useEffect(() => {
    if (!showYoY) return;
    let active = true;
    getActualsYear(year - 1)
      .then((g) => {
        if (active) setPrevTotals(monthlyTotals(g.lines.filter((l) => l.kind === "expense")));
      })
      .catch(() => active && setPrevTotals(null));
    return () => {
      active = false;
    };
  }, [showYoY, year]);

  const totals = useMemo(() => monthlyTotals(lines), [lines]);

  const data = useMemo(() => {
    return MONTHS_SHORT.map((label, m) => {
      const row: Record<string, number | string> = { month: label, Total: Math.round(totals[m]) };
      if (showAvg) {
        const window = totals.slice(Math.max(0, m - 2), m + 1);
        row["3-mo avg"] = Math.round(window.reduce((s, n) => s + n, 0) / window.length);
      }
      if (showMoM) {
        row["MoM change"] = Math.round(totals[m] - (m > 0 ? totals[m - 1] : 0));
      }
      if (showYoY && prevTotals) {
        row[`${year - 1} Total`] = Math.round(prevTotals[m]);
      }
      for (const l of rankedLines) {
        if (selected.has(l.category_id)) {
          row[l.category_name] = Math.round(l.cells[m].effective ?? 0);
        }
      }
      return row;
    });
  }, [totals, showAvg, showMoM, showYoY, prevTotals, rankedLines, selected, year]);

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const selectedList = rankedLines.filter((l) => selected.has(l.category_id));

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="font-semibold">Overlay</h3>
        <div className="flex gap-2 text-xs">
          {[
            ["3-mo avg", showAvg, setShowAvg],
            ["MoM change", showMoM, setShowMoM],
            [`vs ${year - 1}`, showYoY, setShowYoY],
          ].map(([label, on, set]) => (
            <button
              key={label as string}
              onClick={() => (set as (v: boolean) => void)(!(on as boolean))}
              className={`px-2.5 py-1 rounded-md border ${
                on
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                  : "text-gray-400 border-gray-600 hover:text-gray-200"
              }`}
            >
              {label as string}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {rankedLines.map((l) => (
          <button
            key={l.category_id}
            onClick={() => toggle(l.category_id)}
            className={`px-2 py-0.5 rounded-full text-xs border ${
              selected.has(l.category_id)
                ? "bg-blue-500/20 text-blue-300 border-blue-500/40"
                : "text-gray-400 border-gray-600 hover:text-gray-200"
            }`}
          >
            {l.category_name}
          </button>
        ))}
      </div>

      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="month" stroke="#9ca3af" fontSize={12} />
            <YAxis stroke="#9ca3af" fontSize={12} width={70}
              tickFormatter={(v) => fmt(Number(v)).replace(/\.00$/, "")} />
            <Tooltip
              contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: 8 }}
              formatter={(v: number) => fmt(v)}
            />
            <Legend />
            <Line type="monotone" dataKey="Total" stroke="#9ca3af" strokeWidth={2} dot={false} />
            {showAvg && <Line type="monotone" dataKey="3-mo avg" stroke="#f59e0b" strokeWidth={2} dot={false} strokeDasharray="4 2" />}
            {showMoM && <Line type="monotone" dataKey="MoM change" stroke="#ec4899" strokeWidth={2} dot={false} />}
            {showYoY && prevTotals && <Line type="monotone" dataKey={`${year - 1} Total`} stroke="#6b7280" strokeWidth={2} dot={false} strokeDasharray="6 3" />}
            {selectedList.map((l, i) => (
              <Line key={l.category_id} type="monotone" dataKey={l.category_name}
                stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
