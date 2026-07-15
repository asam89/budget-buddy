import { useState, useEffect } from "react";
import {
  getPendingReview,
  getNeedsCategory,
  reviewTransaction,
  getCategories,
  inlineEditTransaction,
  Transaction,
  Category,
} from "../api/client";
import { CheckCircle, XCircle, AlertCircle, Tag } from "lucide-react";

function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

export default function ReviewPage() {
  const [pending, setPending] = useState<Transaction[]>([]);
  const [needsCategory, setNeedsCategory] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);

  useEffect(() => {
    getPendingReview().then(setPending);
    getNeedsCategory().then(setNeedsCategory);
    getCategories().then(setCategories);
  }, []);

  const handleReview = async (id: number, status: string) => {
    await reviewTransaction(id, { review_status: status });
    setPending(pending.filter((t) => t.id !== id));
  };

  const assignCategory = async (id: number, categoryId: number) => {
    await inlineEditTransaction(id, { category_id: categoryId });
    setNeedsCategory(needsCategory.filter((t) => t.id !== id));
  };

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold">Review Transactions</h2>
          {pending.length > 0 && (
            <span className="bg-yellow-500/20 text-yellow-400 text-xs px-2 py-0.5 rounded-full">
              {pending.length} pending
            </span>
          )}
        </div>

        <p className="text-sm text-gray-400">
          AI-parsed transactions require manual review before they affect your analytics.
          Confirm correct entries or reject incorrect ones.
        </p>

        {pending.length === 0 ? (
          <div className="bg-gray-800 rounded-xl p-8 border border-gray-700 text-center">
            <CheckCircle className="mx-auto text-emerald-400 mb-3" size={40} />
            <p className="text-gray-400">All caught up! No transactions pending review.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {pending.map((t) => (
              <div key={t.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <AlertCircle size={14} className="text-yellow-400" />
                    <span className="text-xs text-yellow-400">
                      {t.review_source} {t.confidence ? `(${Math.round(t.confidence * 100)}% confidence)` : ""}
                    </span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-gray-400 text-sm">{t.date}</span>
                    <span className="font-medium">{t.merchant_name || t.name}</span>
                    <span className={`font-medium ${t.amount < 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {fmt(t.amount)}
                    </span>
                  </div>
                  {t.notes && <p className="text-xs text-gray-500 mt-1">{t.notes}</p>}
                </div>
                <div className="flex gap-2 ml-4">
                  <button
                    onClick={() => handleReview(t.id, "confirmed")}
                    className="flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1.5 rounded-lg text-sm"
                  >
                    <CheckCircle size={14} /> Confirm
                  </button>
                  <button
                    onClick={() => handleReview(t.id, "rejected")}
                    className="flex items-center gap-1 bg-red-600 hover:bg-red-500 text-white px-3 py-1.5 rounded-lg text-sm"
                  >
                    <XCircle size={14} /> Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold">Needs a category</h2>
          {needsCategory.length > 0 && (
            <span className="bg-amber-500/20 text-amber-400 text-xs px-2 py-0.5 rounded-full">
              {needsCategory.length} uncategorized
            </span>
          )}
        </div>

        <p className="text-sm text-gray-400">
          These transactions have no category. Budget Buddy has no catch-all "Other" — assign each a
          real category so it shows up in your spending.
        </p>

        {needsCategory.length === 0 ? (
          <div className="bg-gray-800 rounded-xl p-8 border border-gray-700 text-center">
            <CheckCircle className="mx-auto text-emerald-400 mb-3" size={40} />
            <p className="text-gray-400">Nothing uncategorized. Everything has a category.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {needsCategory.map((t) => (
              <div key={t.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <Tag size={14} className="text-amber-400" />
                  <span className="text-gray-400 text-sm">{t.date}</span>
                  <span className="font-medium">{t.merchant_name || t.name}</span>
                  <span className={`font-medium ${t.amount < 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {fmt(t.amount)}
                  </span>
                </div>
                <select
                  defaultValue=""
                  onChange={(e) => e.target.value && assignCategory(t.id, Number(e.target.value))}
                  className="bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm ml-4"
                >
                  <option value="">Assign category…</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
