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


class PaymentStatus(str, Enum):
    """Verified against the live payment_status enum."""

    created = "created"
    authorized = "authorized"
    captured = "captured"
    failed = "failed"
    refund_pending = "refund_pending"
    partially_refunded = "partially_refunded"
    refunded = "refunded"
    reconciliation_required = "reconciliation_required"


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


def _validate_allergen_codes(codes: list[str] | None) -> list[str]:
    """Allergen codes: the database stores text[] with NO enum or
    check constraint, so the API validates format only and does
    NOT invent a closed code list. Codes are lowercased, stripped,
    unique, and limited to letters, digits, underscores and
    hyphens."""
    if codes is None:
        return []
    import re as _re

    cleaned: list[str] = []
    for code in codes:
        item = code.strip().lower()
        if not item or not _re.match(r"^[a-z0-9_-]+$", item):
            raise ValueError(
                "allergen codes must be lowercase letters, digits, underscores or hyphens"
            )
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


def _validate_listing_windows(
    sale_starts_at: datetime | None,
    sale_ends_at: datetime,
    pickup_starts_at: datetime,
    pickup_ends_at: datetime,
) -> None:
    """Window rules mirroring the database CHECKs exactly:
    sale_ends > sale_starts (when a start is given; otherwise the
    DB default now() applies), pickup_ends > pickup_starts, and
    pickup_ends >= sale_ends. No other ordering is invented."""
    if sale_starts_at is not None and not sale_ends_at > sale_starts_at:
        raise ValueError("sale_ends_at must be after sale_starts_at")
    if not pickup_ends_at > pickup_starts_at:
        raise ValueError("pickup_ends_at must be after pickup_starts_at")
    if not pickup_ends_at >= sale_ends_at:
        raise ValueError("pickup_ends_at must not be before sale_ends_at")


class ListingCreate(BaseModel):
    listing_type: ListingType
    category_id: UUID | None = None
    template_id: UUID | None = None
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    contents_description: str | None = Field(default=None, max_length=5000)
    reference_value: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
    selling_price: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    total_quantity: int = Field(gt=0)
    sale_starts_at: datetime | None = None
    sale_ends_at: datetime
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    prepared_at: datetime | None = None
    best_before_at: datetime | None = None
    allergen_codes: list[str] = Field(default_factory=list)
    dietary_classification: DietaryClassification = DietaryClassification.unknown
    storage_instructions: str | None = Field(default=None, max_length=2000)
    food_safety_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, value: object) -> object:
        if isinstance(value, str):
            return _strip_non_empty(value, "title")
        return value

    @field_validator(
        "description",
        "contents_description",
        "storage_instructions",
        "food_safety_notes",
    )
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return _optional_stripped(value)

    @field_validator("allergen_codes")
    @classmethod
    def _validate_allergens(cls, value: list[str] | None) -> list[str]:
        return _validate_allergen_codes(value)

    @model_validator(mode="after")
    def _validate_listing(self) -> ListingCreate:
        _validate_listing_windows(
            self.sale_starts_at,
            self.sale_ends_at,
            self.pickup_starts_at,
            self.pickup_ends_at,
        )
        # The database only checks best_before >= prepared_at when
        # both are set (CHECK best_before IS NULL OR best_before >=
        # prepared_at); a best_before without prepared_at is allowed
        # by the DB and is not rejected here either.
        if (
            self.prepared_at is not None
            and self.best_before_at is not None
            and not self.best_before_at >= self.prepared_at
        ):
            raise ValueError("best_before_at must not be before prepared_at")
        return self


class ListingUpdate(BaseModel):
    """Partial update. Only columns the authenticated role has an
    UPDATE grant on may appear here: status is handled by the
    dedicated transition endpoints, and store_id, listing_type,
    template_id, currency, created_by and all inventory counters
    are immutable through this API (no UPDATE grant, and no
    endpoint may set them)."""

    category_id: UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    contents_description: str | None = Field(default=None, max_length=5000)
    reference_value: Decimal | None = Field(
        default=None, ge=Decimal("0"), max_digits=12, decimal_places=2
    )
    selling_price: Decimal | None = Field(
        default=None, gt=Decimal("0"), max_digits=12, decimal_places=2
    )
    total_quantity: int | None = Field(default=None, gt=0)
    sale_starts_at: datetime | None = None
    sale_ends_at: datetime | None = None
    pickup_starts_at: datetime | None = None
    pickup_ends_at: datetime | None = None
    prepared_at: datetime | None = None
    best_before_at: datetime | None = None
    allergen_codes: list[str] | None = None
    dietary_classification: DietaryClassification | None = None
    storage_instructions: str | None = Field(default=None, max_length=2000)
    food_safety_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, value: object) -> object:
        if isinstance(value, str):
            return _strip_non_empty(value, "title")
        return value

    @field_validator(
        "description",
        "contents_description",
        "storage_instructions",
        "food_safety_notes",
    )
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return _optional_stripped(value)

    @field_validator("allergen_codes")
    @classmethod
    def _validate_allergens(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _validate_allergen_codes(value)


class ListingResponse(BaseModel):
    id: UUID
    store_id: UUID
    template_id: UUID | None = None
    listing_type: ListingType
    category_id: UUID | None = None
    title: str
    description: str | None = None
    contents_description: str | None = None
    reference_value: Decimal
    selling_price: Decimal
    currency: str = "INR"
    total_quantity: int
    reserved_quantity: int = 0
    sold_quantity: int = 0
    # Same formula as the database-generated column
    # (total - reserved - sold, recalculated by PostgreSQL).
    # The authenticated role has SELECT-only on that column, so
    # the API cannot write it either; this value matches the
    # stored generated value. See architecture.md.
    available_quantity: int
    sale_starts_at: datetime
    sale_ends_at: datetime
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    prepared_at: datetime | None = None
    best_before_at: datetime | None = None
    allergen_codes: list[str] = []
    dietary_classification: DietaryClassification = DietaryClassification.unknown
    storage_instructions: str | None = None
    food_safety_notes: str | None = None
    status: ListingStatus
    published_at: datetime | None = None
    created_by: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CategoryResponse(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    name: str
    slug: str
    display_order: int = 0
    is_active: bool = True


class ListingImageCreate(BaseModel):
    """Register an image for a listing. storage_path is validated
    against the listing-media bucket policy path rule
    (<listing_id>/<file>) and the allowed mime types are enforced
    at upload time by the bucket (jpeg/png/webp, 5 MB); the API
    never trusts a client-supplied URL, only a storage path in
    this bucket. The file itself must already have been uploaded
    to that path by the caller with their own token, which the
    bucket policy authorises only for store operators."""

    storage_path: str = Field(max_length=500)
    alt_text: str | None = Field(default=None, max_length=200)
    display_order: int = Field(default=0, ge=0)

    @field_validator("storage_path", mode="before")
    @classmethod
    def _validate_path(cls, value: object) -> object:
        if isinstance(value, str):
            path = value.strip()
            if not path or path.startswith("/") or ".." in path.split("/"):
                raise ValueError(
                    "storage_path must be a relative path in listing-media"
                )
            return path
        return value

    @field_validator("alt_text")
    @classmethod
    def _strip_alt(cls, value: str | None) -> str | None:
        return _optional_stripped(value)


class ListingImageResponse(BaseModel):
    id: UUID
    listing_id: UUID
    storage_path: str
    alt_text: str | None = None
    display_order: int = 0
    created_at: datetime | None = None


class InventoryAvailabilityResponse(BaseModel):
    listing_id: UUID
    store_id: UUID
    status: ListingStatus
    total_quantity: int
    reserved_quantity: int
    sold_quantity: int
    available_quantity: int
    # Same formula as the generated column (see ListingResponse):
    # the figure the reservation function checks, and the figure
    # merchants should act on.
    sale_ends_at: datetime
    pickup_ends_at: datetime


class MarketplaceSort(str, Enum):
    newest = "newest"
    lowest_price = "lowest_price"
    highest_price = "highest_price"
    ending_soon = "ending_soon"


class PublicStoreSummary(BaseModel):
    """Public store fields only. No contact phone, no merchant
    internals, no onboarding data — those are merchant-only."""

    id: UUID
    name: str
    locality: str | None = None
    city: str
    state: str
    pincode: str
    timezone: str = "Asia/Kolkata"


class PublicListingImage(BaseModel):
    """A storage-path reference in the listing-media bucket, never
    a client-supplied URL. Clients resolve it through the public
    listing-media bucket."""

    storage_path: str
    alt_text: str | None = None
    display_order: int = 0


class PublicListingSummary(BaseModel):
    """Customer-safe listing view. Explicitly excludes created_by,
    created_at, updated_at, template_id, food_safety_notes and
    any merchant-only or payment field — even if the database
    row contains them, this model does not carry them."""

    id: UUID
    store: PublicStoreSummary
    listing_type: ListingType
    category_id: UUID | None = None
    category_name: str | None = None
    title: str
    description: str | None = None
    contents_description: str | None = None
    reference_value: Decimal
    selling_price: Decimal
    currency: str = "INR"
    available_quantity: int
    dietary_classification: DietaryClassification = DietaryClassification.unknown
    allergen_codes: list[str] = []
    storage_instructions: str | None = None
    sale_starts_at: datetime
    sale_ends_at: datetime
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    prepared_at: datetime | None = None
    best_before_at: datetime | None = None
    images: list[PublicListingImage] = []


class MarketplaceListingsResponse(BaseModel):
    items: list[PublicListingSummary] = []
    total: int
    page: int
    page_size: int


class ReservationItem(BaseModel):
    listing_id: UUID
    quantity: int = Field(ge=1, le=20)


class ReservationCreate(BaseModel):
    """Reservation request. No customer id, role, or payment field
    is accepted here: identity comes only from the Supabase Auth
    dependency, and payment is a later milestone (begin_payment_
    checkout is deliberately NOT called here)."""

    store_id: UUID
    items: list[ReservationItem] = Field(min_length=1, max_length=20)
    customer_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _unique_listings(self) -> ReservationCreate:
        ids = [item.listing_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("each listing may appear only once per reservation")
        return self

    @field_validator("customer_note")
    @classmethod
    def _strip_note(cls, value: str | None) -> str | None:
        return _optional_stripped(value)


class ReservationResponse(BaseModel):
    """A reservation, NOT a completed or paid order. status is
    the order status returned by the RPC (pending_payment on a
    new reservation); it must never be presented to the customer
    as payment success or full confirmation. reservation_expires_
    at is None on an idempotent replay, because the RPC replay
    response does not carry an expiry."""

    order_id: UUID
    order_number: str
    status: OrderStatus
    total_amount: Decimal
    currency: str = "INR"
    reservation_expires_at: datetime | None = None
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    idempotent_replay: bool = False


class CheckoutResponse(BaseModel):
    """Safe checkout fields only. The public key_id may go to
    the frontend; the key secret, webhook secret, and any
    internal payment record are never in this response."""

    order_id: UUID
    payment_transaction_id: UUID
    key_id: str
    razorpay_order_id: str
    amount_paise: int
    currency: str = "INR"
    prefill_email: str | None = None


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str = Field(min_length=1, max_length=200)
    razorpay_payment_id: str = Field(min_length=1, max_length=200)
    razorpay_signature: str = Field(min_length=1, max_length=500)


class VerifyPaymentResponse(BaseModel):
    """`verified` means: the checkout signature was verified
    against the order id confirmed from Razorpay's own API, the
    provider payment was fetched server-side and found
    captured for the provider-verified amount, and
    backend_confirm_payment_capture was invoked with that
    amount. It is NOT a claim that the database captured the
    order in all cases: the RPC itself routes an amount
    mismatch or a non-live reservation to reconciliation_
    required instead of capturing, and the order's stored
    status remains authoritative. See docs/architecture.md."""

    order_id: UUID
    payment_transaction_id: UUID
    razorpay_payment_id: str
    verified: bool = True
    amount_paise: int
    currency: str = "INR"


class WebhookResponse(BaseModel):
    received: bool = True
    processed: bool
    reason: str | None = None


class OrderStoreSummary(BaseModel):
    id: UUID
    name: str
    locality: str | None = None
    city: str
    state: str
    pincode: str


class OrderStoreDetail(BaseModel):
    id: UUID
    name: str
    address_line_1: str
    address_line_2: str | None = None
    locality: str | None = None
    city: str
    state: str
    pincode: str
    contact_phone: str | None = None
    pickup_instructions: str | None = None


class OrderItemPreview(BaseModel):
    title: str
    quantity: int


class OrderSummary(BaseModel):
    """List-view order. No internal fields: no request_
    idempotency_key, no request_hash, no customer_id (the
    caller is the customer), no gateway ids, no raw notes."""

    id: UUID
    order_number: str
    status: OrderStatus
    payment_status: PaymentStatus
    total_amount: Decimal
    currency: str = "INR"
    created_at: datetime
    updated_at: datetime
    store: OrderStoreSummary
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    item_count: int
    items_preview: list[OrderItemPreview] = []


class OrderListResponse(BaseModel):
    items: list[OrderSummary] = []
    total: int
    page: int
    page_size: int


class OrderItemResponse(BaseModel):
    """Item details come from the order_items SNAPSHOT (title,
    description, prices as recorded at reservation time), not
    from the live listing — so a later listing edit cannot
    rewrite what the customer ordered. The image, where one
    exists, is the listing's current public image and may be
    absent if the listing is no longer public."""

    listing_id: UUID
    listing_type: ListingType
    title: str
    description: str | None = None
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    reference_value: Decimal
    dietary_classification: DietaryClassification = DietaryClassification.unknown
    allergen_codes: list[str] = []
    image_path: str | None = None


class OrderPaymentSummary(BaseModel):
    """Payment status only — no gateway secrets, signatures,
    provider payloads, or private transaction fields. The
    private payment_transactions table is never queried.
    amount_paid is the order total when payment_status is
    captured, otherwise 0: capture is the only state in
    which money is confirmed taken."""

    status: PaymentStatus
    gateway_label: str | None = None
    amount_paid: Decimal
    paid_at: datetime | None = None


class OrderTimelineEvent(BaseModel):
    """One REAL order_status_events row, nothing invented.
    actor_user_id is never exposed; actor_type (customer /
    merchant / admin / system) is safe to show. If no events
    exist, the timeline is empty and the current status
    fields are the only state shown."""

    status: OrderStatus
    label: str
    occurred_at: datetime
    actor_type: str


class OrderDetail(BaseModel):
    id: UUID
    order_number: str
    status: OrderStatus
    payment: OrderPaymentSummary
    subtotal_amount: Decimal
    discount_amount: Decimal
    platform_fee_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str = "INR"
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None
    collected_at: datetime | None = None
    cancelled_at: datetime | None = None
    customer_note: str | None = None
    cancellation_reason: str | None = None
    store: OrderStoreDetail
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    reservation_expires_at: datetime | None = None
    # Pickup availability, derived from the order row (status
    # confirmed/ready_for_pickup and within pickup_ends + 30
    # minutes). It is NOT a database field, and it does not
    # say whether a token was issued — tokens are one-time,
    # plaintext-only at issuance, and cannot be read back.
    # A collected, cancelled, or expired order is never
    # pickup-available.
    pickup_available: bool = False
    items: list[OrderItemResponse] = []
    timeline: list[OrderTimelineEvent] = []


class MerchantOrderSummary(BaseModel):
    """Merchant list view. No customer personal information:
    no customer_id, email, phone, or address — profiles are
    own-only by RLS, so the API cannot (and must not) surface
    customer contact details. Fulfilment runs on the order
    number, items, and pickup window."""

    id: UUID
    order_number: str
    status: OrderStatus
    payment_status: PaymentStatus
    total_amount: Decimal
    currency: str = "INR"
    created_at: datetime
    store: OrderStoreSummary
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    item_count: int
    items_preview: list[OrderItemPreview] = []


class MerchantOrderListResponse(BaseModel):
    items: list[MerchantOrderSummary] = []
    total: int
    page: int
    page_size: int


class MerchantOrderQueueSummary(BaseModel):
    """Counts from real, authorized-store orders only. Paid
    means payment_status captured; awaiting_payment means
    order status pending_payment; upcoming_pickups means
    confirmed or ready_for_pickup with a pickup window not
    yet started; completed means collected (the database's
    completion state — there is no separate 'completed'
    status). Ready-for-pickup is NOT claimed for confirmed
    orders: confirmed means paid, not yet ready."""

    total: int
    awaiting_payment: int
    paid: int
    upcoming_pickups: int
    completed: int
    cancelled_or_expired: int


class PickupTokenResponse(BaseModel):
    """One-time pickup token, returned ONLY at issuance.
    The database stores only the SHA256 hash, so the
    plaintext token cannot be retrieved later — a lost
    token means issuing a fresh one (which invalidates the
    old one). pickup_token_id is deliberately NOT returned:
    the frontend needs the token, not an internal id."""

    order_id: UUID
    order_number: str
    pickup_token: str
    qr_payload: str
    expires_at: datetime
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    store_name: str
    pickup_instructions: str | None = None


class PickupVerifyRequest(BaseModel):
    """store_id is required by the verify RPC's signature and
    is the store where the customer is standing. It is NOT
    trusted as authority: the database checks that the
    caller is authorized for that store AND that the
    token's order belongs to that store. A wrong store_id
    fails; it can never grant access to another store."""

    store_id: UUID
    pickup_token: str = Field(min_length=1, max_length=200)


class PickupVerifyResponse(BaseModel):
    order_id: UUID
    order_number: str
    store_name: str
    status: OrderStatus
    collected_at: datetime
    items: list[OrderItemPreview] = []


class ReviewCreateRequest(BaseModel):
    # Rating is an integer 1-5 (the database CHECK enforces
    # the same range; Pydantic rejects non-integers and
    # out-of-range values before any database call).
    rating: int = Field(ge=1, le=5)
    # Optional written feedback, max 1000 chars.
    # Whitespace-only text is stored as no comment.
    comment: str | None = Field(default=None, max_length=1000)


class ReviewResponse(BaseModel):
    """A customer's own review. customer_id is never
    returned — the caller is the owner by construction."""

    id: UUID
    order_number: str
    store_name: str
    rating: int
    comment: str | None = None
    moderation_status: str
    created_at: datetime


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    page: int
    page_size: int


class PublicReviewResponse(BaseModel):
    """Public review: rating, text, date only. No customer
    id, name, email, phone, address, order id, payment
    data, or moderation notes. There is no customer
    display label: profiles are own-only by RLS, so no
    public customer name exists in the database contract
    to show, and none is invented."""

    id: UUID
    rating: int
    comment: str | None = None
    created_at: datetime


class PublicReviewListResponse(BaseModel):
    items: list[PublicReviewResponse]
    total: int
    page: int
    page_size: int
    store_name: str


class StoreRatingSummary(BaseModel):
    """Aggregates over PUBLIC (visible) reviews only, so
    the summary and the public list always agree. Average
    is rounded half-up to 2 decimal places; a store with
    no public reviews has average None, never a
    fabricated 5.0."""

    store_id: UUID
    store_name: str
    average_rating: float | None = None
    total_reviews: int
    five_star: int
    four_star: int
    three_star: int
    two_star: int
    one_star: int


class DashboardPeriod(BaseModel):
    """Half-open reporting period [from, to): an order
    created exactly at `to` belongs to the next period,
    never to both. Either bound may be null (unbounded)."""

    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None

    model_config = {"populate_by_name": True}


class DashboardStoreContext(BaseModel):
    store_id: UUID | None = None
    store_name: str | None = None
    store_status: str | None = None
    timezone: str
    # True/False when today's hours row exists with times,
    # None when no hours row or no times are stored (unknown,
    # not "closed").
    open_now: bool | None = None
    store_count: int = 1


class DashboardOrderMetrics(BaseModel):
    total_orders: int
    paid_orders: int
    awaiting_payment_orders: int
    collected_orders: int
    cancelled_orders: int
    expired_orders: int
    refund_orders: int
    # Sum of total_amount over orders whose payment_status
    # is captured ONLY. Pending, authorized-only, failed,
    # refunded, and reconciliation states never count.
    # This is NOT merchant earnings, settlement, or payout
    # revenue: platform fees, refunds, and payouts are not
    # deducted or included, because the order row carries
    # no refund amounts to net against. String, not float,
    # so money stays exact.
    captured_order_value: str
    currency: str = "INR"


class DashboardInventoryMetrics(BaseModel):
    total_listings: int
    published_listings: int
    draft_listings: int
    paused_listings: int
    sold_out_listings: int
    # Sums of the database-generated available_quantity
    # (total - reserved - sold), read, never recomputed
    # for business decisions and never written.
    total_available_units: int
    total_reserved_units: int
    total_sold_units: int


class DashboardPickupMetrics(BaseModel):
    upcoming_pickups: int
    in_window_pickups: int
    completed_collections: int
    # Orders whose pickup window has closed (past
    # pickup_ends_at + 30 minutes) without collection.
    # Labelled window_expired, NOT "missed": the database
    # records no no-show event, so a missed pickup is
    # never asserted.
    window_expired_pickups: int


class DashboardRatingMetrics(BaseModel):
    average_rating: float | None = None
    total_visible_reviews: int
    five_star: int
    four_star: int
    three_star: int
    two_star: int
    one_star: int


class DashboardOverview(BaseModel):
    period: DashboardPeriod
    store: DashboardStoreContext
    orders: DashboardOrderMetrics
    inventory: DashboardInventoryMetrics
    pickups: DashboardPickupMetrics
    ratings: DashboardRatingMetrics


class SalesBucket(BaseModel):
    period_start: str
    total_orders: int
    captured_orders: int
    pending_payment_orders: int
    failed_payment_orders: int
    collected_orders: int
    cancelled_or_expired_orders: int
    captured_order_value: str
    currency: str = "INR"


class SalesAnalytics(BaseModel):
    period: DashboardPeriod
    store: DashboardStoreContext
    group_by: str
    reporting_timezone: str
    buckets: list[SalesBucket]
    totals: SalesBucket


class InventoryListingSummary(BaseModel):
    listing_id: UUID
    title: str
    status: str
    available_quantity: int
    reserved_quantity: int
    sold_quantity: int
    sale_ends_at: datetime | None = None


class InventoryDashboard(BaseModel):
    period: DashboardPeriod
    store: DashboardStoreContext
    summary: DashboardInventoryMetrics
    # Only populated when low_stock_threshold is given:
    # listings whose generated available_quantity is at or
    # below the threshold. The threshold is a reporting
    # filter, not a business definition of low stock, and
    # it changes no listing status or quantity.
    low_stock_listings: list[InventoryListingSummary] = []


class PickupOrderSummary(BaseModel):
    order_number: str
    status: str
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    category: str
    total_quantity: int


class PickupDashboard(BaseModel):
    period: DashboardPeriod
    store: DashboardStoreContext
    counts: DashboardPickupMetrics
    orders: list[PickupOrderSummary]


class StoreComparisonRow(BaseModel):
    store_id: UUID
    store_name: str
    store_status: str
    total_orders: int
    captured_order_value: str
    collected_orders: int
    active_listings: int
    available_units: int
    average_rating: float | None = None
    review_count: int


class StoreComparison(BaseModel):
    period: DashboardPeriod
    stores: list[StoreComparisonRow]


class AdminMerchantSummary(BaseModel):
    id: UUID
    legal_name: str
    display_name: str
    business_type: str
    status: str
    verification_status: str
    store_count: int
    created_at: datetime
    approved_at: datetime | None = None


class AdminMerchantDetail(BaseModel):
    id: UUID
    legal_name: str
    display_name: str
    business_type: str
    business_email: str | None = None
    business_phone: str | None = None
    status: str
    verification_status: str
    onboarding_notes: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    stores: list[AdminStoreSummary] = []


class AdminStoreSummary(BaseModel):
    id: UUID
    merchant_id: UUID
    merchant_name: str
    name: str
    status: str
    city: str
    pincode: str
    listing_count: int = 0
    order_count: int = 0
    created_at: datetime | None = None


class AdminStoreDetail(BaseModel):
    id: UUID
    merchant_id: UUID
    merchant_name: str
    name: str
    status: str
    city: str
    state: str
    pincode: str
    address_line_1: str
    locality: str | None = None
    timezone: str
    hours: list[dict] = []
    listing_count: int = 0
    order_count: int = 0
    created_at: datetime | None = None


class AdminMerchantReviewRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    review_notes: str | None = Field(default=None, max_length=1000)


class AdminMerchantReviewResponse(BaseModel):
    merchant_id: UUID
    status: str
    verification_status: str


class AdminStoreReviewRequest(BaseModel):
    activate: bool
    reason: str | None = Field(default=None, max_length=1000)


class AdminStoreReviewResponse(BaseModel):
    store_id: UUID
    activated: bool


class AdminListingSummary(BaseModel):
    id: UUID
    title: str
    store_id: UUID
    store_name: str
    merchant_name: str
    selling_price: str
    currency: str
    total_quantity: int
    reserved_quantity: int
    sold_quantity: int
    available_quantity: int
    status: str
    sale_starts_at: datetime
    sale_ends_at: datetime
    created_at: datetime
    updated_at: datetime


class AdminOrderSummary(BaseModel):
    id: UUID
    order_number: str
    store_id: UUID
    store_name: str
    merchant_name: str
    status: str
    payment_status: str
    total_amount: str
    currency: str
    created_at: datetime


class AdminDashboard(BaseModel):
    merchants_total: int
    merchants_approved: int
    merchants_pending_review: int
    stores_total: int
    stores_active: int
    stores_draft: int
    stores_inactive: int
    stores_suspended: int
    listings_total: int
    listings_published: int
    listings_draft: int
    listings_paused: int
    listings_sold_out: int
    listings_expired: int
    orders_total: int
    orders_pending_payment: int
    orders_confirmed: int
    orders_ready_for_pickup: int
    orders_collected: int
    orders_cancelled_or_expired: int
    captured_payment_count: int
    # Sum of order total_amount where payment_status is
    # captured only. NOT earnings, NOT net revenue.
    captured_order_value: str
    failed_payment_count: int
    pending_payment_count: int
    reconciliation_required_count: int
    refund_pending_count: int
    visible_reviews_total: int
    average_visible_rating: float | None = None
    recent_orders: list[AdminOrderSummary] = []


class AdminOrderItemSummary(BaseModel):
    title: str
    quantity: int
    unit_price: str
    line_total: str


class AdminOrderEventSummary(BaseModel):
    from_status: str | None = None
    to_status: str
    actor_type: str
    reason: str | None = None
    created_at: datetime


class AdminOrderDetail(BaseModel):
    id: UUID
    order_number: str
    store_id: UUID
    store_name: str
    merchant_name: str
    status: str
    payment_status: str
    total_amount: str
    currency: str
    pickup_starts_at: datetime
    pickup_ends_at: datetime
    collected_at: datetime | None = None
    customer_note: str | None = None
    items: list[AdminOrderItemSummary] = []
    events: list[AdminOrderEventSummary] = []
    created_at: datetime


class AdminPaymentException(BaseModel):
    """Payment visibility comes from ORDERS, not from
    private.payment_transactions (inaccessible by design).
    No gateway ids, signatures, or provider payloads."""

    order_id: UUID
    order_number: str
    store_name: str
    merchant_name: str
    amount: str
    currency: str
    payment_status: str
    order_status: str
    created_at: datetime
    updated_at: datetime


class AdminReviewRow(BaseModel):
    """Admin review visibility is limited by the reviews
    SELECT policy (visible or own): hidden and
    under_review reviews are NOT visible to platform
    admins through the user-context client, so this list
    shows visible reviews in practice."""

    id: UUID
    store_id: UUID
    store_name: str
    rating: int
    comment: str | None = None
    moderation_status: str
    created_at: datetime


class AdminActivityEvent(BaseModel):
    """Only recorded order_status_events are returned.
    private.audit_logs (merchant/store review actions)
    and private.pickup_events / webhook events are NOT
    readable through the API by design, so they are not
    fabricated here."""

    order_number: str
    from_status: str | None = None
    to_status: str
    actor_type: str
    reason: str | None = None
    created_at: datetime


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
