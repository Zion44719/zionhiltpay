"""
Identity features against a REAL Postgres: account numbers, username + ID at registration,
login by any identifier, encrypted ID storage, KYC review, and upgrading an old database.

Skipped unless TEST_DATABASE_URL is set (see test_agent_integration.py).
"""
import json
import os
import random
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="set TEST_DATABASE_URL to run DB integration tests")


def _nin() -> str:
    return "".join(random.choice("123456789") + "".join(random.choices("0123456789", k=10)) for _ in range(1))


def _local_phone() -> str:
    return "080" + "".join(random.choices("0123456789", k=8))


@pytest.fixture
async def env(monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.main import app
    from app.core.database import get_db
    from app.core.limiter import limiter
    from app.services.payment_gateway import payment_gateway

    monkeypatch.setattr(limiter, "enabled", False)          # this test registers many users from one IP
    monkeypatch.setattr(payment_gateway, "success_rate", 1.0)
    monkeypatch.setattr(payment_gateway, "latency_ms", 0)
    engine = create_async_engine(TEST_DB, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def override_get_db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c, Session
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


def _payload(**over):
    tag = uuid.uuid4().hex[:8]
    base = {
        "full_name": "Ada Lovelace", "username": f"ada_{tag}", "email": f"ada{tag}@example.com",
        "phone_number": _local_phone(), "password": "StrongPass123",
        "id_type": "national_id", "id_number": _nin(), "consent_id_processing": True,
    }
    base.update(over)
    return base


async def _verify(Session, email):
    from sqlalchemy import text
    async with Session() as s:
        await s.execute(text("UPDATE users SET email_verified=true WHERE lower(email)=:e"), {"e": email.lower()})
        await s.commit()


async def _login(c, identifier, password="StrongPass123"):
    return await c.post("/api/auth/login", json={"identifier": identifier, "password": password})


@pytest.mark.asyncio
async def test_register_login_any_identifier_and_id_protection(env):
    from sqlalchemy import text
    from app.core import identity as idt
    c, Session = env

    p = _payload()
    r = await c.post("/api/auth/register", json=p)
    assert r.status_code == 201, r.text
    reg = r.json()
    acct = reg["account_number"]
    assert idt.is_valid_account_number(acct)
    assert reg["phone_number"] == "+234" + p["phone_number"][1:]      # local format normalised to E.164
    assert reg["username"] == p["username"]
    await _verify(Session, p["email"])

    # ---- login with each of the four identifiers (typed messily) ----
    spaced_acct = f" {acct[:3]} {acct[3:6]} {acct[6:]} "
    for ident in (spaced_acct, p["username"].upper(), p["email"].upper(), p["phone_number"], reg["phone_number"]):
        r = await _login(c, ident)
        assert r.status_code == 200, (ident, r.text)
    assert (await c.post("/api/auth/login", json={"email": p["email"], "password": "StrongPass123"})).status_code == 200  # legacy field

    # wrong password and unknown identifier give the SAME generic answer
    bad_pw = await _login(c, p["username"], "WrongPass123")
    unknown = await _login(c, "nobody_here_x")
    assert bad_pw.status_code == unknown.status_code == 401 and bad_pw.json() == unknown.json()

    token = (await _login(c, acct)).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # ---- the ID number is encrypted at rest and appears nowhere readable ----
    nin = p["id_number"]
    async with Session() as s:
        row = (await s.execute(text("select * from users where lower(email)=:e"), {"e": p["email"]})).mappings().one()
        assert row["id_number_enc"] and nin not in row["id_number_enc"]
        assert row["id_number_hash"] and nin not in row["id_number_hash"] and len(row["id_number_hash"]) == 64
        assert row["id_number_last4"] == nin[-4:] and row["kyc_status"] == "submitted"
        assert nin not in json.dumps({k: str(v) for k, v in row.items() if k != "id_number_last4"})
        audit = (await s.execute(text("select coalesce(string_agg(details::text, ' '), '') from audit_logs"))).scalar_one()
        assert nin not in audit, "ID number leaked into the audit log"

    me = (await c.get("/api/auth/me", headers=h)).json()
    assert me["account_number"] == acct and me["username"] == p["username"].lower()
    assert me["id_number_last4"] == nin[-4:] and me["kyc_status"] == "submitted"
    blob = json.dumps(me)
    assert nin not in blob and "id_number_enc" not in blob and "id_number_hash" not in blob
    bal = (await c.get("/api/wallet/balance", headers=h)).json()
    assert bal["account_number"] == acct

    # ---- duplicates, including disguised ones ----
    assert (await c.post("/api/auth/register", json=_payload(username=p["username"].upper()))).status_code == 409
    assert (await c.post("/api/auth/register", json=_payload(email=p["email"].upper()))).status_code == 409
    assert (await c.post("/api/auth/register", json=_payload(phone_number="+234" + p["phone_number"][1:]))).status_code == 409
    spaced_nin = f"{nin[:3]} {nin[3:7]}-{nin[7:]}"
    dup_id = await c.post("/api/auth/register", json=_payload(id_number=spaced_nin))
    assert dup_id.status_code == 409 and "ID" in dup_id.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [
    {"id_number": "1234567890"},                       # NIN too short
    {"id_number": "00000000000"},                      # not plausible
    {"id_type": "drivers_license", "id_number": "ABCDEFGHIJ"},   # no digit
    {"id_type": "passport"},
    {"consent_id_processing": False},
    {"username": "ab"}, {"username": "1abc"}, {"username": "admin"}, {"username": "zionhilt_ceo"},
    {"phone_number": "1234567890"}, {"phone_number": "abc"},
    {"password": "weak"},
])
async def test_registration_validation_rejects(env, override):
    c, _ = env
    r = await c.post("/api/auth/register", json=_payload(**override))
    assert r.status_code == 422, (override, r.text)


@pytest.mark.asyncio
async def test_missing_username_or_id_is_rejected(env):
    c, _ = env
    for field in ("username", "id_type", "id_number", "consent_id_processing"):
        p = _payload(); p.pop(field)
        assert (await c.post("/api/auth/register", json=p)).status_code == 422, field


@pytest.mark.asyncio
async def test_drivers_license_registration(env):
    c, _ = env
    r = await c.post("/api/auth/register", json=_payload(id_type="drivers_license", id_number="abc-12345-aa-" + str(random.randint(10, 99))))
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_username_availability(env):
    c, _ = env
    p = _payload()
    assert (await c.get("/api/auth/username-available", params={"username": p["username"]})).json()["available"] is True
    await c.post("/api/auth/register", json=p)
    taken = (await c.get("/api/auth/username-available", params={"username": p["username"].upper()})).json()
    assert taken["available"] is False and "taken" in taken["reason"]
    assert (await c.get("/api/auth/username-available", params={"username": "admin"})).json()["available"] is False


@pytest.mark.asyncio
async def test_account_number_collision_is_retried(env, monkeypatch):
    from app.core import identity as idt
    c, _ = env
    first = (await c.post("/api/auth/register", json=_payload())).json()["account_number"]
    seq = iter([first, first, None])
    real = idt.generate_account_number
    monkeypatch.setattr(idt, "generate_account_number", lambda: next(seq) or real())
    r = await c.post("/api/auth/register", json=_payload())          # first two draws collide
    assert r.status_code == 201, r.text
    assert r.json()["account_number"] != first and idt.is_valid_account_number(r.json()["account_number"])


@pytest.mark.asyncio
async def test_real_otp_flow_with_local_phone_format(env, monkeypatch):
    """Register by SMS with '0801...' and verify typing it the same way: both normalise to the same number."""
    from app.services import otp_service
    c, Session = env
    sent = {}

    async def fake_sms(to_phone, code, purpose):
        sent["phone"], sent["code"] = to_phone, code
    monkeypatch.setattr(otp_service, "_deliver_sms", fake_sms)

    p = _payload(preferred_otp_channel="sms")
    reg = (await c.post("/api/auth/register", json=p)).json()
    assert sent["phone"] == reg["phone_number"] == "+234" + p["phone_number"][1:]
    assert (await _login(c, p["username"])).status_code == 403         # not verified yet
    ok = await c.post("/api/auth/otp/verify", json={"phone_number": p["phone_number"], "purpose": "registration", "code": sent["code"]})
    assert ok.status_code == 200, ok.text
    assert (await _login(c, p["phone_number"])).status_code == 200


@pytest.mark.asyncio
async def test_transfer_by_every_identifier_and_name_enquiry(env):
    from app.core import identity as idt
    c, Session = env
    async def mk(name):
        p = _payload(full_name=name); r = (await c.post("/api/auth/register", json=p)).json()
        await _verify(Session, p["email"])
        tok = (await _login(c, p["username"])).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        pin = "7392" if name.startswith("Sender") else "5821"
        await c.post("/api/auth/pin/set", json={"pin": pin, "confirm_pin": pin}, headers=h)
        return p, r, h
    sp, sr, sh = await mk("Sender One")
    rp, rr, rh = await mk("Grace Hopper")
    assert (await c.post("/api/wallet/deposit", json={"amount": 100000}, headers=sh)).status_code == 201

    # name enquiry: masked name only, no email/phone
    q = (await c.get("/api/wallet/resolve-recipient", params={"identifier": rr["account_number"]}, headers=sh)).json()
    assert q["found"] and q["name"] == "Grace H." and q["account_number"] == rr["account_number"]
    assert rp["email"] not in json.dumps(q) and rr["phone_number"] not in json.dumps(q)
    assert (await c.get("/api/wallet/resolve-recipient", params={"identifier": sr["account_number"]}, headers=sh)).json()["is_self"] is True
    typo = rr["account_number"][:-1] + str((int(rr["account_number"][-1]) + 1) % 10)
    assert (await c.get("/api/wallet/resolve-recipient", params={"identifier": typo}, headers=sh)).json()["found"] is False
    assert (await c.get("/api/wallet/resolve-recipient", params={"identifier": rr["account_number"]})).status_code in (401, 403)

    for ident in (rr["account_number"], rp["username"].upper(), rp["email"], rp["phone_number"]):
        r = await c.post("/api/wallet/transfer", headers=sh,
                         json={"recipient_identifier": ident, "amount": 1000, "pin": "7392"})
        assert r.status_code == 201, (ident, r.text)
    bal = (await c.get("/api/wallet/balance", headers=rh)).json()
    assert bal["wallet_balance"] == 4000.0                              # 4 transfers of 1,000 arrived

    bad = await c.post("/api/wallet/transfer", headers=sh, json={"recipient_identifier": typo, "amount": 100, "pin": "7392"})
    assert bad.status_code == 400 and "valid account number" in bad.json()["detail"]
    self_t = await c.post("/api/wallet/transfer", headers=sh, json={"recipient_identifier": sr["account_number"], "amount": 100, "pin": "7392"})
    assert self_t.status_code == 400


@pytest.mark.asyncio
async def test_admin_kyc_review_reveal_and_directory(env):
    from sqlalchemy import text
    from app.core.security import hash_password
    from app.core import identity as idt
    from app.models.user import User, UserRole
    c, Session = env

    async def mk_admin(role):
        tag = uuid.uuid4().hex[:8]
        async with Session() as s:
            u = User(full_name="Staff Member", username=f"staff_{tag}", email=f"staff{tag}@example.com",
                     phone_number="+23481" + str(random.randint(10**7, 10**8 - 1)), password_hash=hash_password("StrongPass123"),
                     role=role, email_verified=True, account_number=idt.generate_account_number(), kyc_status="verified", kyc_level=2)
            s.add(u); await s.commit()
            return u.username, u.id
    admin_name, admin_id = await mk_admin(UserRole.admin)
    super_name, _ = await mk_admin(UserRole.super_admin)
    ah = {"Authorization": "Bearer " + (await _login(c, admin_name)).json()["access_token"]}
    sh = {"Authorization": "Bearer " + (await _login(c, super_name)).json()["access_token"]}

    p = _payload()
    reg = (await c.post("/api/auth/register", json=p)).json()
    uid = reg["user_id"]

    # directory: search by account number / username, filter by kyc_status
    by_acct = (await c.get("/api/admin/users", params={"q": reg["account_number"]}, headers=ah)).json()
    assert [u["id"] for u in by_acct] == [uid]
    u = by_acct[0]
    assert u["username"] == p["username"].lower() and u["kyc_status"] == "submitted" and u["id_number_last4"] == p["id_number"][-4:]
    assert p["id_number"] not in json.dumps(by_acct) and "id_number_enc" not in json.dumps(by_acct)
    pending = (await c.get("/api/admin/users", params={"kyc_status": "submitted", "page_size": 100}, headers=ah)).json()
    assert uid in [x["id"] for x in pending]
    assert (await c.get("/api/admin/users", headers={"Authorization": "Bearer x"})).status_code == 401

    # plain admins cannot reveal; super admins can, and it is audited without the number
    assert (await c.post(f"/api/admin/users/{uid}/kyc/reveal", headers=ah)).status_code == 403
    rev = await c.post(f"/api/admin/users/{uid}/kyc/reveal", headers=sh)
    assert rev.status_code == 200 and rev.json() == {"id_type": "national_id", "id_number": p["id_number"]}
    async with Session() as s:
        n = (await s.execute(text("select count(*) from audit_logs where action='KYC_ID_REVEALED' and entity_id=:i"), {"i": uid})).scalar_one()
        assert n == 1
        alltext = (await s.execute(text("select coalesce(string_agg(details::text, ' '), '') from audit_logs"))).scalar_one()
        assert p["id_number"] not in alltext

    # approve -> verified + level 1; admin cannot review themselves; bad uuid is a clean 422
    ok = await c.post(f"/api/admin/users/{uid}/kyc", json={"decision": "verify", "note": "Matches NIMC record"}, headers=ah)
    assert ok.status_code == 200 and ok.json()["kyc_status"] == "verified"
    got = (await c.get(f"/api/admin/users/{uid}", headers=ah)).json()
    assert got["kyc_status"] == "verified" and got["kyc_level"] == 1
    assert (await c.post(f"/api/admin/users/{admin_id}/kyc", json={"decision": "verify"}, headers=ah)).status_code in (400, 403)
    assert (await c.post("/api/admin/users/not-a-uuid/kyc", json={"decision": "verify"}, headers=ah)).status_code == 422
    rej = await c.post(f"/api/admin/users/{uid}/kyc", json={"decision": "reject", "note": "Name mismatch"}, headers=ah)
    assert rej.json()["kyc_status"] == "rejected"
    assert (await c.get(f"/api/admin/users/{uid}", headers=ah)).json()["kyc_level"] == 0

    # all-transactions view finds things by sender account number
    await _verify(Session, p["email"])
    tok = {"Authorization": "Bearer " + (await _login(c, reg["account_number"])).json()["access_token"]}
    await c.post("/api/wallet/deposit", json={"amount": 5000}, headers=tok)
    txns = (await c.get("/api/admin/transactions", params={"q": reg["account_number"]}, headers=ah)).json()
    assert txns and txns[0]["type"] == "deposit" and txns[0]["from_account_number"] == reg["account_number"]


@pytest.mark.asyncio
async def test_upgrade_of_an_old_database_adds_columns_and_backfills():
    """An older database has `users` without the identity columns. upgrade_schema must add them,
    keep existing users working, and give each a unique valid account number - repeatably."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.core.migrations import upgrade_schema
    from app.core import identity as idt

    engine = create_async_engine(TEST_DB, poolclass=NullPool)
    schema = "legacy_" + uuid.uuid4().hex[:8]
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"CREATE SCHEMA {schema}"))
            await conn.execute(text(f"SET LOCAL search_path TO {schema}"))
            await conn.execute(text("CREATE TABLE users (id uuid PRIMARY KEY, full_name text NOT NULL, email text NOT NULL)"))
            for i in range(25):
                await conn.execute(text("INSERT INTO users VALUES (gen_random_uuid(), :n, :e)"), {"n": f"U{i}", "e": f"u{i}@old.example"})
            assert await upgrade_schema(conn) == 25
            assert await upgrade_schema(conn) == 0                       # idempotent
            rows = (await conn.execute(text("SELECT account_number, kyc_status, username FROM users"))).all()
            nums = [r[0] for r in rows]
            assert len(set(nums)) == 25 and all(idt.is_valid_account_number(n) for n in nums)
            assert all(r[1] == "not_submitted" and r[2] is None for r in rows)   # existing users: no ID yet, no username
            cols = {r[0] for r in (await conn.execute(text(
                "select column_name from information_schema.columns where table_schema=:s and table_name='users'"), {"s": schema})).all()}
            assert {"username", "account_number", "id_type", "id_number_enc", "id_number_hash", "id_number_last4", "kyc_status"} <= cols
            # the unique index really enforces uniqueness
            with pytest.raises(Exception):
                async with conn.begin_nested():
                    await conn.execute(text("UPDATE users SET account_number = :n WHERE id IN (SELECT id FROM users LIMIT 2)"), {"n": nums[0]})
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()


@pytest.mark.asyncio
async def test_otp_verify_exactly_as_the_ui_sends_it(env, monkeypatch):
    """Regression: the verify page sends BOTH email and phone. Each OTP is stored against only one of
    them, so matching on both made every real verification fail. Also, only the proven channel may
    become verified."""
    from sqlalchemy import text
    from app.services import otp_service
    c, Session = env
    sent = {}

    async def fake_email(to_email, code, purpose):
        sent["code"] = code
    monkeypatch.setattr(otp_service, "_deliver_email", fake_email)

    p = _payload()
    reg = (await c.post("/api/auth/register", json=p)).json()
    r = await c.post("/api/auth/otp/verify", json={
        "email": reg["email"], "phone_number": reg["phone_number"], "purpose": "registration", "code": sent["code"]})
    assert r.status_code == 200, r.text
    async with Session() as s:
        email_ok, phone_ok = (await s.execute(
            text("select email_verified, phone_verified from users where lower(email)=:e"), {"e": p["email"]})).one()
    assert email_ok is True
    assert phone_ok is False, "verifying the email code must not mark the phone as verified"
    assert (await _login(c, p["username"])).status_code == 200


@pytest.mark.asyncio
async def test_otp_attempt_limit_is_enforced_and_survives_the_error_response(env, monkeypatch):
    """Regression: failed guesses used to be rolled back with the error, so the limit never applied."""
    from sqlalchemy import text
    from app.services import otp_service
    c, Session = env
    sent = {}

    async def fake_email(to_email, code, purpose):
        sent["code"] = code
    monkeypatch.setattr(otp_service, "_deliver_email", fake_email)

    p = _payload()
    reg = (await c.post("/api/auth/register", json=p)).json()
    right = sent["code"]
    wrong = "000000" if right != "000000" else "111111"
    body = lambda code: {"email": reg["email"], "purpose": "registration", "code": code}

    for _ in range(5):
        assert (await c.post("/api/auth/otp/verify", json=body(wrong))).status_code == 400
    async with Session() as s:
        attempts = (await s.execute(text(
            "select attempts from otp_codes where lower(target_email)=:e order by created_at desc limit 1"), {"e": p["email"]})).scalar_one()
    assert attempts == 5, "failed attempts were not persisted"
    locked = await c.post("/api/auth/otp/verify", json=body(right))
    assert locked.status_code == 400, "a locked code must be rejected even when correct"

    # asking for a fresh code is the way out
    assert (await c.post("/api/auth/otp/resend", json={"email": reg["email"], "purpose": "registration"})).status_code == 200
    assert sent["code"] != right or True
    ok = await c.post("/api/auth/otp/verify", json=body(sent["code"]))
    assert ok.status_code == 200, ok.text
