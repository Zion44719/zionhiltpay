"""
Verification documents and tier upgrades: draft, edit, submit, edit under review, withdraw, direct Tier 1 to Tier 3,
and ID correction. Real Postgres; skipped without TEST_DATABASE_URL.
"""
import asyncio
import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_features_integration import env, make_staff, make_user, image_bytes, assert_ledger_reconciles  # noqa: E402,F401
from test_identity_integration import _payload  # noqa: E402

TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="set TEST_DATABASE_URL to run DB integration tests")

ADDR = "12 Adeola Odeku Street, Victoria Island, Lagos"


def bvn_number() -> str:
    return "2" + "".join(random.choices("0123456789", k=10))


def doc_files(tmp_path):
    d = tmp_path / "documents"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


async def put(c, u, files=None, **form):
    return await c.put("/api/tier/documents", headers=u["h"], data={k: str(v) for k, v in form.items()}, files=files)


def bill(size=(1800, 1200)):
    return {"document": ("bill.jpg", image_bytes("JPEG", size), "image/jpeg")}


async def add_photo(c, u):
    assert (await c.post("/api/profile/photo", headers=u["h"], files={"file": ("me.png", image_bytes(), "image/png")})).status_code == 200


async def verify_id(c, admin, u):
    assert (await c.post(f"/api/admin/users/{u['id']}/kyc", headers=admin["h"], json={"decision": "verify"})).status_code == 200


async def admin_row(c, admin, u, status="pending"):
    rows = (await c.get("/api/admin/tier-requests", params={"status": status}, headers=admin["h"])).json()
    return next((r for r in rows if r["user"]["id"] == u["id"]), None)


@pytest.mark.asyncio
async def test_documents_draft_edit_submit_and_go_straight_to_tier_three(env, tmp_path, monkeypatch):
    from sqlalchemy import text
    from app.core.config import settings
    from app.models.user import UserRole
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    c, Session = env
    u = await make_user(c, Session)                                   # Tier 1, ID submitted but not yet verified
    admin = await make_staff(c, Session, UserRole.admin)
    bvn, bvn2 = bvn_number(), bvn_number()

    ov = (await c.get("/api/tier", headers=u["h"])).json()
    assert ov["request"] is None and ov["targets"] == [2, 3] and ov["identity"]["kyc_status"] == "submitted" and ov["has_photo"] is False

    # a draft is created on first save, and can be filled in over several visits
    assert (await put(c, u)).status_code == 400                       # no target chosen
    for bad in (1, 4, 0):
        assert (await put(c, u, target_tier=bad)).status_code == 400
    d = (await put(c, u, target_tier=3)).json()
    assert d["status"] == "draft" and d["target_tier"] == 3 and d["can_edit"]
    assert {m["key"] for m in d["missing"]} == {"photo", "bvn", "address", "document"}
    sub = await c.post("/api/tier/submit", headers=u["h"])
    assert sub.status_code == 400 and "Still needed" in sub.json()["detail"]

    await add_photo(c, u)
    assert (await put(c, u, bvn="1234567890")).status_code == 400                       # 10 digits
    assert (await put(c, u, bvn="11111111111")).status_code == 400
    assert (await put(c, u, address="short")).status_code == 400
    assert (await put(c, u, files={"document": ("b.pdf", b"%PDF-1.4 nope", "application/pdf")})).status_code == 400
    assert (await put(c, u, files={"document": ("t.png", image_bytes("PNG", (100, 100)), "image/png")})).status_code == 400
    assert doc_files(tmp_path) == [], "refused uploads must leave nothing behind"

    d = (await put(c, u, bvn=bvn2, address=ADDR, files=bill())).json()                 # (first BVN typed wrongly)
    assert d["bvn_last4"] == bvn2[-4:] and d["address"] == ADDR and d["has_document"] and d["status"] == "draft"
    first_doc = doc_files(tmp_path); assert len(first_doc) == 1
    d = (await put(c, u, bvn=bvn)).json()                                              # ...so the draft is simply edited
    assert d["bvn_last4"] == bvn[-4:]
    d = (await put(c, u, files=bill((2000, 1400)))).json()                             # replace the photo of the bill
    new_doc = doc_files(tmp_path); assert len(new_doc) == 1 and new_doc != first_doc, "replacing a document must delete the old file"
    mine = await c.get("/api/tier/documents/file", headers=u["h"])
    assert mine.status_code == 200 and mine.headers["content-type"] == "image/jpeg" and "no-store" in mine.headers["cache-control"]
    other = await make_user(c, Session)
    assert (await c.get("/api/tier/documents/file", headers=other["h"])).status_code == 404       # nobody else can fetch it
    assert (await put(c, u, target_tier=2)).json()["target_tier"] == 2 and (await put(c, u, target_tier=3)).json()["target_tier"] == 3

    # a draft is private: the reviewer cannot see it, however they ask (default view, "everything", or "drafts" specifically)
    for params in ({}, {"status": ""}, {"status": "draft"}):
        listing = (await c.get("/api/admin/tier-requests", params=params, headers=admin["h"])).json()
        assert u["id"] not in [r["user"]["id"] for r in listing], params

    # submit: now it is under review, and visible to the reviewer
    s = (await c.post("/api/tier/submit", headers=u["h"])).json()
    assert s["status"] == "pending" and s["missing"] == [] and s["edit_count"] == 0
    assert (await c.post("/api/tier/submit", headers=u["h"])).status_code == 409
    async with Session() as s_:                                                        # the BVN is encrypted at rest, never plain
        enc, fp = (await s_.execute(text("SELECT bvn_enc, bvn_hash FROM tier_requests WHERE user_id=:i"), {"i": u["id"]})).one()
    assert enc and bvn not in enc and (fp is None or (len(fp) == 64 and bvn not in fp))
    row = await admin_row(c, admin, u)
    assert row["target_tier"] == 3 and row["user"]["current_tier"] == 1 and row["edited_after_submit"] is False and row["bvn_last4"] == bvn[-4:]

    # ...but it stays editable, and the reviewer is told when it changed
    e = (await put(c, u, address="45 Allen Avenue, Ikeja, Lagos State")).json()
    assert e["status"] == "pending" and e["edit_count"] == 1 and e["address"].startswith("45 Allen")
    before = doc_files(tmp_path)
    e = (await put(c, u, files=bill((1600, 1100)))).json()
    assert e["edit_count"] == 2 and doc_files(tmp_path) != before and len(doc_files(tmp_path)) == 1
    assert (await put(c, u, address="")).status_code == 400                           # cannot strip things out while under review
    assert (await put(c, u, remove_document="true")).status_code == 400
    assert (await put(c, u, bvn="12345")).status_code == 400
    row = await admin_row(c, admin, u)
    assert row["edited_after_submit"] is True and row["edit_count"] == 2 and row["address"].startswith("45 Allen")

    # approval: the ID must be verified first, and then Tier 1 goes straight to Tier 3
    blocked = await c.post(f"/api/admin/tier-requests/{row['id']}/decision", headers=admin["h"], json={"decision": "approve"})
    assert blocked.status_code == 400 and "Verify this customer's ID first" in blocked.json()["detail"]
    await verify_id(c, admin, u)
    ok = await c.post(f"/api/admin/tier-requests/{row['id']}/decision", headers=admin["h"], json={"decision": "approve", "note": "All good"})
    assert ok.json() == {"status": "approved", "user_tier": 3}
    ov = (await c.get("/api/tier", headers=u["h"])).json()
    assert ov["current_tier"] == 3 and ov["request"] is None and ov["targets"] == [] and ov["usage"]["daily_limit"] == 5000000
    assert (await put(c, u, target_tier=3)).status_code == 400

    async with Session() as s_:
        audit = (await s_.execute(text("SELECT coalesce(string_agg(action || ' ' || details::text, ' '),'') FROM audit_logs"))).scalar_one()
    assert bvn not in audit and bvn2 not in audit and "Adeola" not in audit and "Allen" not in audit, "secrets leaked into the audit trail"
    for action in ("TIER_DRAFT_SAVED", "TIER_UPGRADE_REQUESTED", "TIER_REQUEST_EDITED", "TIER_APPROVED"):
        assert action in audit, action


@pytest.mark.asyncio
async def test_rejection_is_fixed_by_editing_and_documents_are_reused(env, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.models.user import UserRole
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    c, Session = env
    u = await make_user(c, Session)
    admin = await make_staff(c, Session, UserRole.admin)
    await add_photo(c, u); await verify_id(c, admin, u)
    bvn = bvn_number()

    await put(c, u, target_tier=2, bvn=bvn)
    assert (await c.post("/api/tier/submit", headers=u["h"])).json()["status"] == "pending"
    row = await admin_row(c, admin, u)
    rej = await c.post(f"/api/admin/tier-requests/{row['id']}/decision", headers=admin["h"], json={"decision": "reject", "note": "BVN does not match the name on the account"})
    assert rej.json()["status"] == "rejected"
    ov = (await c.get("/api/tier", headers=u["h"])).json()
    assert ov["request"] is None and ov["last_rejection"]["review_note"].startswith("BVN does not match")

    # a new draft starts from what they already gave us: nothing is typed twice
    d = (await put(c, u, target_tier=3)).json()
    assert d["bvn_last4"] == bvn[-4:] and {m["key"] for m in d["missing"]} == {"address", "document"}
    await put(c, u, address=ADDR, files=bill())
    assert (await c.post("/api/tier/submit", headers=u["h"])).status_code == 200      # inherited BVN submits fine
    row3 = await admin_row(c, admin, u)
    assert (await c.post(f"/api/admin/tier-requests/{row3['id']}/decision", headers=admin["h"], json={"decision": "reject", "note": "Bill too old"})).status_code == 200
    assert len(doc_files(tmp_path)) == 1                                              # the rejected request still holds its photo

    # editing after a rejection copies the earlier photo, so withdrawing the new draft cannot delete the old one
    d = (await put(c, u, target_tier=3)).json()
    assert d["has_document"] and d["address"] == ADDR and d["missing"] == []
    assert len(doc_files(tmp_path)) == 2
    assert (await c.delete("/api/tier/documents", headers=u["h"])).json() == {"withdrawn": True}
    assert len(doc_files(tmp_path)) == 1 and (await c.get("/api/tier", headers=u["h"])).json()["request"] is None

    # after Tier 2 is approved, the Tier 3 draft re-uses the approved BVN without tripping the uniqueness rule
    v = await make_user(c, Session)
    await add_photo(c, v); await verify_id(c, admin, v)
    vb = bvn_number()
    await put(c, v, target_tier=2, bvn=vb); await c.post("/api/tier/submit", headers=v["h"])
    r2 = await admin_row(c, admin, v)
    assert (await c.post(f"/api/admin/tier-requests/{r2['id']}/decision", headers=admin["h"], json={"decision": "approve"})).json()["user_tier"] == 2
    d = (await put(c, v, target_tier=3, address=ADDR, files=bill())).json()
    assert d["bvn_last4"] == vb[-4:] and d["missing"] == []
    assert (await c.post("/api/tier/submit", headers=v["h"])).status_code == 200
    r3 = await admin_row(c, admin, v)
    assert (await c.post(f"/api/admin/tier-requests/{r3['id']}/decision", headers=admin["h"], json={"decision": "approve"})).json()["user_tier"] == 3


@pytest.mark.asyncio
async def test_withdraw_one_open_request_and_bvn_belongs_to_one_customer(env, tmp_path, monkeypatch):
    from sqlalchemy import text
    from app.core.config import settings
    from app.models.user import UserRole
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    c, Session = env
    a, b = await make_user(c, Session), await make_user(c, Session)
    admin = await make_staff(c, Session, UserRole.admin)
    for u in (a, b):
        await add_photo(c, u)
    shared = bvn_number()
    assert (await c.delete("/api/tier/documents", headers=a["h"])).status_code == 404

    await put(c, a, target_tier=3, bvn=shared, address=ADDR, files=bill())
    assert (await c.post("/api/tier/submit", headers=a["h"])).status_code == 200
    clash = await put(c, b, target_tier=2, bvn=shared)                                 # a's BVN is under review: b cannot claim it
    assert clash.status_code == 409 and "already linked" in clash.json()["detail"]
    assert (await c.delete("/api/tier/documents", headers=a["h"])).json() == {"withdrawn": True}      # withdrawing a request under review
    assert doc_files(tmp_path) == [] and await admin_row(c, admin, a) is None
    assert (await put(c, b, target_tier=2, bvn=shared)).status_code == 200            # now it is free

    # several fast taps on "save" create exactly one draft
    w = await make_user(c, Session)
    rs = await asyncio.gather(*[put(c, w, target_tier=3) for _ in range(6)])
    assert all(r.status_code == 200 for r in rs), [r.text for r in rs if r.status_code != 200][:1]
    async with Session() as s:
        n = (await s.execute(text("SELECT count(*) FROM tier_requests WHERE user_id=:i AND status IN ('draft','pending')"), {"i": w["id"]})).scalar_one()
    assert n == 1


@pytest.mark.asyncio
async def test_a_rejected_or_missing_id_can_be_corrected_but_a_verified_one_cannot(env):
    from sqlalchemy import text
    from app.models.user import UserRole
    c, Session = env
    u = await make_user(c, Session)
    admin = await make_staff(c, Session, UserRole.admin)
    other = await make_user(c, Session)
    body = lambda **kw: {"id_type": "national_id", "id_number": "".join(random.choices("123456789", k=11)), "consent_id_processing": True, **kw}
    put_id = lambda who, **kw: c.put("/api/profile/identity", headers=who["h"], json=body(**kw))

    assert (await c.post(f"/api/admin/users/{u['id']}/kyc", headers=admin["h"], json={"decision": "reject", "note": "Number does not match"})).status_code == 200
    me = (await c.get("/api/auth/me", headers=u["h"])).json()
    assert me["kyc_status"] == "rejected"
    await add_photo(c, u)
    await put(c, u, target_tier=2, bvn=bvn_number())
    sub = await c.post("/api/tier/submit", headers=u["h"])
    assert sub.status_code == 400 and "ID number" in sub.json()["detail"]              # cannot submit on a rejected ID

    fixed = body()
    r = await c.put("/api/profile/identity", headers=u["h"], json=fixed)
    assert r.status_code == 200 and r.json()["kyc_status"] == "submitted" and r.json()["id_number_last4"] == fixed["id_number"][-4:]
    assert (await c.post("/api/tier/submit", headers=u["h"])).status_code == 200     # back in the queue, so it can go forward
    async with Session() as s:
        row = (await s.execute(text("SELECT id_number_enc, kyc_note FROM users WHERE id=:i"), {"i": u["id"]})).one()
    assert fixed["id_number"] not in row[0] and row[1] is None

    # refusals
    taken = body(id_number=fixed["id_number"])
    assert (await put_id(other, id_number=fixed["id_number"])).status_code == 409      # someone else's ID
    assert (await put_id(u, id_number="12345")).status_code == 422
    assert (await put_id(u, consent_id_processing=False)).status_code == 422
    assert (await put_id(u, id_type="passport")).status_code == 422
    assert (await c.put("/api/profile/identity", json=body())).status_code in (401, 403)
    await c.post(f"/api/admin/users/{u['id']}/kyc", headers=admin["h"], json={"decision": "verify"})
    locked = await put_id(u)
    assert locked.status_code == 403 and "already verified" in locked.json()["detail"]

    # a customer from before IDs were collected has none on file, and can add one
    legacy = await make_user(c, Session)
    async with Session() as s:
        await s.execute(text("UPDATE users SET id_type=NULL, id_number_enc=NULL, id_number_hash=NULL, id_number_last4=NULL, kyc_status='not_submitted' WHERE id=:i"), {"i": legacy["id"]}); await s.commit()
    assert (await c.get("/api/auth/me", headers=legacy["h"])).json()["kyc_status"] == "not_submitted"
    assert (await put_id(legacy)).json()["kyc_status"] == "submitted"
    async with Session() as s:
        audit = (await s.execute(text("SELECT coalesce(string_agg(action || ' ' || details::text, ' '),'') FROM audit_logs"))).scalar_one()
    assert "ID_RESUBMITTED" in audit and fixed["id_number"] not in audit
