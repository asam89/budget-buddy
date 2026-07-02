import { useEffect, useState } from "react";
import { Plus, Search } from "lucide-react";
import { api, Transaction, Account } from "../api/client";

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
  }).format(amount);
}

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [filterCategory, setFilterCategory] = useState("");
  const [filterAccount, setFilterAccount] = useState<number | undefined>();
  const [formData, setFormData] = useState({
    account_id: 0,
    amount: 0,
    date: new Date().toISOString().slice(0, 10),
    name: "",
    category: "",
  });

  const loadData = () => {
    setLoading(true);
    Promise.all([
      api.getTransactions({
        category: filterCategory || undefined,
        account_id: filterAccount,
        limit: 200,
      }),
      api.getAccounts(),
    ])
      .then(([txns, accts]) => {
        setTransactions(txns);
        setAccounts(accts);
        if (accts.length > 0 && formData.account_id === 0) {
          setFormData((prev) => ({ ...prev, account_id: accts[0].id }));
        }
      })
      .catch(() => {
        setTransactions([]);
        setAccounts([]);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, [filterCategory, filterAccount]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.createTransaction({
      ...formData,
      date: new Date(formData.date).toISOString(),
    });
    setShowForm(false);
    setFormData({
      account_id: accounts[0]?.id || 0,
      amount: 0,
      date: new Date().toISOString().slice(0, 10),
      name: "",
      category: "",
    });
    loadData();
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Transactions</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-brand-600 text-white px-4 py-2 rounded-lg hover:bg-brand-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Transaction
        </button>
      </div>

      {/* Add transaction form */}
      {showForm && accounts.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">Add Transaction</h3>
          <form onSubmit={handleSubmit} className="grid grid-cols-2 md:grid-cols-5 gap-4 items-end">
            <div>
              <label className="block text-sm text-gray-600 mb-1">Account</label>
              <select
                value={formData.account_id}
                onChange={(e) =>
                  setFormData({ ...formData, account_id: Number(e.target.value) })
                }
                className="w-full border rounded-lg px-3 py-2"
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">
                Description
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                className="w-full border rounded-lg px-3 py-2"
                placeholder="Coffee shop"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">
                Amount (+ expense, - income)
              </label>
              <input
                type="number"
                step="0.01"
                required
                value={formData.amount}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    amount: parseFloat(e.target.value) || 0,
                  })
                }
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Date</label>
              <input
                type="date"
                value={formData.date}
                onChange={(e) =>
                  setFormData({ ...formData, date: e.target.value })
                }
                className="w-full border rounded-lg px-3 py-2"
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

      {/* Filters */}
      <div className="flex gap-4 mb-4">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Filter by category..."
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm"
          />
        </div>
        <select
          value={filterAccount || ""}
          onChange={(e) =>
            setFilterAccount(e.target.value ? Number(e.target.value) : undefined)
          }
          className="border rounded-lg px-3 py-2 text-sm"
        >
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>

      {/* Transaction list */}
      {loading ? (
        <p className="text-gray-400">Loading transactions...</p>
      ) : transactions.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-8 text-center text-gray-500">
          <p className="text-lg mb-2">No transactions found</p>
          <p>Add a transaction or sync from your connected accounts.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b bg-gray-50">
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((txn) => (
                <tr key={txn.id} className="border-b last:border-0 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    {new Date(txn.date).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <div>
                      <span className="font-medium">
                        {txn.merchant_name || txn.name}
                      </span>
                      {txn.merchant_name && txn.merchant_name !== txn.name && (
                        <span className="block text-xs text-gray-400">
                          {txn.name}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {txn.category ? (
                      <span className="bg-gray-100 text-gray-600 px-2 py-1 rounded text-xs">
                        {txn.category}
                      </span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {txn.pending ? (
                      <span className="text-yellow-600 text-xs">Pending</span>
                    ) : (
                      <span className="text-green-600 text-xs">Posted</span>
                    )}
                  </td>
                  <td
                    className={`px-4 py-3 text-right font-medium ${
                      txn.amount < 0 ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {txn.amount < 0 ? "+" : "-"}
                    {formatCurrency(Math.abs(txn.amount))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
