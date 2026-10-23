"""
Bank transfers, tier limits, tier upgrades, profile photos, loans and ledger concurrency, against a REAL Postgres.
Skipped unless TEST_DATABASE_URL is set (see test_agent_integration.py).
"""
import asyncio
import io
import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_identity_integration import env, _payload, _verify, _login  # noqa: E402,F401  (shared fixture + helpers)

TEST_DB = os.environ.get("TEST_DATABASE_URL")
_RUN_START = datetime.now(timezone.utc)   # accounts created before this test run are not ours to judge
pytestmark = pytest.mark.skipif(not TEST_DB, reason="set TEST_DATABASE_URL to run DB integration tests")


# ------------------------------------------------------------------ helpers
async def make_user(c, Session, *, tier=1, deposit=0, pin="7392", tag="u"):
    from sqlalchemy import text
    p = _payload(full_name=f"{tag.title()} Tester")
    reg = (await c.post("/api/auth/register", json=p)).json()
    await _verify(Session, p["email"])
    h = {"Authorization": "Bearer " + (await _login(c, p["username"])).json()["access_token"]}
    assert (await c.post("/api/auth/pin/set", json={"pin": pin, "confirm_pin": pin}, headers=h)).status_code == 200
    if tier != 1:
        async with Session() as s:
            await s.execute(text("UPDATE users SET account_tier=:t WHERE id=:i"), {"t": tier, "i": reg["user_id"]}); await s.commit()
    if deposit:
        assert (await c.post("/api/wallet/deposit", json={"amount": deposit}, headers=h)).status_code == 201
    return {"h": h, "id": reg["user_id"], "acct": reg["account_number"], "username": p["username"], "email": p["email"], "pin": pin, "payload": p}


async def make_staff(c, Session, role):
    from app.core.security import hash_password
    from app.core import identity as idt
    from app.models.user import User
    tag = uuid.uuid4().hex[:8]
    async with Session() as s:
        u = User(full_name="Staff Member", username=f"staff_{tag}", email=f"staff{tag}@example.com",
                 phone_number="+23481" + str(random.randint(10**7, 10**8 - 1)), password_hash=hash_password("StrongPass123"),
                 role=role, email_verified=True, account_number=idt.generate_account_number(), kyc_status="verified", kyc_level=2, account_tier=3)
        s.add(u); await s.commit()
        name, uid = u.username, str(u.id)
    h = {"Authorization": "Bearer " + (await _login(c, name)).json()["access_token"]}
    return {"h": h, "id": uid}


def image_bytes(fmt="PNG", size=(900, 600), exif=False, color=(200, 80, 40)):
    from PIL import Image
    im = Image.new("RGB", size, color)
    out = io.BytesIO()
    if exif:
        ex = Image.Exif(); ex[0x010F] = "SecretPhoneMaker"; ex[0x0112] = 1
        im.save(out, format=fmt, exif=ex)
    else:
        im.save(out, format=fmt)
    return out.getvalue()


async def balances(c, u):
    return (await c.get("/api/wallet/balance", headers=u["h"])).json()


_DRIFT_BASELINE: dict = {}          # platform-account id -> (balance - ledger sum) when this module started


@pytest.fixture(scope="module", autouse=True)
def _record_drift_baseline():
    """A long-lived test database may carry old damage. We only judge drift that appears DURING this run."""
    if not TEST_DB:
        return

    async def go():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        engine = create_async_engine(TEST_DB, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                rows = (await conn.execute(text(_DRIFT_SQL))).all()
            _DRIFT_BASELINE.update({str(r[0]): r[3] for r in rows if r[1] is None})
        finally:
            await engine.dispose()
    asyncio.run(go())


_DRIFT_SQL = ("SELECT a.id, a.user_id, a.account_type::text, a.balance - COALESCE(l.s, 0), a.created_at FROM accounts a LEFT JOIN "
              "(SELECT account_id, SUM(CASE WHEN direction='C' THEN amount ELSE -amount END) s FROM ledger_entries GROUP BY account_id) l "
              "ON l.account_id = a.id")


async def assert_ledger_reconciles(Session):
    """Double-entry invariants for everything that happened during this test run:
    (1) no account's stored balance has drifted away from the sum of its ledger entries
        (platform accounts are compared with their starting drift; accounts created in this run must be exact), and
    (2) every transaction created in this run nets to exactly zero."""
    from decimal import Decimal
    from sqlalchemy import text
    async with Session() as s:
        rows = (await s.execute(text(_DRIFT_SQL))).all()
        bad_txns = (await s.execute(text(
            "SELECT t.reference, SUM(CASE WHEN le.direction='C' THEN le.amount ELSE -le.amount END) FROM transactions t "
            "JOIN ledger_entries le ON le.transaction_id=t.id WHERE t.created_at >= :t GROUP BY t.id, t.reference "
            "HAVING SUM(CASE WHEN le.direction='C' THEN le.amount ELSE -le.amount END) <> 0"), {"t": _RUN_START})).all()
    bad_accounts = []
    for acct_id, user_id, kind, drift, created in rows:
        if user_id is None:
            expected = _DRIFT_BASELINE.get(str(acct_id), Decimal("0"))
        elif created >= _RUN_START:
            expected = Decimal("0")
        else:
            continue                                       # a customer account from an earlier run: not ours to judge
        if drift != expected:
            bad_accounts.append((kind, str(drift - expected)))
    assert not bad_accounts, f"accounts that drifted away from their ledger entries during this run (account, drift): {bad_accounts[:3]}"
    assert not bad_txns, f"transactions that do not balance to zero: {bad_txns[:3]}"


@pytest.fixture(autouse=True)
def _reset_provider():
    from app.services.banks import set_bank_provider
    set_bank_provider(None)
    yield
    set_bank_provider(None)


# ------------------------------------------------------------------ ledger concurrency
@pytest.mark.asyncio
async def test_concurrent_deposits_and_the_ledger_still_reconciles(env):
    """Many customers depositing at once all touch the shared platform account: a read-then-write balance update
    would silently lose some of those changes, and the books would stop matching."""
    c, Session = env
    users = [await make_user(c, Session, tier=3) for _ in range(8)]
    jobs = [u for u in users for _ in range(2)] + [users[0]] * 4          # 20 deposits, 8 customers, one of them hammering
    rs = await asyncio.gather(*[c.post("/api/wallet/deposit", json={"amount": 1000}, headers=u["h"]) for u in jobs])
    assert all(r.status_code == 201 for r in rs), [r.text for r in rs if r.status_code != 201][:1]
    assert (await balances(c, users[0]))["wallet_balance"] == 6000.0
    for u in users[1:]:
        assert (await balances(c, u))["wallet_balance"] == 2000.0, "lost update on a customer wallet"
    await assert_ledger_reconciles(Session)                                # includes the shared external-gateway account


@pytest.mark.asyncio
async def test_concurrent_transfers_cannot_overdraw_a_wallet(env):
    c, Session = env
    a = await make_user(c, Session, deposit=1000)
    b = await make_user(c, Session)
    rs = await asyncio.gather(*[c.post("/api/wallet/transfer", headers=a["h"], json={"recipient_identifier": b["username"], "amount": 600, "pin": "7392"}) for _ in range(6)])
    ok = [r for r in rs if r.status_code == 201]
    assert len(ok) == 1, [r.status_code for r in rs]
    assert all(r.status_code == 400 for r in rs if r.status_code != 201)
    bal = await balances(c, a)
    assert bal["wallet_balance"] >= 0 and bal["wallet_balance"] == 1000 - 600 - 9
    assert (await balances(c, b))["wallet_balance"] == 600.0
    await assert_ledger_reconciles(Session)


@pytest.mark.asyncio
async def test_concurrent_transfers_cannot_beat_the_daily_limit(env):
    c, Session = env
    a = await make_user(c, Session, tier=2, deposit=300000)      # tier 2 so the balance is allowed...
    async with Session() as s:                                    # ...then use the strict tier-1 daily limit (50,000)
        from sqlalchemy import text
        await s.execute(text("UPDATE users SET account_tier=1 WHERE id=:i"), {"i": a["id"]}); await s.commit()
    b = await make_user(c, Session)
    rs = await asyncio.gather(*[c.post("/api/wallet/transfer", headers=a["h"], json={"recipient_identifier": b["username"], "amount": 20000, "pin": "7392"}) for _ in range(5)])
    assert sorted(r.status_code for r in rs).count(201) == 2, [r.status_code for r in rs]      # 2 x 20,000 fits under 50,000, a 3rd does not
    assert any(r.status_code == 403 and "daily limit" in r.json()["detail"] for r in rs)
    await assert_ledger_reconciles(Session)


# ------------------------------------------------------------------ tier limits
@pytest.mark.asyncio
async def test_tier_one_daily_limit_and_balance_cap(env):
    c, Session = env
    a = await make_user(c, Session, deposit=200000)
    b = await make_user(c, Session)
    send = lambda amt: c.post("/api/wallet/transfer", headers=a["h"], json={"recipient_identifier": b["username"], "amount": amt, "pin": "7392"})
    assert (await send(30000)).status_code == 201
    over = await send(25000)                                        # 30,000 + 25,000 > 50,000
    assert over.status_code == 403 and "Tier 1 daily limit" in over.json()["detail"] and "₦20,000.00 left today" in over.json()["detail"]
    assert (await send(20000)).status_code == 201                    # exactly reaching the limit is allowed
    t = (await c.get("/api/tier", headers=a["h"])).json()["usage"]
    assert t["daily_limit"] == 50000 and t["spent_today"] == 50000 and t["remaining_today"] == 0
    # wallet cap: a has ~99,5xx; depositing 250,000 more would pass 300,000
    capped = await c.post("/api/wallet/deposit", json={"amount": 250000}, headers=a["h"])
    assert capped.status_code == 403 and "at most ₦300,000.00 on Tier 1" in capped.json()["detail"]
    # a bigger tier raises both limits
    async with Session() as s:
        from sqlalchemy import text
        await s.execute(text("UPDATE users SET account_tier=2 WHERE id=:i"), {"i": a["id"]}); await s.commit()
    assert (await send(60000)).status_code == 201
    assert (await c.post("/api/wallet/deposit", json={"amount": 250000}, headers=a["h"])).status_code == 201
    await assert_ledger_reconciles(Session)


@pytest.mark.asyncio
async def test_recipient_balance_cap_is_enforced_without_revealing_their_tier(env):
    c, Session = env
    rich = await make_user(c, Session, deposit=290000)
    sender = await make_user(c, Session, deposit=40000)
    r = await c.post("/api/wallet/transfer", headers=sender["h"], json={"recipient_identifier": rich["username"], "amount": 20000, "pin": "7392"})
    assert r.status_code == 400 and r.json()["detail"] == "The recipient's account can't receive this amount right now"
    assert "Tier" not in r.text and "300" not in r.text


# ------------------------------------------------------------------ bank transfers
@pytest.mark.asyncio
async def test_bank_list_suggestions_and_name_enquiry(env):
    from app.core import nuban
    c, Session = env
    u = await make_user(c, Session)
    listing = (await c.get("/api/banks", headers=u["h"])).json()
    assert listing["mode"] == "mock" and any(b["code"] == "058" and b["checkable"] for b in listing["banks"])
    assert any(not b["checkable"] for b in listing["banks"])              # wallet-style codes cannot be checked
    assert len(listing["demo_accounts"]) == 3
    assert (await c.get("/api/banks")).status_code in (401, 403)

    acct = nuban.make_account_number("058", "000000123")
    sug = (await c.get("/api/banks/suggest", params={"account_number": acct}, headers=u["h"])).json()["banks"]
    assert "058" in [b["code"] for b in sug] and len(sug) <= 5
    assert (await c.get("/api/banks/suggest", params={"account_number": "12345"}, headers=u["h"])).json() == {"banks": []}

    ok = (await c.get("/api/banks/resolve", params={"bank_code": "058", "account_number": acct}, headers=u["h"])).json()
    assert ok["bank_name"] == "Guaranty Trust Bank" and ok["account_number"] == acct and ok["account_name"].isupper()
    again = (await c.get("/api/banks/resolve", params={"bank_code": "058", "account_number": acct}, headers=u["h"])).json()
    assert again["account_name"] == ok["account_name"]                     # deterministic

    wrong_bank = nuban.make_account_number("044", "000000123")             # valid for Access, not for GTBank
    r = await c.get("/api/banks/resolve", params={"bank_code": "058", "account_number": wrong_bank}, headers=u["h"])
    assert r.status_code == 400 and "doesn't look right for Guaranty Trust Bank" in r.json()["detail"]
    assert (await c.get("/api/banks/resolve", params={"bank_code": "058", "account_number": "12345"}, headers=u["h"])).status_code == 400
    assert (await c.get("/api/banks/resolve", params={"bank_code": "999", "account_number": acct}, headers=u["h"])).status_code == 400
    missing = nuban.make_account_number("058", "999000001")                # valid number, but no such account
    assert (await c.get("/api/banks/resolve", params={"bank_code": "058", "account_number": missing}, headers=u["h"])).status_code == 404


@pytest.mark.asyncio
async def test_bank_transfer_end_to_end_and_it_is_safe_to_retry(env):
    from sqlalchemy import text
    from app.core import nuban
    c, Session = env
    u = await make_user(c, Session, deposit=20000)
    acct = nuban.make_account_number("058", "000000123")
    body = {"bank_code": "058", "account_number": acct, "amount": 5000, "pin": "7392", "narration": "Rent", "client_reference": "ref-" + uuid.uuid4().hex[:12]}
    r = await c.post("/api/banks/transfer", headers=u["h"], json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "completed" and out["type"] == "withdrawal" and out["amount"] == 5000 and out["fee_amount"] == 25
    assert out["beneficiary_name"].isupper() and out["bank_name"] == "Guaranty Trust Bank" and out["account_last4"] == acct[-4:] and out["replayed"] is False
    assert (await balances(c, u))["wallet_balance"] == 20000 - 5000 - 25

    again = await c.post("/api/banks/transfer", headers=u["h"], json=body)          # double-tap / network retry
    assert again.status_code == 201 and again.json()["reference"] == out["reference"] and again.json()["replayed"] is True
    assert (await balances(c, u))["wallet_balance"] == 20000 - 5000 - 25, "a retried payout must not debit twice"

    async with Session() as s:
        net = (await s.execute(text("SELECT SUM(CASE WHEN le.direction='C' THEN le.amount ELSE -le.amount END) FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id WHERE t.reference=:r"), {"r": out["reference"]})).scalar_one()
        meta = (await s.execute(text("SELECT metadata FROM transactions WHERE reference=:r"), {"r": out["reference"]})).scalar_one()
    assert net == 0
    assert meta["kind"] == "bank_transfer" and meta["account_last4"] == acct[-4:] and acct not in json.dumps(meta)   # full number never stored in metadata
    assert any(t["reference"] == out["reference"] for t in (await c.get("/api/wallet/transactions", headers=u["h"])).json()["items"])
    await assert_ledger_reconciles(Session)


@pytest.mark.asyncio
async def test_bank_transfer_rejections(env):
    from app.core import nuban
    c, Session = env
    u = await make_user(c, Session, deposit=10000)
    good = nuban.make_account_number("058", "000000123")
    base = {"bank_code": "058", "account_number": good, "amount": 1000, "pin": "7392"}
    post = lambda **kw: c.post("/api/banks/transfer", headers=u["h"], json={**base, **kw})
    assert (await post(pin="0001")).status_code == 400                                   # wrong PIN
    assert (await post(amount=999999)).status_code == 400                                # insufficient funds
    assert (await post(account_number=nuban.make_account_number("044", "000000123"))).status_code == 400   # wrong bank
    assert (await post(account_number="123")).status_code == 422
    assert (await post(client_reference="short")).status_code == 422
    assert (await post(amount=0)).status_code == 422
    assert (await c.post("/api/banks/transfer", json=base)).status_code in (401, 403)
    assert (await balances(c, u))["wallet_balance"] == 10000.0                           # nothing was debited by any of them
    big = await make_user(c, Session, tier=1, deposit=200000)
    over = await c.post("/api/banks/transfer", headers=big["h"], json={**base, "amount": 60000})
    assert over.status_code == 403 and "daily limit" in over.json()["detail"]


@pytest.mark.asyncio
async def test_bank_transfer_when_the_lookup_service_is_down(env):
    from app.core import nuban
    from app.services.banks import ProviderUnavailable, set_bank_provider
    c, Session = env
    u = await make_user(c, Session, deposit=5000)

    class Down:
        mode = "down"
        async def list_banks(self): raise ProviderUnavailable("boom")
        async def resolve_account(self, *a): raise ProviderUnavailable("boom")
    set_bank_provider(Down())
    r = await c.post("/api/banks/transfer", headers=u["h"], json={"bank_code": "058", "account_number": nuban.make_account_number("058", "1"), "amount": 1000, "pin": "7392"})
    assert r.status_code == 503
    assert (await balances(c, u))["wallet_balance"] == 5000.0


# ------------------------------------------------------------------ the Paystack provider (HTTP mocked)
@pytest.mark.asyncio
async def test_paystack_provider_against_mocked_http(monkeypatch):
    import httpx
    from app.core.config import settings
    from app.services.banks import AccountNotFound, ProviderUnavailable, paystack as pmod
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", "sk_test_x")
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.url.path, dict(request.url.params), request.headers.get("authorization")))
        if request.url.path == "/bank":
            if request.url.params.get("next") == "CUR2":
                return httpx.Response(200, json={"status": True, "data": [
                    {"name": "Zenith Bank", "code": "057", "active": True, "currency": "NGN"},
                    {"name": "Dead Bank", "code": "999", "active": False, "currency": "NGN"}], "meta": {"next": None}})
            return httpx.Response(200, json={"status": True, "data": [
                {"name": "Access Bank", "code": "044", "active": True, "currency": "NGN"},
                {"name": "Some Dollar Bank", "code": "777", "active": True, "currency": "USD"},
                {"name": "Access Bank", "code": "044", "active": True, "currency": "NGN"}], "meta": {"next": "CUR2"}})
        if request.url.path == "/bank/resolve":
            n = request.url.params["account_number"]
            if n == "0000000404":
                return httpx.Response(422, json={"status": False, "message": "Could not resolve account name"})
            if n == "0000000401":
                return httpx.Response(401, json={"status": False})
            if n == "0000000500":
                return httpx.Response(500, text="oops")
            return httpx.Response(200, json={"status": True, "data": {"account_number": n, "account_name": "DOE JANE LOREN", "bank_id": 9}})
        return httpx.Response(404)

    real = httpx.AsyncClient
    monkeypatch.setattr(pmod.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    p = pmod.PaystackBankProvider()
    banks = await p.list_banks()
    assert [b["code"] for b in banks] == ["044", "057"]                   # follows the cursor, drops inactive/USD/duplicates
    assert [s[1].get("next") for s in seen if s[0] == "/bank"] == [None, "CUR2"] and seen[0][2] == "Bearer sk_test_x"
    assert seen[0][1]["country"] == "nigeria" and seen[0][1]["use_cursor"] == "true"
    await p.list_banks(); assert len([s for s in seen if s[0] == "/bank"]) == 2        # cached
    assert (await p.resolve_account("058", "0123456789"))["account_name"] == "DOE JANE LOREN"
    with pytest.raises(AccountNotFound):
        await p.resolve_account("058", "0000000404")
    with pytest.raises(ProviderUnavailable):
        await p.resolve_account("058", "0000000401")
    with pytest.raises(ProviderUnavailable):
        await p.resolve_account("058", "0000000500")
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", "")
    with pytest.raises(ProviderUnavailable):
        await pmod.PaystackBankProvider().resolve_account("058", "0123456789")


# ------------------------------------------------------------------ profile photo
@pytest.mark.asyncio
async def test_profile_photo_upload_is_validated_reencoded_and_private(env, tmp_path, monkeypatch):
    from PIL import Image
    from app.core.config import settings
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    c, Session = env
    u, other = await make_user(c, Session), await make_user(c, Session)
    up = lambda name, data, ctype, who=u: c.post("/api/profile/photo", headers=who["h"], files={"file": (name, data, ctype)})

    assert (await c.get("/api/profile/photo", headers=u["h"])).status_code == 404
    r = await up("../../etc/passwd.png", image_bytes("JPEG", (1200, 700), exif=True), "image/jpeg")       # hostile name, real image with EXIF
    assert r.status_code == 200 and r.json() == {"has_photo": True}
    stored = list((tmp_path / "avatars").iterdir())
    assert len(stored) == 1 and len(stored[0].name) == 36 and stored[0].suffix == ".jpg" and "passwd" not in stored[0].name

    got = await c.get("/api/profile/photo", headers=u["h"])
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    im = Image.open(io.BytesIO(got.content))
    assert im.size == (512, 512) and im.format == "JPEG" and len(im.getexif()) == 0 and b"SecretPhoneMaker" not in got.content
    assert (await c.get("/api/auth/me", headers=u["h"])).json()["has_photo"] is True
    assert (await c.get("/api/profile/photo", headers=other["h"])).status_code == 404      # my photo is not visible to another user

    await up("new.png", image_bytes("PNG"), "image/png")                                  # replaces and removes the old file
    assert len(list((tmp_path / "avatars").iterdir())) == 1 and stored[0].name not in [p.name for p in (tmp_path / "avatars").iterdir()]

    # things that must be refused
    assert (await up("x.jpg", b"this is not an image", "image/jpeg")).status_code == 400
    assert (await up("x.jpg", b"", "image/jpeg")).status_code == 400
    assert (await up("x.gif", image_bytes("GIF"), "image/gif")).status_code == 400          # format not allowed
    assert (await up("x.jpg", b"\xff\xd8\xff" + b"0" * 100, "image/jpeg")).status_code == 400   # truncated JPEG
    assert (await up("big.png", b"\x89PNG\r\n\x1a\n" + b"0" * (settings.MAX_PHOTO_BYTES + 10), "image/png")).status_code == 413
    bomb = Image.new("1", (30000, 30000)); buf = io.BytesIO(); bomb.save(buf, format="PNG")
    assert (await up("bomb.png", buf.getvalue(), "image/png")).status_code == 400          # decompression bomb
    assert (await c.post("/api/profile/photo", files={"file": ("a.png", image_bytes(), "image/png")})).status_code in (401, 403)
    assert len(list((tmp_path / "avatars").iterdir())) == 1                                 # refusals left nothing behind

    staff = await make_staff(c, Session, __import__("app.models.user", fromlist=["UserRole"]).UserRole.admin)
    assert (await c.get(f"/api/admin/users/{u['id']}/photo", headers=u["h"])).status_code == 403
    assert (await c.get(f"/api/admin/users/{u['id']}/photo", headers=staff["h"])).status_code == 200

    assert (await c.delete("/api/profile/photo", headers=u["h"])).json() == {"has_photo": False}
    assert (await c.get("/api/profile/photo", headers=u["h"])).status_code == 404 and not list((tmp_path / "avatars").iterdir())


# ------------------------------------------------------------------ loans
@pytest.mark.asyncio
async def test_loan_lifecycle_and_the_ledger_stays_balanced(env):
    from sqlalchemy import text
    c, Session = env
    u = await make_user(c, Session)                      # tier 1
    offer = (await c.get("/api/loans/offer", headers=u["h"])).json()
    assert offer["eligible"] is False and "Tier 2" in offer["reasons"][0]
    body = {"amount": 10000, "tenor_days": 14, "pin": "7392", "accept_terms": True}
    assert (await c.post("/api/loans/apply", headers=u["h"], json=body)).status_code == 403

    async with Session() as s:
        await s.execute(text("UPDATE users SET account_tier=2 WHERE id=:i"), {"i": u["id"]}); await s.commit()
        pool_before = (await s.execute(text("SELECT balance FROM accounts WHERE account_type='platform_loan_pool'"))).scalar_one()
    offer = (await c.get("/api/loans/offer", headers=u["h"])).json()
    assert offer["eligible"] and offer["max_amount"] == 50000 and offer["min_amount"] == 1000
    assert [t["days"] for t in offer["tenors"]] == [7, 14, 30] and offer["tenors"][2]["interest_percent"] == 5.0

    q = (await c.post("/api/loans/quote", headers=u["h"], json={"amount": 10000, "tenor_days": 14})).json()
    assert q["principal"] == 10000 and q["interest"] == 233.33 and q["total_due"] == 10233.33
    assert (await c.post("/api/loans/quote", headers=u["h"], json={"amount": 500, "tenor_days": 14})).status_code == 400          # below minimum
    assert (await c.post("/api/loans/quote", headers=u["h"], json={"amount": 60000, "tenor_days": 14})).status_code == 400         # above maximum
    assert (await c.post("/api/loans/quote", headers=u["h"], json={"amount": 5000, "tenor_days": 10})).status_code == 400          # not an offered period

    assert (await c.post("/api/loans/apply", headers=u["h"], json={**body, "accept_terms": False})).status_code == 400
    assert (await c.post("/api/loans/apply", headers=u["h"], json={**body, "pin": "0001"})).status_code == 400
    r = await c.post("/api/loans/apply", headers=u["h"], json=body)
    assert r.status_code == 201, r.text
    loan = r.json()
    assert loan["status"] == "active" and loan["outstanding"] == 10233.33 and loan["is_overdue"] is False
    assert (await balances(c, u))["wallet_balance"] == 10000.0
    assert (await c.post("/api/loans/apply", headers=u["h"], json=body)).status_code == 403                                       # one active loan at a time
    async with Session() as s:
        pool = (await s.execute(text("SELECT balance FROM accounts WHERE account_type='platform_loan_pool'"))).scalar_one()
        net = (await s.execute(text("SELECT SUM(CASE WHEN le.direction='C' THEN le.amount ELSE -le.amount END) FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id WHERE t.reference=:r"), {"r": loan["transaction_reference"]})).scalar_one()
    assert float(pool) - float(pool_before) == -10000 and net == 0

    # repayments: interest first, then principal
    bad = lambda amt, pin="7392": c.post(f"/api/loans/{loan['id']}/repay", headers=u["h"], json={"amount": amt, "pin": pin})
    assert (await bad(50000)).status_code == 400 and (await bad(100, "0001")).status_code == 400
    part = (await bad(5000)).json()
    assert part["repaid"] == 5000 and part["outstanding"] == 5233.33 and part["status"] == "active"
    async with Session() as s:
        rev = (await s.execute(text("SELECT COALESCE(SUM(le.amount),0) FROM ledger_entries le JOIN accounts a ON a.id=le.account_id JOIN transactions t ON t.id=le.transaction_id WHERE a.account_type='platform_revenue' AND t.type='loan_repayment' AND t.metadata->>'loan_reference'=:r AND le.direction='C'"), {"r": loan["reference"]})).scalar_one()
    assert float(rev) == 233.33                                                       # the whole interest, paid first
    await c.post("/api/wallet/deposit", json={"amount": 1000}, headers=u["h"])
    done = (await bad(5233.33)).json()
    assert done["status"] == "repaid" and done["outstanding"] == 0 and done["closed_at"]
    assert (await bad(1)).status_code == 400                                          # already repaid
    async with Session() as s:
        pool_after = (await s.execute(text("SELECT balance FROM accounts WHERE account_type='platform_loan_pool'"))).scalar_one()
    assert float(pool_after) == float(pool_before)                                    # all the principal came back
    assert [l["status"] for l in (await c.get("/api/loans", headers=u["h"])).json()] == ["repaid"]
    assert (await c.get("/api/loans/offer", headers=u["h"])).json()["eligible"] is True        # can borrow again
    await assert_ledger_reconciles(Session)


@pytest.mark.asyncio
async def test_loan_edge_cases_overdue_isolation_balance_cap_and_races(env):
    from sqlalchemy import text
    from app.models.user import UserRole
    c, Session = env
    u = await make_user(c, Session, tier=2, deposit=495000)
    offer = (await c.get("/api/loans/offer", headers=u["h"])).json()
    assert offer["max_amount"] == 5000                                                # tier-2 balance cap of 500,000 leaves room for 5,000
    assert (await c.post("/api/loans/quote", headers=u["h"], json={"amount": 6000, "tenor_days": 7})).status_code == 400
    full = await make_user(c, Session, tier=2, deposit=499500)
    o2 = (await c.get("/api/loans/offer", headers=full["h"])).json()
    assert o2["eligible"] is False and "too close" in o2["reasons"][0]

    # two simultaneous applications: exactly one loan
    v = await make_user(c, Session, tier=2)
    body = {"amount": 2000, "tenor_days": 7, "pin": "7392", "accept_terms": True}
    rs = await asyncio.gather(*[c.post("/api/loans/apply", headers=v["h"], json=body) for _ in range(4)])
    assert sorted(r.status_code for r in rs).count(201) == 1, [r.status_code for r in rs]
    assert (await balances(c, v))["wallet_balance"] == 2000.0
    loan = next(r.json() for r in rs if r.status_code == 201)

    # another customer cannot repay or see it
    thief = await make_user(c, Session, tier=2, deposit=5000)
    assert (await c.post(f"/api/loans/{loan['id']}/repay", headers=thief["h"], json={"amount": 100, "pin": "7392"})).status_code == 404
    assert (await c.get("/api/loans", headers=thief["h"])).json() == []
    assert (await c.post("/api/loans/not-a-uuid/repay", headers=v["h"], json={"amount": 100, "pin": "7392"})).status_code == 404

    # overdue is detected, and shows in the admin view and the stats
    async with Session() as s:
        await s.execute(text("UPDATE loans SET due_at = now() - interval '2 days' WHERE id=:i"), {"i": loan["id"]}); await s.commit()
    mine = (await c.get("/api/loans", headers=v["h"])).json()[0]
    assert mine["is_overdue"] is True and mine["status"] == "active"
    admin = await make_staff(c, Session, UserRole.admin)
    listing = (await c.get("/api/admin/loans", params={"status": "active"}, headers=admin["h"])).json()
    row = next(l for l in listing if l["id"] == loan["id"])
    assert row["is_overdue"] and row["user"]["account_number"] == v["acct"]
    assert (await c.get("/api/admin/loans", headers=v["h"])).status_code == 403
    stats = (await c.get("/api/admin/stats", headers=admin["h"])).json()
    assert stats["active_loans"] >= 1 and stats["loans_outstanding"] >= 2000
    await assert_ledger_reconciles(Session)


# ------------------------------------------------------------------ platform accounts + upgrade of an old database
@pytest.mark.asyncio
async def test_platform_accounts_exist_exactly_once_and_seeding_is_idempotent(env):
    from sqlalchemy import text
    from app.core.migrations import seed_platform_accounts, PLATFORM_ACCOUNT_TYPES
    c, Session = env
    async with Session() as s:
        conn = await s.connection()
        await seed_platform_accounts(conn); await seed_platform_accounts(conn); await s.commit()
        rows = (await s.execute(text("SELECT account_type::text, count(*) FROM accounts WHERE user_id IS NULL GROUP BY 1"))).all()
    assert {r[0] for r in rows} >= set(PLATFORM_ACCOUNT_TYPES) and all(r[1] == 1 for r in rows)
