"""Pydantic v2 request/response schemas.

Enums mirror the live database enums from Milestone 1 exactly — do not
add values here without an approved schema change. Money uses Decimal
(NUMERIC in the database); never use binary floating point for INR
arithmetic in service code, even though JSON transport serialises
Decimal as a number here.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


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


class MerchantBusinessType(str, Enum):
    """Exact merchant_business_type enum from the live database.
    Do not add values without an approved schema change."""

    restaurant = "restaurant"
    bakery = "bakery"
    cafe = "cafe"
    supermarket = "supermarket"
    hotel = "hotel"
    cloud_kitchen = "cloud_kitchen"
    grocery_store = "grocery_store"
    food_manufacturer = "food_manufacturer"
    sweet_shop = "sweet_shop"
    other = "other"


class MerchantStatusDetail(str, Enum):
    """Verification status is separate from merchant_status in the DB;
    kept here for completeness of MerchantResponse."""

    pending = "pending"
    under_review = "under_review"
    verified = "verified"
    rejected = "rejected"
    expired = "expired"


class StoreStatus(str, Enum):
    draft = "draft"
    active = "active"
    inactive = "inactive"
    suspended = "suspended"


def _strip_non_empty(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    return stripped


def _optional_stripped(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _validate_indian_mobile(value: str | None) -> str | None:
    """Indian mobile format: 10 digits starting 6-9, optionally with
    a +91 prefix and spaces/hyphens. Returns the digits with +91
    preserved when given, otherwise the plain 10 digits."""
    if value is None:
        return None
    cleaned = value.replace(" ", "").replace("-", "")
    digits = cleaned[11:] if cleaned.startswith("+91") else cleaned
    if cleaned.startswith("+91"):
        if len(cleaned) != 13 or not digits.isdigit() or digits[0] not in "6789":
            raise ValueError("phone must be a valid Indian mobile number")
        return cleaned
    if len(cleaned) != 10 or not cleaned.isdigit() or cleaned[0] not in "6789":
        raise ValueError("phone must be a valid Indian mobile number")
    return cleaned


class MerchantApplicationCreate(BaseModel):
    legal_name: str = Field(max_length=200)
    display_name: str = Field(max_length=200)
    business_type: MerchantBusinessType
    # Optional in the database (RPC defaults NULL) and optional here:
    # the API does not invent a stricter requirement than the DB.
    # When supplied, format is validated.
    business_email: str | None = Field(default=None, max_length=254)
    business_phone: str | None = Field(default=None, max_length=20)

    @field_validator("legal_name", "display_name", mode="before")
    @classmethod
    def _strip_names(cls, value: object) -> object:
        if isinstance(value, str):
            return _strip_non_empty(value, "business name")
        return value

    @field_validator("business_email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        email = value.strip()
        # Simple format check only; no email-validator dependency.
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("business_email must be a valid email address")
        if any(ch.isspace() for ch in email) or email.count("@") != 1:
            raise ValueError("business_email must be a valid email address")
        return email

    @field_validator("business_phone")
    @classmethod
    def _validate_phone(cls, value: str | None) -> str | None:
        return _validate_indian_mobile(value)


class MerchantResponse(BaseModel):
    id: UUID
    legal_name: str
    display_name: str
    business_type: MerchantBusinessType
    business_email: str | None = None
    business_phone: str | None = None
    status: MerchantStatus
    verification_status: MerchantStatusDetail
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StoreCreate(BaseModel):
    name: str = Field(max_length=200)
    slug: str = Field(max_length=200)
    address_line_1: str = Field(max_length=500)
    address_line_2: str | None = Field(default=None, max_length=500)
    locality: str | None = Field(default=None, max_length=200)
    city: str = Field(max_length=200)
    state: str = Field(max_length=200)
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    contact_phone: str | None = Field(default=None, max_length=20)
    pickup_instructions: str | None = Field(default=None, max_length=1000)

    @field_validator("name", "address_line_1", "city", "state", mode="before")
    @classmethod
    def _strip_required(cls, value: object) -> object:
        if isinstance(value, str):
            return _strip_non_empty(value, "field")
        return value

    @field_validator("slug", mode="before")
    @classmethod
    def _normalise_slug(cls, value: object) -> object:
        if isinstance(value, str):
            slug = value.strip().lower()
            if not slug:
                raise ValueError("slug must not be empty")
            import re as _re

            if not _re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
                raise ValueError("slug must be lowercase letters, digits and hyphens")
            return slug
        return value

    @field_validator("address_line_2", "locality", "pickup_instructions")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return _optional_stripped(value)

    @field_validator("contact_phone")
    @classmethod
    def _validate_contact_phone(cls, value: str | None) -> str | None:
        return _validate_indian_mobile(value)

    @model_validator(mode="after")
    def _lat_long_together(self) -> StoreCreate:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "latitude and longitude must both be supplied or both be omitted"
            )
        return self


class StoreResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    name: str
    slug: str
    address_line_1: str
    address_line_2: str | None = None
    locality: str | None = None
    city: str
    state: str
    pincode: str
    country_code: str = "IN"
    contact_phone: str | None = None
    pickup_instructions: str | None = None
    timezone: str = "Asia/Kolkata"
    status: StoreStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StoreHoursEntry(BaseModel):
    weekday: int = Field(ge=0, le=6)
    is_closed: bool = False
    opens_at: time | None = None
    closes_at: time | None = None

    @model_validator(mode="after")
    def _closed_rules(self) -> StoreHoursEntry:
        if self.is_closed:
            if self.opens_at is not None or self.closes_at is not None:
                raise ValueError("closed days must not have opening or closing times")
        else:
            if self.opens_at is None or self.closes_at is None:
                raise ValueError("open days require both opens_at and closes_at")
            if self.opens_at >= self.closes_at:
                raise ValueError("opens_at must be before closes_at")
        return self


class StoreHoursUpdate(BaseModel):
    hours: list[StoreHoursEntry] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def _unique_weekdays(self) -> StoreHoursUpdate:
        weekdays = [entry.weekday for entry in self.hours]
        if len(set(weekdays)) != len(weekdays):
            raise ValueError("one entry per weekday is allowed")
        return self


class StoreHoursResponse(BaseModel):
    store_id: UUID
    hours: list[StoreHoursEntry] = []


class StoreHoursUpdateResponse(BaseModel):
    store_id: UUID
    processed: int
    hours: list[StoreHoursEntry] = []


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
