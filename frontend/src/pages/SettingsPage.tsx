import { useState } from "react";
import { Link2, RefreshCw, AlertCircle, CheckCircle } from "lucide-react";
import { api } from "../api/client";

export default function SettingsPage() {
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);

  const handleConnectBank = async () => {
    setLinkError(null);
    try {
      const { link_token } = await api.createLinkToken();
      // In production, this would open the Plaid Link modal
      // For now, show the token for development reference
      alert(
        `Plaid Link Token generated: ${link_token.slice(0, 20)}...\n\n` +
          "To complete the connection, integrate the Plaid Link SDK in production."
      );
    } catch (err) {
      setLinkError(
        "Could not connect to Plaid. Make sure PLAID_CLIENT_ID and PLAID_SECRET are set in .env"
      );
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await api.syncTransactions();
      setSyncResult(
        `Synced successfully! ${(result as { transactions_added: number }).transactions_added} new transactions added.`
      );
    } catch {
      setSyncResult("Sync failed. Check your Plaid connection.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="p-8 max-w-2xl">
      <h2 className="text-2xl font-bold mb-6">Settings</h2>

      {/* Plaid connection */}
      <div className="bg-white rounded-xl shadow-sm border p-6 mb-6">
        <h3 className="text-lg font-semibold mb-2">Bank Connection</h3>
        <p className="text-gray-500 text-sm mb-4">
          Connect your bank accounts, credit cards, and investment accounts
          using Plaid. Your credentials are never stored — Plaid handles
          authentication securely.
        </p>
        <div className="flex gap-3">
          <button
            onClick={handleConnectBank}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Link2 className="w-4 h-4" />
            Connect Bank Account
          </button>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 border border-gray-300 px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing..." : "Sync Transactions"}
          </button>
        </div>
        {linkError && (
          <div className="mt-3 flex items-center gap-2 text-red-600 text-sm">
            <AlertCircle className="w-4 h-4" />
            {linkError}
          </div>
        )}
        {syncResult && (
          <div className="mt-3 flex items-center gap-2 text-green-600 text-sm">
            <CheckCircle className="w-4 h-4" />
            {syncResult}
          </div>
        )}
      </div>

      {/* About */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold mb-2">About Budget Buddy</h3>
        <div className="text-sm text-gray-500 space-y-2">
          <p>
            <strong>Version:</strong> 0.1.0
          </p>
          <p>
            <strong>Data Storage:</strong> All data is stored locally in SQLite.
            Nothing is sent to external servers (except Plaid for bank
            connections).
          </p>
          <p>
            <strong>Privacy:</strong> Your financial data never leaves your
            machine. Plaid handles bank authentication — your bank credentials
            are never stored by Budget Buddy.
          </p>
        </div>
      </div>
    </div>
  );
}
