from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --- Auth ---
class LoginRequest(BaseModel):
    username: str
    password: str


class SetupRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    is_active: bool
    model_config = {"from_attributes": True}


# --- Institutions ---
class InstitutionOut(BaseModel):
    id: int
    plaid_inst_id: Optional[str]
    name: str
    logo_url: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# --- Accounts ---
class AccountOut(BaseModel):
    id: int
    name: str
    official_name: Optional[str]
    account_type: str
    account_subtype: Optional[str]
    mask: Optional[str]
    current_balance: float
    available_balance: Optional[float]
    currency: str
    is_active: bool
    institution: Optional[InstitutionOut] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class AccountCreate(BaseModel):
    name: str
    account_type: str
    account_subtype: Optional[str] = None
    current_balance: float = 0.0
    currency: str = "CAD"


class AccountEntityMapRequest(BaseModel):
    entity_id: int
    priority: int = 10  # account rules are high priority by default


# --- Categories ---
class CategoryOut(BaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    kind: str
    icon: Optional[str]
    color: Optional[str]
    is_system: bool
    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str
    kind: str = "expense"
    parent_id: Optional[int] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None


# --- Entities ---
class EntityOut(BaseModel):
    id: int
    name: str
    entity_type: str
    color: Optional[str]
    icon: Optional[str]
    is_default: bool
    is_active: bool
    notes: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class EntityCreate(BaseModel):
    name: str
    entity_type: str  # 'household' | 'rental' | 'business' | 'other'
    color: Optional[str] = None
    icon: Optional[str] = None
    is_default: bool = False
    notes: Optional[str] = None


class EntityUpdate(BaseModel):
    name: Optional[str] = None
    entity_type: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


# --- Entity Rules ---
class EntityRuleOut(BaseModel):
    id: int
    entity_id: int
    field: str
    operator: str
    value: str
    priority: int
    is_active: bool
    model_config = {"from_attributes": True}


class EntityRuleCreate(BaseModel):
    field: str       # 'name' | 'merchant_name' | 'account_id' | 'category_id'
    operator: str    # 'contains' | 'equals' | 'starts_with'
    value: str
    priority: int = 100

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed = {"name", "merchant_name", "account_id", "category_id"}
        if v not in allowed:
            raise ValueError(f"field must be one of {allowed}")
        return v

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        allowed = {"contains", "equals", "starts_with"}
        if v not in allowed:
            raise ValueError(f"operator must be one of {allowed}")
        return v


class RuleApplyPreview(BaseModel):
    matched_count: int
    sample_transactions: list[dict]


class RuleApplyResult(BaseModel):
    updated_count: int


# --- Transaction Splits ---
class TransactionSplitOut(BaseModel):
    id: int
    transaction_id: int
    entity_id: int
    amount: float
    percent: Optional[float]
    notes: Optional[str]
    model_config = {"from_attributes": True}


class TransactionSplitItem(BaseModel):
    entity_id: int
    amount: float
    percent: Optional[float] = None
    notes: Optional[str] = None


class TransactionSplitsRequest(BaseModel):
    splits: list[TransactionSplitItem]


# --- Transactions ---
class TransactionOut(BaseModel):
    id: int
    account_id: int
    entity_id: Optional[int]
    amount: float
    currency: str
    date: date
    name: str
    merchant_name: Optional[str]
    category_id: Optional[int]
    txn_type: Optional[str]
    entity_source: Optional[str]
    pending: bool
    review_status: str
    review_source: Optional[str]
    confidence: Optional[float]
    notes: Optional[str]
    created_at: datetime
    splits: list[TransactionSplitOut] = []
    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    account_id: int
    amount: float
    date: date
    name: str
    merchant_name: Optional[str] = None
    category_id: Optional[int] = None
    entity_id: Optional[int] = None
    notes: Optional[str] = None


class TransactionReview(BaseModel):
    review_status: str  # "confirmed" or "rejected"
    name: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[date] = None
    category_id: Optional[int] = None
    merchant_name: Optional[str] = None


class TransactionBulkEntityAssign(BaseModel):
    transaction_ids: list[int]
    entity_id: int


class TransactionInlineEdit(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    entity_id: Optional[int] = None
    notes: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[date] = None


# --- Saved Views ---
class SavedViewOut(BaseModel):
    id: int
    name: str
    config: str
    created_at: datetime
    model_config = {"from_attributes": True}


class SavedViewCreate(BaseModel):
    name: str
    config: str  # JSON string


# --- Budgets ---
class BudgetOut(BaseModel):
    id: int
    category_id: int
    entity_id: Optional[int] = None
    monthly_limit: float
    year_month: Optional[str]
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class BudgetCreate(BaseModel):
    category_id: int
    monthly_limit: float
    year_month: Optional[str] = None
    entity_id: Optional[int] = None


class BudgetUpsert(BaseModel):
    category_id: int
    year_month: str
    monthly_limit: float = Field(ge=0)
    entity_id: Optional[int] = None


class BudgetFillForward(BaseModel):
    category_id: int
    from_year_month: str
    monthly_limit: float = Field(ge=0)
    entity_id: Optional[int] = None


# --- Manual actuals ---
class ManualActualUpsert(BaseModel):
    category_id: int
    year_month: str
    amount: float = Field(ge=0)
    note: Optional[str] = None
    entity_id: Optional[int] = None


class ManualActualBulkEntry(BaseModel):
    category_id: int
    year_month: str
    amount: float = Field(ge=0)


class ManualActualBulk(BaseModel):
    entries: list[ManualActualBulkEntry]
    entity_id: Optional[int] = None


# --- Bills ---
class BillOut(BaseModel):
    id: int
    name: str
    amount: float
    currency: str
    category_id: Optional[int]
    frequency: str
    due_day: Optional[int]
    next_due_date: Optional[date]
    is_active: bool
    notes: Optional[str]
    model_config = {"from_attributes": True}


class BillCreate(BaseModel):
    name: str
    amount: float
    currency: str = "CAD"
    category_id: Optional[int] = None
    frequency: str
    due_day: Optional[int] = None
    next_due_date: Optional[date] = None
    notes: Optional[str] = None


# --- Plaid ---
class PlaidLinkTokenResponse(BaseModel):
    link_token: str


class PlaidExchangeRequest(BaseModel):
    public_token: str


# --- Import ---
class ImportSourceOut(BaseModel):
    id: int
    source_type: str
    filename: Optional[str]
    record_count: int
    status: str
    error_message: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# --- Dashboard ---
class SavedSummary(BaseModel):
    """Total-saved figures, all derived from the shared aggregation layer."""
    year_month: str
    month_income_actual: float
    month_expense_actual: float
    month_saved_actual: float
    month_saved_budget: float
    ytd_saved_actual: float
    ytd_through_month: int
    year_saved_budget: float


class DashboardSummary(BaseModel):
    total_balance: float
    total_income: float
    total_expenses: float
    net_cash_flow: float
    account_count: int
    recent_transactions: list[TransactionOut]
    spending_by_category: dict[str, float]
    monthly_trend: list[dict]
    budget_status: list[dict]
    saved: SavedSummary
