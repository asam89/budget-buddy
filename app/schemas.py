from datetime import datetime
from pydantic import BaseModel


class InstitutionOut(BaseModel):
    id: int
    plaid_institution_id: str | None
    name: str
    logo_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountOut(BaseModel):
    id: int
    name: str
    official_name: str | None
    account_type: str
    account_subtype: str | None
    mask: str | None
    current_balance: float
    available_balance: float | None
    currency: str
    is_active: bool
    institution: InstitutionOut | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountCreate(BaseModel):
    name: str
    account_type: str
    account_subtype: str | None = None
    current_balance: float = 0.0
    currency: str = "CAD"


class TransactionOut(BaseModel):
    id: int
    account_id: int
    amount: float
    currency: str
    date: datetime
    name: str
    merchant_name: str | None
    category: str | None
    subcategory: str | None
    pending: bool
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    account_id: int
    amount: float
    date: datetime
    name: str
    merchant_name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None


class BudgetOut(BaseModel):
    id: int
    category: str
    monthly_limit: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class BudgetCreate(BaseModel):
    category: str
    monthly_limit: float


class PlaidLinkTokenResponse(BaseModel):
    link_token: str


class PlaidExchangeRequest(BaseModel):
    public_token: str


class DashboardSummary(BaseModel):
    total_balance: float
    total_income: float
    total_expenses: float
    net_cash_flow: float
    account_count: int
    recent_transactions: list[TransactionOut]
    spending_by_category: dict[str, float]
    monthly_trend: list[dict]
