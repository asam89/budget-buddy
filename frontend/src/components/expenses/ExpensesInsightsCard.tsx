import { useEffect, useState } from "react";
import { Sparkles, RefreshCw, Loader2, CircleAlert } from "lucide-react";
import {
  InsightsFindings, InsightsResult, getInsightsFindings, generateInsights,
} from "../../api/client";
import ModelBadge from "../ModelBadge";
import { fmt, ym } from "./trendUtils";

interface Props {
  year: number;
  monthIdx: number;
}

export default function ExpensesInsightsCard({ year, monthIdx }: Props) {
  const period = ym(year, monthIdx);
  const [findings, setFindings] = useState<InsightsFindings | null>(null);
  const [result, setResult] = useState<InsightsResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Findings load fast and independently — the narrative never blocks them.
  useEffect(() => {
    let active = true;
    setFindings(null);
    setResult(null);
    setError(null);
    getInsightsFindings(period)
      .then((r) => {
        if (!active) return;
        setFindings(r.findings);
        runGenerate(false);
      })
      .catch((e) => active && setError(e instanceof Error ? e.message : "Failed to load"));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  const runGenerate = (force: boolean) => {
    setGenerating(true);
    generateInsights(period, force)
      .then((r) => {
        setResult(r);
        setFindings(r.findings);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to generate"))
      .finally(() => setGenerating(false));
  };

  const t = findings?.totals;

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-5 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-emerald-400" />
          <h3 className="font-semibold">AI Insights</h3>
          {findings && <span className="text-xs text-gray-500">· {findings.period_label}</span>}
        </div>
        <div className="flex items-center gap-2">
          {result?.generated && result.model && <ModelBadge override={result.model} />}
          <button
            onClick={() => runGenerate(true)}
            disabled={generating || !findings}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-emerald-400 disabled:opacity-40"
          >
            <RefreshCw size={13} className={generating ? "animate-spin" : ""} /> Regenerate
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {/* Narrative (optional, validated). Findings below always render. */}
      {generating && !result && (
        <p className="flex items-center gap-2 text-sm text-gray-400">
          <Loader2 size={14} className="animate-spin" /> Generating insights…
        </p>
      )}
      {result?.generated && result.narrative && (
        <div className="space-y-2">
          {result.narrative.summary && <p className="text-sm text-gray-200">{result.narrative.summary}</p>}
          {result.narrative.bullets.length > 0 && (
            <ul className="list-disc list-inside text-sm text-gray-300 space-y-1">
              {result.narrative.bullets.map((b, i) => <li key={i}>{b}</li>)}
            </ul>
          )}
          {result.generated_at && (
            <p className="text-[11px] text-gray-500">
              Generated {new Date(result.generated_at).toLocaleString()}{result.cached ? " · cached" : ""}
            </p>
          )}
        </div>
      )}
      {result && !result.generated && (
        <p className="flex items-start gap-2 text-xs text-amber-400">
          <CircleAlert size={14} className="mt-0.5 shrink-0" />
          {result.error || "AI narrative unavailable — showing computed findings."}
        </p>
      )}

      {/* Deterministic findings — the source of truth, always visible. */}
      {t && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
          <Stat label="Spent" value={fmt(t.expense_actual)} />
          <Stat label="Budget" value={fmt(t.expense_budget)} />
          <Stat label="Saved" value={fmt(t.saved_actual)} accent={t.saved_actual >= 0} />
          <Stat label="Savings rate" value={`${t.savings_rate_pct}%`} />
        </div>
      )}

      {findings && findings.over_budget.length > 0 && (
        <div className="text-sm">
          <p className="text-xs text-gray-500 mb-1">Over budget</p>
          <ul className="space-y-0.5">
            {findings.over_budget.map((o) => (
              <li key={o.name} className="flex justify-between">
                <span>{o.name}</span>
                <span className="text-red-400">+{fmt(o.overage)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {findings && findings.biggest_changes.length > 0 && (
        <div className="text-sm">
          <p className="text-xs text-gray-500 mb-1">Biggest changes vs {findings.previous_period_label}</p>
          <ul className="space-y-0.5">
            {findings.biggest_changes.map((c) => (
              <li key={c.name} className="flex justify-between">
                <span>{c.name}</span>
                <span className={c.delta >= 0 ? "text-red-400" : "text-emerald-400"}>
                  {c.delta >= 0 ? "+" : ""}{fmt(c.delta)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="bg-gray-900/50 rounded-lg p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`font-semibold ${accent === false ? "text-red-400" : accent ? "text-emerald-400" : ""}`}>
        {value}
      </p>
    </div>
  );
}
