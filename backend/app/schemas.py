"""Pydantic v2 request/response schemas.

Enums mirror the live database enums from Milestone 1 exactly — do not
add values here without an approved schema change. Money uses Decimal
(NUMERIC in the database); never use binary floating point for INR
arithmetic in service code, even though JSON transport serialises
Decimal as a number here.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ListingType(str, Enum):
    surprise_bag = "surprise_bag"
    individual_item = "individual_item"


class ListingStatus(str, Enum):
    draft = "draft"
    scheduled = "scheduled"
    active = "active"
    paused = "paused"
    sold_out = "sold_out"
    expired = "expired"
    cancelled = "cancelled"


class DietaryClassification(str, Enum):
    vegetarian = "vegetarian"
    non_vegetarian = "non_vegetarian"
    vegan = "vegan"
    egg = "egg"
    unknown = "unknown"


class OrderStatus(str, Enum):
    pending_payment = "pending_payment"
    confirmed = "confirmed"
    ready_for_pickup = "ready_for_pickup"
    collected = "collected"
    expired = "expired"
    cancelled = "cancelled"
    refund_pending = "refund_pending"
    refunded = "refunded"


class MerchantStatus(str, Enum):
    pending_review = "pending_review"
    additional_information_required = "additional_information_required"
    approved = "approved"
    rejected = "rejected"
    suspended = "suspended"


class PlatformRole(str, Enum):
    support_agent = "support_agent"
    finance_admin = "finance_admin"
    compliance_admin = "compliance_admin"
    operations_admin = "operations_admin"
    super_admin = "super_admin"


class MerchantMemberRole(str, Enum):
    owner = "owner"
    admin = "admin"
    store_manager = "store_manager"
    inventory_manager = "inventory_manager"
    pickup_operator = "pickup_operator"
    finance_viewer = "finance_viewer"


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    service: str
    version: str
    checks: dict[str, str]


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str = ""


class ErrorResponse(BaseModel):
    error: ErrorDetail


class AuthenticatedUser(BaseModel):
    """Identity resolved from Supabase Auth. The token is carried only
    for building the user-context Supabase client and is excluded
    from every serialised response."""

    id: UUID
    email: str | None = None
    token: str = Field(default="", exclude=True)


class MeResponse(BaseModel):
    id: UUID
    email: str | None = None
    platform_roles: list[PlatformRole] = []


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class MoneyAmount(BaseModel):
    """An INR amount in rupees, as Decimal. The database stores NUMERIC;
    service code must keep Decimal through calculations and only format
    for display at the edge."""

    amount: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
