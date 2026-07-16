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
    // Session expired/absent: trigger the app's auth gate (App listens for
    // this and drops to the login screen) instead of leaving pages stuck on a
    // dead "Not authenticated" error. Skip for the auth probes themselves so
    // the initial getMe()/authStatus() can't cause a redirect loop.
    if (!path.startsWith("/auth")) {
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
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
export const getNeedsCategory = () => request<Transaction[]>("/transactions/needs-category");
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
export const createCategory = (data: { name: string; kind: string; entity_id?: number | null }) =>
  request<Category>("/categories/", { method: "POST", body: JSON.stringify(data) });
export const updateCategory = (id: number, data: { name?: string; kind?: string; entity_id?: number | null }) =>
  request<Category>(`/categories/${id}`, { method: "PATCH", body: JSON.stringify(data) });
export const deleteCategory = (id: number) =>
  request<{ deleted: boolean; budgets_deleted: number; manual_actuals_deleted: number }>(
    `/categories/${id}`,
    { method: "DELETE" },
  );

// Entities
export const getEntities = () => request<Entity[]>("/entities/");
export const createEntity = (data: {
  name: string;
  entity_type: string;
  color?: string;
  is_default?: boolean;
}) => request<Entity>("/entities/", { method: "POST", body: JSON.stringify(data) });
export const updateEntity = (
  id: number,
  data: { name?: string; entity_type?: string; color?: string; is_default?: boolean; is_active?: boolean },
) => request<Entity>(`/entities/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const deactivateEntity = (id: number) =>
  request<{}>(`/entities/${id}`, { method: "DELETE" });

// Saved Views
export const getSavedViews = () => request<SavedView[]>("/entities/views/all");
export const createSavedView = (data: { name: string; config: string }) =>
  request<SavedView>("/entities/views", { method: "POST", body: JSON.stringify(data) });
export const updateSavedView = (id: number, data: { name: string; config: string }) =>
  request<SavedView>(`/entities/views/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteSavedView = (id: number) =>
  request<{}>(`/entities/views/${id}`, { method: "DELETE" });

const entityParam = (entityId?: number | null) =>
  entityId != null ? `&entity_id=${entityId}` : "";

// Budgets
export const getBudgets = () => request<Budget[]>("/budgets/");
export const createBudget = (data: { category_id: number; monthly_limit: number }) =>
  request<Budget>("/budgets/", { method: "POST", body: JSON.stringify(data) });
export const upsertBudget = (data: { category_id: number; year_month: string; monthly_limit: number; entity_id?: number | null }) =>
  request<Budget>("/budgets/upsert", { method: "POST", body: JSON.stringify(data) });
export const fillForwardBudget = (data: { category_id: number; from_year_month: string; monthly_limit: number; entity_id?: number | null }) =>
  request<{ updated: number }>("/budgets/fill-forward", { method: "POST", body: JSON.stringify(data) });

// Manual actuals / year grid
export type CellSource = "manual" | "transactions" | "none";
export interface ActualCell {
  year_month: string;
  effective: number | null;
  source: CellSource;
  transaction_sum: number;
  manual_amount: number | null;
  budget: number | null;
}
export interface ActualLine {
  category_id: number;
  category_name: string;
  kind: string;
  entity_id: number | null;
  cells: ActualCell[];
}
export interface YearGrid {
  year: number;
  lines: ActualLine[];
}
export interface MonthTotals {
  year_month: string;
  income_actual: number;
  expense_actual: number;
  income_budget: number;
  expense_budget: number;
  saved_actual: number;
  saved_budget: number;
}
export interface YearSummary {
  year: number;
  months: MonthTotals[];
  saved_budget_year: number;
  income_budget_year: number;
  expense_budget_year: number;
  saved_actual_ytd: number;
  income_actual_ytd: number;
  expense_actual_ytd: number;
  ytd_through_month: number;
}

export const getActualsYear = (year: number, entityId?: number | null) =>
  request<YearGrid>(`/actuals/?year=${year}${entityParam(entityId)}`);
export const upsertActual = (data: { category_id: number; year_month: string; amount: number; note?: string; entity_id?: number | null }) =>
  request<ActualCell>("/actuals/", { method: "POST", body: JSON.stringify(data) });
export const bulkActuals = (entries: { category_id: number; year_month: string; amount: number }[], entityId?: number | null) =>
  request<{ upserted: number }>("/actuals/bulk", { method: "POST", body: JSON.stringify({ entries, entity_id: entityId ?? null }) });
export const deleteActual = (categoryId: number, yearMonth: string, entityId?: number | null) =>
  request<{}>(`/actuals/${categoryId}/${yearMonth}?_=1${entityParam(entityId)}`, { method: "DELETE" });
export const getMonthTotals = (yearMonth: string, entityId?: number | null) =>
  request<MonthTotals>(`/actuals/month-totals?year_month=${yearMonth}${entityParam(entityId)}`);
export const getYearSummary = (year: number, entityId?: number | null) =>
  request<YearSummary>(`/actuals/year-summary?year=${year}${entityParam(entityId)}`);

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
export const getDashboard = (months = 1, entityId?: number | null) =>
  request<DashboardSummary>(`/dashboard/summary?months=${months}${entityParam(entityId)}`);
export const getBalances = () => request<BalanceItem[]>("/dashboard/balances");
export interface EntityBreakdown {
  entity_id: number;
  entity_name: string;
  entity_type: string;
  color: string | null;
  income: number;
  expenses: number;
  net: number;
}
export const getEntityBreakdown = (months = 1) =>
  request<EntityBreakdown[]>(`/dashboard/entity-breakdown?months=${months}`);

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

export interface BudgetAnalyzeEvent {
  stage: string;
  detail: Record<string, unknown>;
}

// Consume a Server-Sent-Events analyze stream, invoking onEvent per step and
// resolving with the final proposal (the "complete" event's payload).
async function streamAnalyze(
  path: string,
  body: FormData,
  onEvent: (e: BudgetAnalyzeEvent) => void,
): Promise<BudgetProposal> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    body,
    credentials: "same-origin",
  });
  if (res.status === 401) throw new Error("Not authenticated");
  if (!res.ok || !res.body) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail || `HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let proposal: BudgetProposal | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const line = buf
        .slice(0, idx)
        .split("\n")
        .find((l) => l.startsWith("data:"));
      buf = buf.slice(idx + 2);
      if (!line) continue;
      const evt = JSON.parse(line.slice(5).trim()) as BudgetAnalyzeEvent;
      if (evt.stage === "complete") {
        proposal = evt.detail as unknown as BudgetProposal;
      } else if (evt.stage === "error") {
        throw new Error((evt.detail.error as string) || "Analysis failed");
      }
      onEvent(evt);
    }
  }
  if (!proposal) throw new Error("Analysis did not complete");
  return proposal;
}

export const analyzeBudgetFileStream = (
  file: File,
  onEvent: (e: BudgetAnalyzeEvent) => void,
) => {
  const form = new FormData();
  form.append("file", file);
  return streamAnalyze("/budget-setup/analyze-stream", form, onEvent);
};

export const analyzeBudgetPasteStream = (
  text: string,
  onEvent: (e: BudgetAnalyzeEvent) => void,
) => {
  const form = new FormData();
  form.append("text", text);
  return streamAnalyze("/budget-setup/analyze-paste-stream", form, onEvent);
};

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
  category: string | null;
  needs_category: boolean;
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
  category: string | null;
  label?: string;
  monthly_amount: number;
  kind: string;
}

// Legacy 'Other' category migration
export interface OtherGroup {
  key: string;
  kind: string;
  label: string;
  count: number;
  amount: number;
}
export interface OtherSummary {
  exists: boolean;
  category_id: number | null;
  groups: OtherGroup[];
  totals: Record<string, number>;
}
export interface OtherAssignment {
  group_key: string;
  to_category_id?: number;
  new_category_name?: string;
}
export const getOtherSummary = () => request<OtherSummary>("/migration/other");
export const reassignOther = (assignments: OtherAssignment[]) =>
  request<{ moved: number; other_deleted: boolean; remaining_references: number }>(
    "/migration/other/reassign",
    { method: "POST", body: JSON.stringify({ assignments }) },
  );
export const completeOtherMigration = () =>
  request<{ other_deleted: boolean; already_absent: boolean }>("/migration/other/complete", {
    method: "POST",
  });

// Insights (WS-D)
export interface InsightsFindings {
  period: string;
  period_label: string;
  previous_period_label: string;
  totals: {
    expense_actual: number;
    expense_budget: number;
    income_actual: number;
    saved_actual: number;
    savings_rate_pct: number;
  };
  top_categories: { name: string; actual: number; budget: number; variance: number; share_pct: number }[];
  over_budget: { name: string; actual: number; budget: number; overage: number }[];
  biggest_changes: { name: string; previous: number; current: number; delta: number }[];
}

export interface InsightsNarrative {
  summary: string;
  bullets: string[];
  dropped: number;
}

export interface InsightsResult {
  findings: InsightsFindings;
  generated: boolean;
  narrative: InsightsNarrative | null;
  model: string | null;
  generated_at: string | null;
  error: string | null;
  cached: boolean;
  prompt_version: string;
}

export const getInsightsFindings = (yearMonth: string) =>
  request<{ findings: InsightsFindings; has_cached_narrative: boolean }>(
    `/insights/findings?year_month=${yearMonth}`,
  );

export const generateInsights = (yearMonth: string, force = false) =>
  request<InsightsResult>(
    `/insights/generate?year_month=${yearMonth}&force=${force}`,
    { method: "POST" },
  );

// App version / self-update
export interface VersionInfo {
  available: boolean;
  version: string;
  commit: string | null;
  commit_date: string | null;
  dirty: boolean;
}
export interface UpdateCheck {
  available: boolean;
  status: "up_to_date" | "behind" | "ahead" | "diverged" | "unknown";
  behind: number;
  ahead: number;
  local_version: string;
  latest_version: string;
  error: string | null;
}
export const getVersion = () => request<VersionInfo>("/version");
export const checkForUpdate = () => request<UpdateCheck>("/version/check");
export const startUpdate = () => request<{ started: boolean }>("/version/update", { method: "POST" });
export const getUpdateLog = () => request<{ lines: string[] }>("/version/update/log");

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
  color: string | null;
  icon: string | null;
  is_default: boolean;
  is_active: boolean;
  notes: string | null;
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
  kind: string;
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
  saved: SavedSummary;
}

export interface SavedSummary {
  year_month: string;
  month_income_actual: number;
  month_expense_actual: number;
  month_saved_actual: number;
  month_saved_budget: number;
  ytd_saved_actual: number;
  ytd_through_month: number;
  year_saved_budget: number;
}

export interface BalanceItem {
  id: number;
  name: string;
  type: string;
  balance: number;
  currency: string;
}
