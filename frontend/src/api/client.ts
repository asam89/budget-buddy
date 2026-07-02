const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface Account {
  id: number;
  name: string;
  official_name: string | null;
  account_type: string;
  account_subtype: string | null;
  mask: string | null;
  current_balance: number;
  available_balance: number | null;
  currency: string;
  is_active: boolean;
  created_at: string;
}

export interface Transaction {
  id: number;
  account_id: number;
  amount: number;
  currency: string;
  date: string;
  name: string;
  merchant_name: string | null;
  category: string | null;
  subcategory: string | null;
  pending: boolean;
  notes: string | null;
  created_at: string;
}

export interface DashboardSummary {
  total_balance: number;
  total_income: number;
  total_expenses: number;
  net_cash_flow: number;
  account_count: number;
  recent_transactions: Transaction[];
  spending_by_category: Record<string, number>;
  monthly_trend: { month: string; income: number; expenses: number; net: number }[];
}

export interface BalanceItem {
  id: number;
  name: string;
  type: string;
  balance: number;
  currency: string;
}

export interface SpendingItem {
  category: string;
  amount: number;
}

export const api = {
  getDashboard: (months = 1) =>
    request<DashboardSummary>(`/dashboard/summary?months=${months}`),

  getBalances: () => request<BalanceItem[]>("/dashboard/balances"),

  getSpendingBreakdown: (months = 1) =>
    request<SpendingItem[]>(`/dashboard/spending-breakdown?months=${months}`),

  getAccounts: () => request<Account[]>("/accounts/"),

  createAccount: (data: { name: string; account_type: string; current_balance?: number }) =>
    request<Account>("/accounts/", { method: "POST", body: JSON.stringify(data) }),

  getTransactions: (params?: { account_id?: number; category?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.account_id) search.set("account_id", String(params.account_id));
    if (params?.category) search.set("category", params.category);
    if (params?.limit) search.set("limit", String(params.limit));
    return request<Transaction[]>(`/transactions/?${search}`);
  },

  createTransaction: (data: {
    account_id: number;
    amount: number;
    date: string;
    name: string;
    category?: string;
  }) => request<Transaction>("/transactions/", { method: "POST", body: JSON.stringify(data) }),

  createLinkToken: () => request<{ link_token: string }>("/plaid/link-token", { method: "POST" }),

  exchangeToken: (public_token: string) =>
    request("/plaid/exchange-token", {
      method: "POST",
      body: JSON.stringify({ public_token }),
    }),

  syncTransactions: () => request("/plaid/sync-transactions", { method: "POST" }),
};
