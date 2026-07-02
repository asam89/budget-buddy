import { useState, useEffect } from "react";
import { getTransactions, getAccounts, Transaction, Account } from "../api/client";

function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountFilter, setAccountFilter] = useState("");

  useEffect(() => {
    getAccounts().then(setAccounts);
  }, []);

  useEffect(() => {
    const params: Record<string, string> = {};
    if (accountFilter) params.account_id = accountFilter;
    getTransactions(params).then(setTransactions);
  }, [accountFilter]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Transactions</h2>
        <select
          value={accountFilter}
          onChange={(e) => setAccountFilter(e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm"
        >
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
      </div>

      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-700 bg-gray-800/50">
              <th className="text-left py-3 px-4">Date</th>
              <th className="text-left py-3 px-4">Description</th>
              <th className="text-left py-3 px-4">Source</th>
              <th className="text-left py-3 px-4">Status</th>
              <th className="text-right py-3 px-4">Amount</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => (
              <tr key={t.id} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                <td className="py-3 px-4 text-gray-400">{t.date}</td>
                <td className="py-3 px-4">
                  <p>{t.merchant_name || t.name}</p>
                  {t.merchant_name && t.name !== t.merchant_name && (
                    <p className="text-xs text-gray-500">{t.name}</p>
                  )}
                </td>
                <td className="py-3 px-4">
                  <span className="text-xs bg-gray-700 px-2 py-0.5 rounded capitalize">
                    {t.review_source || "unknown"}
                  </span>
                </td>
                <td className="py-3 px-4">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    t.review_status === "confirmed" ? "bg-emerald-500/20 text-emerald-400" :
                    t.review_status === "pending" ? "bg-yellow-500/20 text-yellow-400" :
                    "bg-red-500/20 text-red-400"
                  }`}>
                    {t.review_status}
                  </span>
                </td>
                <td className={`py-3 px-4 text-right font-medium ${t.amount < 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {fmt(t.amount)}
                </td>
              </tr>
            ))}
            {transactions.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-8 text-gray-500">
                  No transactions found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
