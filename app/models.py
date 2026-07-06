import hashlib
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, ForeignKey,
    Boolean, Text, Index, UniqueConstraint,
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


class ImportTemplate(Base):
    __tablename__ = "import_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    header_signature = Column(String, unique=True, nullable=False)  # hash of sorted header names
    mapping = Column(Text, nullable=False)  # JSON: column mapping config
    created_at = Column(DateTime, default=datetime.utcnow)


class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    entity_type = Column(String, nullable=False)  # 'household' | 'rental' | 'business' | 'other'
    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="entity")
    splits = relationship("TransactionSplit", back_populates="entity")
    rules = relationship("EntityRule", back_populates="entity")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_entity_date", "entity_id", "date"),
        Index("ix_transactions_date", "date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    plaid_txn_id = Column(String, unique=True, nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    import_source_id = Column(Integer, ForeignKey("import_sources.id"), nullable=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="CAD")
    date = Column(Date, nullable=False)
    name = Column(String, nullable=False)
    merchant_name = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    txn_type = Column(String, default="expense")  # 'expense' | 'income' | 'transfer'
    entity_source = Column(String, nullable=True)  # 'rule' | 'default' | 'manual'
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
    entity = relationship("Entity", back_populates="transactions")
    splits = relationship("TransactionSplit", back_populates="transaction", cascade="all, delete-orphan")

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


class TransactionSplit(Base):
    __tablename__ = "transaction_splits"
    __table_args__ = (
        Index("ix_transaction_splits_entity_id", "entity_id"),
    )

    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    amount = Column(Float, nullable=False)  # signed, same convention as Transaction.amount
    percent = Column(Float, nullable=True)  # optional; if set, amount derived from it
    notes = Column(Text, nullable=True)

    transaction = relationship("Transaction", back_populates="splits")
    entity = relationship("Entity", back_populates="splits")


class EntityRule(Base):
    __tablename__ = "entity_rules"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    field = Column(String, nullable=False)     # 'name' | 'merchant_name' | 'account_id' | 'category_id'
    operator = Column(String, nullable=False)  # 'contains' | 'equals' | 'starts_with'
    value = Column(String, nullable=False)
    priority = Column(Integer, default=100)    # lower runs first; first match wins
    is_active = Column(Boolean, default=True)

    entity = relationship("Entity", back_populates="rules")


class SavedView(Base):
    __tablename__ = "saved_views"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    config = Column(Text, nullable=False)  # JSON: filters, sort, visible columns, grouping
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
