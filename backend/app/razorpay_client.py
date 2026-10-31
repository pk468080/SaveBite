"""Razorpay API client (Milestone 6).

Server-side only, using HTTP Basic Auth (key_id as username,
key_secret as password) against https://api.razorpay.com/v1.
No Razorpay SDK dependency is added: the three calls this
milestone needs (create order, fetch payment, fetch order) are
plain HTTPS, and httpx is already a pinned runtime dependency.

Security rules for this module:
- The key secret is used only in the Authorization header of
  these calls. It is never logged, never returned, and never
  included in an error message or response body.
- Provider responses are returned to the caller as data, never
  logged wholesale: they can contain customer contact details.
- Timeouts are bounded (15s). A timeout or HTTP error becomes
  a 502 BadGatewayError, never a stack trace to the customer,
  and never a claim about whether the provider-side operation
  happened — callers must treat a timeout after order creation
  as ambiguous (see the payments router).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.errors import BadGatewayError

_BASE_URL = "https://api.razorpay.com/v1"
_TIMEOUT_SECONDS = 15.0


class RazorpayClient:
    def __init__(
        self,
        key_id: str,
        key_secret: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._client = client

    def _auth(self) -> tuple[str, str]:
        return (self._key_id, self._key_secret)

    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = await self._client.request(method, path, json=json)
            else:
                async with httpx.AsyncClient(
                    base_url=_BASE_URL,
                    auth=self._auth(),
                    timeout=_TIMEOUT_SECONDS,
                ) as client:
                    response = await client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise BadGatewayError("Payment provider is unavailable") from exc
        if response.status_code >= 400:
            raise BadGatewayError("Payment provider request failed")
        data = response.json()
        if not isinstance(data, dict):
            raise BadGatewayError("Payment provider returned an unexpected response")
        return data

    async def create_order(
        self,
        amount_paise: int,
        currency: str,
        notes: dict[str, str],
    ) -> dict[str, Any]:
        """Create a Razorpay order. `notes` carries the SaveBite
        payment-transaction id and order id so that a later
        verification or webhook can be tied back to the SaveBite
        transaction through Razorpay's own records (see the
        payments router and the proposed lookup RPC in
        docs/architecture.md)."""
        return await self._request(
            "POST",
            "/orders",
            json={
                "amount": amount_paise,
                "currency": currency,
                "payment_capture": 1,
                "notes": notes,
            },
        )

    async def get_payment(self, payment_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/payments/{payment_id}")

    async def get_order(self, order_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/orders/{order_id}")
