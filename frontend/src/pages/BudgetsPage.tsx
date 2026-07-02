import { useState, useEffect, FormEvent } from "react";
import { getBudgets, createBudget, getCategories, seedCategories, Budget, Category } from "../api/client";
import { Plus, Target } from "lucide-react";

function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

export default function BudgetsPage() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [catId, setCatId] = useState("");
  const [limit, setLimit] = useState("");

  useEffect(() => {
    getBudgets().then(setBudgets);
    getCategories().then((cats) => {
      if (cats.length === 0) {
        seedCategories().then(setCategories);
      } else {
        setCategories(cats);
      }
    });
  }, []);

  const catName = (id: number) => categories.find((c) => c.id === id)?.name || `Category #${id}`;

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    const b = await createBudget({
      category_id: parseInt(catId),
      monthly_limit: parseFloat(limit),
    });
    setBudgets([...budgets, b]);
    setShowForm(false);
    setCatId("");
    setLimit("");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Budgets</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm"
        >
          <Plus size={16} /> Set Budget
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-gray-800 rounded-xl p-4 border border-gray-700 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <select
              value={catId}
              onChange={(e) => setCatId(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
              required
            >
              <option value="">Select category...</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <input
              type="number"
              step="0.01"
              placeholder="Monthly limit ($)"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
              required
            />
          </div>
          <button type="submit" className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm">
            Create
          </button>
        </form>
      )}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {budgets.map((b) => (
          <div key={b.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <div className="flex items-center gap-3 mb-2">
              <Target className="text-emerald-400" size={20} />
              <p className="font-medium">{catName(b.category_id)}</p>
            </div>
            <p className="text-xl font-bold text-emerald-400">{fmt(b.monthly_limit)}</p>
            <p className="text-xs text-gray-400 mt-1">
              {b.year_month ? `For ${b.year_month}` : "Every month"}
            </p>
          </div>
        ))}
        {budgets.length === 0 && (
          <p className="text-gray-500 col-span-full text-center py-8">
            No budgets set yet. Create one to track spending by category.
          </p>
        )}
      </div>
    </div>
  );
}
