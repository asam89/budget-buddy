import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Wallet, ArrowLeftRight, Upload,
  Target, AlertCircle, BarChart3, LogOut, Sparkles,
} from "lucide-react";
import { logout } from "../api/client";

const links = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/accounts", icon: Wallet, label: "Accounts" },
  { to: "/transactions", icon: ArrowLeftRight, label: "Transactions" },
  { to: "/import", icon: Upload, label: "Import" },
  { to: "/budgets", icon: Target, label: "Budgets" },
  { to: "/budget-setup", icon: Sparkles, label: "Budget Setup" },
  { to: "/review", icon: AlertCircle, label: "Review" },
  { to: "/reports", icon: BarChart3, label: "Reports" },
];

export default function Sidebar({ username }: { username: string }) {
  const handleLogout = async () => {
    await logout();
    window.location.href = "/login";
  };

  return (
    <aside className="w-56 bg-gray-800 border-r border-gray-700 flex flex-col">
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-xl font-bold text-emerald-400">Budget Buddy</h1>
        <p className="text-xs text-gray-400 mt-1">{username}</p>
      </div>
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
            {label}
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
      </div>
    </aside>
  );
}
