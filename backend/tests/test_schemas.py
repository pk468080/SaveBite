from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import (
    ListingType,
    MoneyAmount,
    OrderStatus,
    PaginationParams,
)


def test_enums_match_database_contract():
    assert ListingType.surprise_bag.value == "surprise_bag"
    assert ListingType.individual_item.value == "individual_item"
    assert OrderStatus.pending_payment.value == "pending_payment"
    assert OrderStatus.collected.value == "collected"


def test_pagination_bounds():
    assert PaginationParams().page_size == 20
    with pytest.raises(ValidationError):
        PaginationParams(page=0)
    with pytest.raises(ValidationError):
        PaginationParams(page_size=101)


def test_money_amount_uses_decimal_and_rejects_negative():
    amount = MoneyAmount(amount=Decimal("199.50"))
    assert amount.amount == Decimal("199.50")
    assert amount.currency == "INR"
    with pytest.raises(ValidationError):
        MoneyAmount(amount=Decimal("-1.00"))
    with pytest.raises(ValidationError):
        MoneyAmount(amount=Decimal("1.00"), currency="inr")
