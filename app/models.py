import hashlib
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, ForeignKey,
    Boolean, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Institution(Base):
    __tablename__ = "institutions"

    id = Column(Integer, primary_key=True, index=True)
    plaid_inst_id = Column(String, unique=True, nullable=True)
    name = Column(String, nullable=False)
    logo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    accounts = relationship("Account", back_populates="institution")


class PlaidItem(Base):
    __tablename__ = "plaid_items"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String, unique=True, nullable=False)
    access_token = Column(String, nullable=False)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    cursor = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    institution = relationship("Institution")
    accounts = relationship("Account", back_populates="plaid_item")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    plaid_account_id = Column(String, unique=True, nullable=True)
    plaid_item_id = Column(Integer, ForeignKey("plaid_items.id"), nullable=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    name = Column(String, nullable=False)
    official_name = Column(String, nullable=True)
    account_type = Column(String, nullable=False)
    account_subtype = Column(String, nullable=True)
    mask = Column(String, nullable=True)
    current_balance = Column(Float, default=0.0)
    available_balance = Column(Float, nullable=True)
    currency = Column(String, default="CAD")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    institution = relationship("Institution", back_populates="accounts")
    plaid_item = relationship("PlaidItem", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    icon = Column(String, nullable=True)
    color = Column(String, nullable=True)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship("Category", remote_side=[id])
    transactions = relationship("Transaction", back_populates="category_rel")
    budgets = relationship("Budget", back_populates="category_rel")


class ImportSource(Base):
    __tablename__ = "import_sources"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String, nullable=False)
    filename = Column(String, nullable=True)
    file_hash = Column(String, nullable=True)
    record_count = Column(Integer, default=0)
    status = Column(String, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="import_source")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    plaid_txn_id = Column(String, unique=True, nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    import_source_id = Column(Integer, ForeignKey("import_sources.id"), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="CAD")
    date = Column(Date, nullable=False)
    name = Column(String, nullable=False)
    merchant_name = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    pending = Column(Boolean, default=False)
    review_status = Column(String, default="confirmed")
    review_source = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    source_file = Column(String, nullable=True)
    source_page = Column(Integer, nullable=True)
    dedup_hash = Column(String, unique=True, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="transactions")
    category_rel = relationship("Category", back_populates="transactions")
    import_source = relationship("ImportSource", back_populates="transactions")

    @staticmethod
    def compute_dedup_hash(txn_date: date, amount: float, name: str, account_id: int) -> str:
        normalized = f"{txn_date.isoformat()}|{amount:.2f}|{name.strip().lower()}|{account_id}"
        return hashlib.sha256(normalized.encode()).hexdigest()


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    monthly_limit = Column(Float, nullable=False)
    year_month = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category_rel = relationship("Category", back_populates="budgets")


class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="CAD")
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    frequency = Column(String, nullable=False)
    due_day = Column(Integer, nullable=True)
    next_due_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category_rel = relationship("Category")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
