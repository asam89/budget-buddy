import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import {
  Category,
  OtherAssignment,
  OtherGroup,
  OtherSummary,
  getCategories,
  getOtherSummary,
  reassignOther,
} from "../api/client";

const NEW = "__new__";

function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

interface Choice {
  categoryId: string; // category id, "" (unset), or NEW
  newName: string;
}

/**
 * One-time flow that empties and deletes the legacy "Other" category by letting
 * the user re-point each group of its data to a real category. Renders nothing
 * unless an "Other" category with attached data exists.
 */
export default function OtherReassignmentModal({ onDone }: { onDone?: () => void }) {
  const [summary, setSummary] = useState<OtherSummary | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    getOtherSummary()
      .then((s) => {
        setSummary(s);
        if (s.exists && s.groups.length > 0) getCategories().then(setCategories);
      })
      .catch(() => setSummary(null));
  }, []);

  const groups: OtherGroup[] = summary?.groups ?? [];

  const setChoice = (key: string, patch: Partial<Choice>) =>
    setChoices((prev) => {
      const current = prev[key] ?? { categoryId: "", newName: "" };
      return { ...prev, [key]: { ...current, ...patch } };
    });

  const allChosen = useMemo(
    () =>
      groups.every((g) => {
        const c = choices[g.key];
        if (!c) return false;
        return c.categoryId === NEW ? c.newName.trim().length > 0 : c.categoryId !== "";
      }),
    [groups, choices],
  );

  if (!summary?.exists || groups.length === 0 || dismissed) return null;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const assignments: OtherAssignment[] = groups.map((g) => {
        const c = choices[g.key];
        return c.categoryId === NEW
          ? { group_key: g.key, new_category_name: c.newName.trim() }
          : { group_key: g.key, to_category_id: Number(c.categoryId) };
      });
      const res = await reassignOther(assignments);
      if (res.other_deleted) {
        setDismissed(true);
        onDone?.();
      } else {
        setError(`${res.remaining_references} items still reference Other.`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reassignment failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-800 rounded-2xl border border-gray-700 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between p-5 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-amber-400 shrink-0" size={22} />
            <div>
              <h2 className="text-lg font-bold">Reassign your "Other" category</h2>
              <p className="text-sm text-gray-400 mt-1">
                Budget Buddy no longer uses a catch-all category. Map each group below to a real
                category. "Other" is deleted once everything is reassigned.
              </p>
            </div>
          </div>
          <button
            onClick={() => setDismissed(true)}
            className="text-gray-500 hover:text-gray-300"
            title="Do this later"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-3">
          {groups.map((g) => (
            <div
              key={g.key}
              className="flex items-center justify-between gap-3 bg-gray-900/50 rounded-lg p-3"
            >
              <div className="min-w-0">
                <p className="font-medium truncate">{g.label}</p>
                <p className="text-xs text-gray-500">
                  {g.kind} · {g.count} item{g.count > 1 ? "s" : ""} · {fmt(g.amount)}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <select
                  value={choices[g.key]?.categoryId ?? ""}
                  onChange={(e) => setChoice(g.key, { categoryId: e.target.value })}
                  className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm"
                >
                  <option value="">Choose category…</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                  <option value={NEW}>+ New category…</option>
                </select>
                {choices[g.key]?.categoryId === NEW && (
                  <input
                    value={choices[g.key]?.newName ?? ""}
                    onChange={(e) => setChoice(g.key, { newName: e.target.value })}
                    placeholder="New category name"
                    className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm w-40"
                  />
                )}
              </div>
            </div>
          ))}
        </div>

        {error && (
          <div className="mx-5 mb-3 bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 p-5 border-t border-gray-700">
          <button
            onClick={() => setDismissed(true)}
            className="bg-gray-700 hover:bg-gray-600 text-gray-200 px-4 py-2 rounded-lg text-sm"
          >
            Later
          </button>
          <button
            onClick={submit}
            disabled={busy || !allChosen}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm"
          >
            Reassign & remove Other
          </button>
        </div>
      </div>
    </div>
  );
}
