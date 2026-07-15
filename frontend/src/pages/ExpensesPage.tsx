import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { LayoutGrid, CalendarDays, CalendarRange, Sparkles, ArrowLeft } from "lucide-react";
import BudgetGridPage from "./BudgetGridPage";
import BudgetSetupPage from "./BudgetSetupPage";
import MonthlyTrendView from "../components/expenses/MonthlyTrendView";
import YearlyTrendView from "../components/expenses/YearlyTrendView";
import ExpensesInsightsCard from "../components/expenses/ExpensesInsightsCard";

type View = "tiles" | "monthly" | "yearly";

const VIEW_KEY = "expenses.view";
const YEAR_KEY = "expenses.year";
const MONTH_KEY = "expenses.month";

const TABS: { id: View; label: string; icon: typeof LayoutGrid }[] = [
  { id: "tiles", label: "Tiles", icon: LayoutGrid },
  { id: "monthly", label: "Monthly trend", icon: CalendarDays },
  { id: "yearly", label: "Yearly trend", icon: CalendarRange },
];

function readStored(key: string, fallback: number): number {
  const raw = sessionStorage.getItem(key);
  const n = raw === null ? NaN : parseInt(raw, 10);
  return Number.isFinite(n) ? n : fallback;
}

export default function ExpensesPage() {
  const [params, setParams] = useSearchParams();
  const setupRequested = params.get("action") === "setup";
  const [setupOpen, setSetupOpen] = useState(setupRequested);
  const now = new Date();
  const [view, setView] = useState<View>(
    () => (sessionStorage.getItem(VIEW_KEY) as View) || "tiles",
  );
  const [year, setYear] = useState(() => readStored(YEAR_KEY, now.getFullYear()));
  const [monthIdx, setMonthIdx] = useState(() => readStored(MONTH_KEY, now.getMonth()));

  useEffect(() => {
    sessionStorage.setItem(VIEW_KEY, view);
  }, [view]);
  useEffect(() => {
    sessionStorage.setItem(YEAR_KEY, String(year));
  }, [year]);
  useEffect(() => {
    sessionStorage.setItem(MONTH_KEY, String(monthIdx));
  }, [monthIdx]);

  useEffect(() => {
    if (setupRequested) setSetupOpen(true);
  }, [setupRequested]);

  const closeSetup = () => {
    setSetupOpen(false);
    if (params.has("action")) {
      params.delete("action");
      setParams(params, { replace: true });
    }
  };

  if (setupOpen) {
    return (
      <div className="space-y-4">
        <button
          onClick={closeSetup}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-emerald-400"
        >
          <ArrowLeft size={16} /> Back to Expenses
        </button>
        <BudgetSetupPage />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-bold">Expenses</h2>
        <button
          onClick={() => setSetupOpen(true)}
          className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-2 rounded-lg text-sm"
        >
          <Sparkles size={16} /> Budget Setup
        </button>
      </div>

      <div className="flex gap-1 bg-gray-800 border border-gray-700 rounded-lg p-1 w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setView(id)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
              view === id ? "bg-emerald-500/20 text-emerald-400" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {view === "tiles" && (
        <BudgetGridPage kind="expense" budgetLabel="Budget" actualLabel="Actual" />
      )}
      {view === "monthly" && (
        <MonthlyTrendView year={year} monthIdx={monthIdx} setYear={setYear} setMonthIdx={setMonthIdx} />
      )}
      {view === "yearly" && <YearlyTrendView year={year} setYear={setYear} />}

      <ExpensesInsightsCard year={year} monthIdx={monthIdx} />
    </div>
  );
}
