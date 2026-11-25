import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Wallet, ArrowLeftRight, Upload,
  Receipt, AlertCircle, BarChart3, LogOut, TrendingUp, Settings, Scale, PlusCircle,
} from "lucide-react";
import AddSpendingModal from "./spending/AddSpendingModal";
import { logout, getPendingReview, getNeedsCategory, getVersion, VersionInfo } from "../api/client";

const links = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/accounts", icon: Wallet, label: "Accounts" },
  { to: "/transactions", icon: ArrowLeftRight, label: "Transactions" },
  { to: "/import", icon: Upload, label: "Import" },
  { to: "/expenses", icon: Receipt, label: "Expenses" },
  { to: "/income", icon: TrendingUp, label: "Income" },
  { to: "/review", icon: AlertCircle, label: "Review" },
  { to: "/net-worth", icon: Scale, label: "Net Worth" },
  { to: "/reports", icon: BarChart3, label: "Reports" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function Sidebar({ username }: { username: string }) {
  const [reviewCount, setReviewCount] = useState(0);
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    Promise.all([getPendingReview(), getNeedsCategory()])
      .then(([pending, needs]) => setReviewCount(pending.length + needs.length))
      .catch(() => setReviewCount(0));
    getVersion().then(setVersion).catch(() => setVersion(null));
  }, []);

  const handleLogout = async () => {
    await logout();
    window.location.href = "/login";
  };

  return (
    <aside className="w-56 bg-gray-800 border-r border-gray-700 flex flex-col">
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="w-9 h-9 shrink-0" />
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-emerald-400 leading-tight">Budget Buddy</h1>
            <p className="text-xs text-gray-400 truncate">{username}</p>
          </div>
        </div>
      </div>
      <div className="px-2 pt-2">
        <button
          onClick={() => setAdding(true)}
          className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-3 py-2 text-sm font-medium"
        >
          <PlusCircle size={16} /> Add spending
        </button>
      </div>
      {adding && <AddSpendingModal onClose={() => setAdding(false)} />}
      <nav className="flex-1 p-2 space-y-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-emerald-500/20 text-emerald-400"
                  : "text-gray-400 hover:bg-gray-700 hover:text-gray-200"
              }`
            }
          >
            <Icon size={18} />
            <span className="flex-1">{label}</span>
            {label === "Review" && reviewCount > 0 && (
              <span className="bg-amber-500/20 text-amber-400 text-xs px-1.5 py-0.5 rounded-full">
                {reviewCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="p-2 border-t border-gray-700">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-gray-700 hover:text-gray-200 w-full"
        >
          <LogOut size={18} />
          Logout
        </button>
        {version?.available && (
          <NavLink
            to="/settings"
            className="flex items-center gap-1.5 px-3 pt-1.5 pb-0.5 text-[11px] font-mono text-gray-500 hover:text-gray-300"
            title={
              `Running ${version.running_version}` +
              (version.started_at ? ` since ${new Date(version.started_at).toLocaleString()}` : "") +
              (version.restart_needed ? `\nVersion ${version.version} is installed: restart to finish updating` : "") +
              (version.dirty ? "\nModified locally" : "")
            }
          >
            {(version.restart_needed || version.dirty) && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" aria-hidden />
            )}
            <span>v {version.running_version}</span>
            {version.restart_needed && <span className="text-amber-400 font-sans">· restart needed</span>}
          </NavLink>
        )}
      </div>
    </aside>
  );
}
