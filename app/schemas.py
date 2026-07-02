from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel


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


# --- Categories ---
class CategoryOut(BaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    icon: Optional[str]
    color: Optional[str]
    is_system: bool
    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    icon: Optional[str] = None
    color: Optional[str] = None


# --- Transactions ---
class TransactionOut(BaseModel):
    id: int
    account_id: int
    amount: float
    currency: str
    date: date
    name: str
    merchant_name: Optional[str]
    category_id: Optional[int]
    pending: bool
    review_status: str
    review_source: Optional[str]
    confidence: Optional[float]
    notes: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    account_id: int
    amount: float
    date: date
    name: str
    merchant_name: Optional[str] = None
    category_id: Optional[int] = None
    notes: Optional[str] = None


class TransactionReview(BaseModel):
    review_status: str  # "confirmed" or "rejected"
    name: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[date] = None
    category_id: Optional[int] = None
    merchant_name: Optional[str] = None


# --- Budgets ---
class BudgetOut(BaseModel):
    id: int
    category_id: int
    monthly_limit: float
    year_month: Optional[str]
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class BudgetCreate(BaseModel):
    category_id: int
    monthly_limit: float
    year_month: Optional[str] = None


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
