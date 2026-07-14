const BASE = "/api";

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      ...(opts?.headers || {}),
      ...(opts?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    },
    credentials: "same-origin",
  });
  if (res.status === 401) {
    throw new Error("Not authenticated");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return {} as T;
  return res.json();
}

// Auth
export const authStatus = () => request<{ setup_required: boolean }>("/auth/status");
export const setup = (username: string, password: string) =>
  request("/auth/setup", { method: "POST", body: JSON.stringify({ username, password }) });
export const login = (username: string, password: string) =>
  request("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
export const logout = () => request("/auth/logout", { method: "POST" });
export const getMe = () => request<{ id: number; username: string }>("/auth/me");

// Accounts
export const getAccounts = () => request<Account[]>("/accounts/");
export const createAccount = (data: { name: string; account_type: string; current_balance?: number }) =>
  request<Account>("/accounts/", { method: "POST", body: JSON.stringify(data) });

// Transactions
export const getTransactions = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return request<Transaction[]>(`/transactions/${qs}`);
};
export const getTransactionTotals = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return request<TransactionTotals>(`/transactions/totals${qs}`);
};
export const getPendingReview = () => request<Transaction[]>("/transactions/pending-review");
export const reviewTransaction = (id: number, data: ReviewData) =>
  request<Transaction>(`/transactions/${id}/review`, { method: "PUT", body: JSON.stringify(data) });
export const createTransaction = (data: TransactionCreate) =>
  request<Transaction>("/transactions/", { method: "POST", body: JSON.stringify(data) });
export const inlineEditTransaction = (id: number, data: Partial<TransactionInlineEdit>) =>
  request<Transaction>(`/transactions/${id}`, { method: "PATCH", body: JSON.stringify(data) });
export const bulkAssignEntity = (transactionIds: number[], entityId: number) =>
  request<{ updated_count: number }>("/transactions/bulk-entity", {
    method: "POST",
    body: JSON.stringify({ transaction_ids: transactionIds, entity_id: entityId }),
  });
export const deleteTransaction = (id: number) =>
  request<{}>(`/transactions/${id}`, { method: "DELETE" });

// Categories
export const getCategories = () => request<Category[]>("/categories/");
export const seedCategories = () => request<Category[]>("/categories/seed-defaults", { method: "POST" });

// Entities
export const getEntities = () => request<Entity[]>("/entities/");

// Saved Views
export const getSavedViews = () => request<SavedView[]>("/entities/views/all");
export const createSavedView = (data: { name: string; config: string }) =>
  request<SavedView>("/entities/views", { method: "POST", body: JSON.stringify(data) });
export const updateSavedView = (id: number, data: { name: string; config: string }) =>
  request<SavedView>(`/entities/views/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteSavedView = (id: number) =>
  request<{}>(`/entities/views/${id}`, { method: "DELETE" });

// Budgets
export const getBudgets = () => request<Budget[]>("/budgets/");
export const createBudget = (data: { category_id: number; monthly_limit: number }) =>
  request<Budget>("/budgets/", { method: "POST", body: JSON.stringify(data) });

// Bills
export const getBills = () => request<Bill[]>("/bills/");
export const createBill = (data: BillCreate) =>
  request<Bill>("/bills/", { method: "POST", body: JSON.stringify(data) });

// Import
export const uploadFile = (endpoint: string, file: File, accountId: number) => {
  const form = new FormData();
  form.append("file", file);
  form.append("account_id", accountId.toString());
  return request<ImportSource>(endpoint, { method: "POST", body: form });
};
export const getImportHistory = () => request<ImportSource[]>("/import/history");

// Dashboard
export const getDashboard = (months = 1) =>
  request<DashboardSummary>(`/dashboard/summary?months=${months}`);
export const getBalances = () => request<BalanceItem[]>("/dashboard/balances");

// Export helpers (trigger file download via window.open)
export const exportTransactionsCsv = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  window.open(`${BASE}/export/transactions/csv${qs}`, "_blank");
};
export const exportTransactionsXlsx = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  window.open(`${BASE}/export/transactions/xlsx${qs}`, "_blank");
};
export const exportFullWorkbook = () => {
  window.open(`${BASE}/export/full`, "_blank");
};

// LLM / model
export const getLlmHealth = () => request<LlmHealth>("/settings/llm/health");

// Budget Setup (AI-assisted)
export const analyzeBudgetFile = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<BudgetProposal>("/budget-setup/analyze", { method: "POST", body: form });
};
export const analyzeBudgetPaste = (text: string) => {
  const form = new FormData();
  form.append("text", text);
  return request<BudgetProposal>("/budget-setup/analyze-paste", { method: "POST", body: form });
};
export const commitBudgetSetup = (items: BudgetCommitItem[]) =>
  request<BudgetCommitResult>("/budget-setup/commit", {
    method: "POST",
    body: JSON.stringify({ items }),
  });

// Types
export interface LlmHealth {
  provider_name: string;
  reachable: boolean;
  model_available: boolean;
  latency_ms: number;
  error: string | null;
}

export interface BudgetProposalItem {
  label: string;
  source_amount: number;
  period: string;
  monthly_amount: number;
  category: string;
  kind: string;
  confidence: number;
  note: string;
}

export interface BudgetProposal {
  ai_used: boolean;
  assisting_model: string | null;
  existing_categories: string[];
  items: BudgetProposalItem[];
}

export interface BudgetCommitItem {
  category: string;
  monthly_amount: number;
  kind: string;
}

export interface BudgetCommitResult {
  categories_created: number;
  budgets_created: number;
  budgets_updated: number;
  income_items_skipped: number;
  categories_budgeted: number;
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
  entity_id: number | null;
  entity_source: string | null;
  txn_type: string | null;
  amount: number;
  currency: string;
  date: string;
  name: string;
  merchant_name: string | null;
  category_id: number | null;
  pending: boolean;
  review_status: string;
  review_source: string | null;
  confidence: number | null;
  notes: string | null;
  created_at: string;
}

export interface TransactionInlineEdit {
  name?: string;
  category_id?: number;
  entity_id?: number;
  notes?: string;
  amount?: number;
  date?: string;
}

export interface TransactionTotals {
  count: number;
  sum: number;
  income: number;
  expenses: number;
  entity_subtotals: Record<string, number>;
}

export interface Entity {
  id: number;
  name: string;
  entity_type: string;
  is_default: boolean;
  created_at: string;
}

export interface SavedView {
  id: number;
  name: string;
  config: string;
  created_at: string;
}

export interface TransactionCreate {
  account_id: number;
  amount: number;
  date: string;
  name: string;
  merchant_name?: string;
  category_id?: number;
}

export interface ReviewData {
  review_status: string;
  name?: string;
  amount?: number;
  date?: string;
  category_id?: number;
  merchant_name?: string;
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  icon: string | null;
  color: string | null;
  is_system: boolean;
}

export interface Budget {
  id: number;
  category_id: number;
  monthly_limit: number;
  year_month: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Bill {
  id: number;
  name: string;
  amount: number;
  currency: string;
  category_id: number | null;
  frequency: string;
  due_day: number | null;
  next_due_date: string | null;
  is_active: boolean;
  notes: string | null;
}

export interface BillCreate {
  name: string;
  amount: number;
  frequency: string;
  due_day?: number;
  next_due_date?: string;
  notes?: string;
}

export interface ImportSource {
  id: number;
  source_type: string;
  filename: string | null;
  record_count: number;
  status: string;
  error_message: string | null;
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
  budget_status: { category: string; budget: number; spent: number; remaining: number; percent_used: number }[];
}

export interface BalanceItem {
  id: number;
  name: string;
  type: string;
  balance: number;
  currency: string;
}
