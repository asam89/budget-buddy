import { useEffect, useState } from "react";
import { Plus, CreditCard, Landmark, PiggyBank, TrendingUp } from "lucide-react";
import { api, Account } from "../api/client";

const ACCOUNT_ICONS: Record<string, React.ElementType> = {
  checking: Landmark,
  savings: PiggyBank,
  credit: CreditCard,
  investment: TrendingUp,
};

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
  }).format(amount);
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    account_type: "checking",
    current_balance: 0,
  });

  const loadAccounts = () => {
    setLoading(true);
    api
      .getAccounts()
      .then(setAccounts)
      .catch(() => setAccounts([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadAccounts();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.createAccount(formData);
    setShowForm(false);
    setFormData({ name: "", account_type: "checking", current_balance: 0 });
    loadAccounts();
  };

  const totalBalance = accounts.reduce((sum, a) => sum + a.current_balance, 0);

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Accounts</h2>
          <p className="text-gray-500 mt-1">
            Total balance: {formatCurrency(totalBalance)}
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-brand-600 text-white px-4 py-2 rounded-lg hover:bg-brand-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Account
        </button>
      </div>

      {/* Add account form */}
      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">Add Manual Account</h3>
          <form onSubmit={handleSubmit} className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="block text-sm text-gray-600 mb-1">
                Account Name
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                className="w-full border rounded-lg px-3 py-2"
                placeholder="e.g. TD Chequing"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Type</label>
              <select
                value={formData.account_type}
                onChange={(e) =>
                  setFormData({ ...formData, account_type: e.target.value })
                }
                className="border rounded-lg px-3 py-2"
              >
                <option value="checking">Chequing</option>
                <option value="savings">Savings</option>
                <option value="credit">Credit Card</option>
                <option value="investment">Investment</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">
                Balance
              </label>
              <input
                type="number"
                step="0.01"
                value={formData.current_balance}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    current_balance: parseFloat(e.target.value) || 0,
                  })
                }
                className="w-32 border rounded-lg px-3 py-2"
              />
            </div>
            <button
              type="submit"
              className="bg-brand-600 text-white px-6 py-2 rounded-lg hover:bg-brand-700"
            >
              Add
            </button>
          </form>
        </div>
      )}

      {/* Account list */}
      {loading ? (
        <p className="text-gray-400">Loading accounts...</p>
      ) : accounts.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-8 text-center text-gray-500">
          <Landmark className="w-12 h-12 mx-auto mb-3 text-gray-300" />
          <p className="text-lg mb-2">No accounts yet</p>
          <p>Add a manual account or connect your bank via Plaid.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {accounts.map((account) => {
            const Icon = ACCOUNT_ICONS[account.account_type] || Landmark;
            return (
              <div
                key={account.id}
                className="bg-white rounded-xl shadow-sm border p-6 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-gray-100 rounded-lg">
                      <Icon className="w-5 h-5 text-gray-600" />
                    </div>
                    <div>
                      <h4 className="font-semibold">{account.name}</h4>
                      <p className="text-sm text-gray-500 capitalize">
                        {account.account_type}
                        {account.mask && ` ••••${account.mask}`}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="mt-4">
                  <p className="text-2xl font-bold">
                    {formatCurrency(account.current_balance)}
                  </p>
                  {account.available_balance !== null &&
                    account.available_balance !== account.current_balance && (
                      <p className="text-sm text-gray-500">
                        Available: {formatCurrency(account.available_balance)}
                      </p>
                    )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
