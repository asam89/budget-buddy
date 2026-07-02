import { useState, useEffect, FormEvent } from "react";
import { getAccounts, createAccount, Account } from "../api/client";
import { Plus, Wallet } from "lucide-react";

const TYPES = ["checking", "savings", "credit", "investment", "other"];

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState("checking");
  const [balance, setBalance] = useState("0");

  useEffect(() => {
    getAccounts().then(setAccounts);
  }, []);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    const acct = await createAccount({
      name,
      account_type: type,
      current_balance: parseFloat(balance) || 0,
    });
    setAccounts([...accounts, acct]);
    setShowForm(false);
    setName("");
    setBalance("0");
  };

  const fmt = (n: number) =>
    new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Accounts</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm"
        >
          <Plus size={16} /> Add Account
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-gray-800 rounded-xl p-4 border border-gray-700 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <input
              placeholder="Account name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
              required
            />
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
              ))}
            </select>
            <input
              type="number"
              step="0.01"
              placeholder="Balance"
              value={balance}
              onChange={(e) => setBalance(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <button type="submit" className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm">
            Create
          </button>
        </form>
      )}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {accounts.map((a) => (
          <div key={a.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <div className="flex items-center gap-3 mb-3">
              <Wallet className="text-emerald-400" size={20} />
              <div>
                <p className="font-medium">{a.name}</p>
                <p className="text-xs text-gray-400 capitalize">{a.account_type}</p>
              </div>
            </div>
            <p className={`text-xl font-bold ${a.current_balance >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {fmt(a.current_balance)}
            </p>
            {a.mask && <p className="text-xs text-gray-500 mt-1">****{a.mask}</p>}
          </div>
        ))}
        {accounts.length === 0 && (
          <p className="text-gray-500 col-span-full text-center py-8">
            No accounts yet. Add one manually or connect via Plaid in Settings.
          </p>
        )}
      </div>
    </div>
  );
}
