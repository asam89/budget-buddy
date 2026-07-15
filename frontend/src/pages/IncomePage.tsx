import { useEffect, useState } from "react";
import { LayoutGrid, CalendarDays, CalendarRange } from "lucide-react";
import BudgetGridPage from "./BudgetGridPage";
import MonthlyTrendView from "../components/expenses/MonthlyTrendView";
import YearlyTrendView from "../components/expenses/YearlyTrendView";

type View = "tiles" | "monthly" | "yearly";

const VIEW_KEY = "income.view";
const YEAR_KEY = "income.year";
const MONTH_KEY = "income.month";

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

export default function IncomePage() {
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

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Income</h2>

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
        <BudgetGridPage kind="income" budgetLabel="Expected" actualLabel="Actual" />
      )}
      {view === "monthly" && (
        <MonthlyTrendView
          year={year}
          monthIdx={monthIdx}
          setYear={setYear}
          setMonthIdx={setMonthIdx}
          kind="income"
        />
      )}
      {view === "yearly" && <YearlyTrendView year={year} setYear={setYear} kind="income" />}
    </div>
  );
}
