"""All ORM tables. Category-specific attributes live in JSON `attrs` columns."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


def _attrs() -> Mapped[dict[str, Any]]:
    return mapped_column(JSON, default=dict, nullable=False)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    stir: Mapped[str] = mapped_column(String(9), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    city: Mapped[str] = mapped_column(String(80), default="Toshkent")
    district: Mapped[str | None] = mapped_column(String(80))
    tax_regime: Mapped[str] = mapped_column(String(10), default="turnover")
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256 hex
    telegram_chat_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    username: Mapped[str] = mapped_column(String(100), unique=True)
    category_hint: Mapped[str] = mapped_column(String(20))
    seller_type_default: Mapped[str] = mapped_column(String(10), default="shop")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_msg_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RawPost(Base):
    __tablename__ = "raw_posts"
    __table_args__ = (UniqueConstraint("source", "msg_id", name="uq_raw_source_msg"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    msg_id: Mapped[int] = mapped_column(Integer)
    posted_at: Mapped[datetime] = mapped_column(DateTime)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(40), index=True)
    has_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    processed: Mapped[int] = mapped_column(Integer, default=0, index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        Index("ix_listings_cat_model", "category", "model_norm"),
        Index("ix_listings_posted", "posted_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    raw_post_id: Mapped[int | None] = mapped_column(ForeignKey("raw_posts.id"))
    category: Mapped[str] = mapped_column(String(10))
    brand: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120))
    model_norm: Mapped[str] = mapped_column(String(120))
    condition: Mapped[str | None] = mapped_column(String(10))
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    price_uzs: Mapped[float] = mapped_column(Float)
    price_usd: Mapped[float] = mapped_column(Float)
    city: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80))
    attrs: Mapped[dict[str, Any]] = _attrs()
    seller_type: Mapped[str] = mapped_column(String(10), default="private")
    posted_at: Mapped[datetime] = mapped_column(DateTime)
    source_url: Mapped[str | None] = mapped_column(String(300))
    origin: Mapped[str] = mapped_column(String(10), default="telegram")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    fair_price_uzs: Mapped[float | None] = mapped_column(Float)
    discount_pct: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    type: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(30))
    item_category: Mapped[str | None] = mapped_column(String(10))
    brand: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(120))
    condition: Mapped[str | None] = mapped_column(String(10))
    attrs: Mapped[dict[str, Any]] = _attrs()
    qty: Mapped[float] = mapped_column(Float, default=1)
    unit_price: Mapped[float | None] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    counterparty: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(15), default="manual")
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("deals.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InventoryItem(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    category: Mapped[str] = mapped_column(String(10))
    brand: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120))
    condition: Mapped[str | None] = mapped_column(String(10))
    attrs: Mapped[dict[str, Any]] = _attrs()
    district: Mapped[str | None] = mapped_column(String(80))
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[float] = mapped_column(Float)
    acquired_at: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="in_stock")


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("company_id", "month", "category", name="uq_budget"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    month: Mapped[str] = mapped_column(String(7))
    category: Mapped[str] = mapped_column(String(30))
    planned: Mapped[float] = mapped_column(Float)


class Rfq(Base):
    __tablename__ = "rfqs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    category: Mapped[str] = mapped_column(String(10))
    brand: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120))
    condition: Mapped[str | None] = mapped_column(String(10))
    attrs: Mapped[dict[str, Any]] = _attrs()
    qty: Mapped[int] = mapped_column(Integer)
    target_unit_price: Mapped[float | None] = mapped_column(Float)
    district: Mapped[str | None] = mapped_column(String(80))
    deadline: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("rfq_id", "supplier_id", name="uq_quote"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    unit_price: Mapped[float] = mapped_column(Float)
    qty: Mapped[int] = mapped_column(Integer)
    delivery_days: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Offer(Base):
    __tablename__ = "offers"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(10))
    brand: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120))
    condition: Mapped[str | None] = mapped_column(String(10))
    attrs: Mapped[dict[str, Any]] = _attrs()
    qty: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    district: Mapped[str | None] = mapped_column(String(80))
    commission_split: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Deal(Base):
    __tablename__ = "deals"
    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    rfq_id: Mapped[int | None] = mapped_column(ForeignKey("rfqs.id"))
    quote_id: Mapped[int | None] = mapped_column(ForeignKey("quotes.id"), unique=True)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id"))
    category: Mapped[str] = mapped_column(String(10))
    brand: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(120))
    condition: Mapped[str | None] = mapped_column(String(10))
    attrs: Mapped[dict[str, Any]] = _attrs()
    qty: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("deal_id", "rater_id", name="uq_rating"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"))
    rater_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    ratee_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    category: Mapped[str | None] = mapped_column(String(10))
    type: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10), default="info")
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_telegram: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AlertRead(Base):
    """Per-company read marker for broadcast alerts (company_id IS NULL)."""

    __tablename__ = "alert_reads"
    __table_args__ = (UniqueConstraint("alert_id", "company_id", name="uq_alert_read"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
