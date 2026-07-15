import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { ActualCell, Transaction, getTransactions } from "../../api/client";
import { MONTHS, fmt, ym, lastDay } from "./trendUtils";

interface Props {
  categoryId: number;
  categoryName: string;
  year: number;
  monthIdx: number;
  cell: ActualCell;
  onClose: () => void;
}

/**
 * Drill-down into a single category/month: the transactions behind the actual,
 * plus the manual actual when one overrides the transaction sum. Read-only
 * projection of the same data the aggregation layer uses.
 */
export default function CategoryDrilldown({
  categoryId, categoryName, year, monthIdx, cell, onClose,
}: Props) {
  const [txns, setTxns] = useState<Transaction[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTransactions({
      category_id: String(categoryId),
      start_date: ym(year, monthIdx) + "-01",
      end_date: lastDay(year, monthIdx),
      limit: "500",
    })
      .then(setTxns)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [categoryId, year, monthIdx]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-800 rounded-2xl border border-gray-700 w-full max-w-xl max-h-[85vh] overflow-y-auto">
        <div className="flex items-start justify-between p-5 border-b border-gray-700">
          <div>
            <h3 className="text-lg font-bold">{categoryName}</h3>
            <p className="text-sm text-gray-400">{MONTHS[monthIdx]} {year}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Effective actual</p>
              <p className="font-semibold">{cell.effective !== null ? fmt(cell.effective) : "—"}</p>
              <p className="text-[11px] text-gray-500 mt-0.5">source: {cell.source}</p>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Transaction sum</p>
              <p className="font-semibold">{fmt(cell.transaction_sum)}</p>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Manual</p>
              <p className="font-semibold">{cell.manual_amount !== null ? fmt(cell.manual_amount) : "—"}</p>
            </div>
          </div>

          {cell.source === "manual" && (
            <p className="text-xs text-amber-400">
              A manual actual overrides the transaction sum for this month — the two are never added.
            </p>
          )}

          {error && <p className="text-sm text-red-400">{error}</p>}
          {txns === null && !error && <p className="text-sm text-gray-500">Loading transactions…</p>}
          {txns && txns.length === 0 && (
            <p className="text-sm text-gray-500">No transactions in this category for {MONTHS[monthIdx]}.</p>
          )}
          {txns && txns.length > 0 && (
            <table className="w-full text-sm">
              <thead className="text-left text-gray-500 border-b border-gray-700">
                <tr><th className="py-1">Date</th><th className="py-1">Name</th><th className="py-1 text-right">Amount</th></tr>
              </thead>
              <tbody>
                {txns.map((t) => (
                  <tr key={t.id} className="border-b border-gray-700/40">
                    <td className="py-1 text-gray-400">{t.date}</td>
                    <td className="py-1">{t.merchant_name || t.name}</td>
                    <td className={`py-1 text-right ${t.amount < 0 ? "text-emerald-400" : ""}`}>{fmt(t.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
