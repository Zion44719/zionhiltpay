"""
Live bank list and account-name resolution via Paystack.
Written against Paystack's documented endpoints:
  GET /bank?country=nigeria&use_cursor=true&perPage=..&next=..   (cursor-paginated list)
  GET /bank/resolve?account_number=..&bank_code=..               -> data.account_name
Only reads: it never moves money.
"""
import time

import httpx

from app.core.config import settings
from app.services.banks import AccountNotFound, ProviderUnavailable

_CACHE_SECONDS = 6 * 3600


class PaystackBankProvider:
    mode = "paystack"

    def __init__(self):
        self._banks: list[dict] = []
        self._loaded_at = 0.0

    def _client(self) -> httpx.AsyncClient:
        if not settings.PAYSTACK_SECRET_KEY:
            raise ProviderUnavailable("PAYSTACK_SECRET_KEY is not set")
        return httpx.AsyncClient(
            base_url=settings.PAYSTACK_BASE_URL.rstrip("/"), timeout=15.0,
            headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}", "Accept": "application/json"},
        )

    async def list_banks(self) -> list[dict]:
        if self._banks and time.time() - self._loaded_at < _CACHE_SECONDS:
            return self._banks
        banks: list[dict] = []
        cursor = None
        try:
            async with self._client() as c:
                for _ in range(30):                                   # hard stop: never loop forever
                    params = {"country": "nigeria", "use_cursor": "true", "perPage": "100"}
                    if cursor:
                        params["next"] = cursor
                    r = await c.get("/bank", params=params)
                    r.raise_for_status()
                    body = r.json()
                    for b in body.get("data") or []:
                        if b.get("active", True) and b.get("currency", "NGN") == "NGN" and b.get("code") and b.get("name"):
                            banks.append({"name": b["name"], "code": str(b["code"])})
                    cursor = (body.get("meta") or {}).get("next")
                    if not cursor:
                        break
        except (httpx.HTTPError, ValueError) as exc:
            if self._banks:
                return self._banks                                    # stale list beats no list
            raise ProviderUnavailable(f"Could not load the bank list: {exc}") from exc
        if not banks:
            raise ProviderUnavailable("The provider returned no banks")
        seen, unique = set(), []
        for b in sorted(banks, key=lambda x: x["name"].lower()):
            if b["code"] not in seen:
                seen.add(b["code"]); unique.append(b)
        self._banks, self._loaded_at = unique, time.time()
        return unique

    async def resolve_account(self, bank_code: str, account_number: str) -> dict:
        try:
            async with self._client() as c:
                r = await c.get("/bank/resolve", params={"account_number": account_number, "bank_code": bank_code})
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Account lookup failed: {exc}") from exc
        if r.status_code in (400, 404, 422):
            raise AccountNotFound("Could not resolve this account")
        if r.status_code in (401, 403):
            raise ProviderUnavailable("The bank lookup service rejected our credentials")
        if r.status_code >= 400:
            raise ProviderUnavailable(f"Bank lookup returned HTTP {r.status_code}")
        data = (r.json() or {}).get("data") or {}
        name = (data.get("account_name") or "").strip()
        if not name:
            raise AccountNotFound("Could not resolve this account")
        return {"account_number": account_number, "account_name": name, "bank_code": bank_code}
