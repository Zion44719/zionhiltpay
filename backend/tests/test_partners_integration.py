"""Partner logos: public strip + admin management, against a REAL Postgres (skipped without TEST_DATABASE_URL)."""
import io
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_features_integration import env, make_staff, make_user, image_bytes  # noqa: E402,F401

TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="set TEST_DATABASE_URL to run DB integration tests")


def transparent_logo(size=(800, 400)):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", size, (0, 0, 0, 0))                                   # fully transparent background
    ImageDraw.Draw(im).rectangle((size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4), fill=(30, 90, 200, 255))
    out = io.BytesIO(); im.save(out, format="PNG"); return out.getvalue()


async def add(c, h, name, logo=None, **form):
    files = {"logo": ("logo.png", logo, "image/png")} if logo is not None else None
    return await c.post("/api/admin/partners", headers=h, data={"name": name, **{k: str(v) for k, v in form.items()}}, files=files)


async def public_names(c, mine):
    r = await c.get("/api/partners")                                              # NOTE: no login header at all
    assert r.status_code == 200
    return [p for p in r.json() if p["name"] in mine]


def logo_files(tmp_path):
    d = tmp_path / "logos"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


@pytest.mark.asyncio
async def test_partner_lifecycle_visibility_and_file_cleanup(env, tmp_path, monkeypatch):
    from PIL import Image
    from sqlalchemy import text
    from app.core.config import settings
    from app.models.user import UserRole
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    c, Session = env
    staff = await make_staff(c, Session, UserRole.admin)
    tag = uuid.uuid4().hex[:6]
    a, b, d = f"Alpha {tag}", f"Beta {tag}", f"Delta {tag}"

    ra = await add(c, staff["h"], a, logo=transparent_logo(), sort_order=50, website="https://alpha.example.com")
    rb = await add(c, staff["h"], b, sort_order=10)                                  # no logo: shown as a text name
    rd = await add(c, staff["h"], d, logo=transparent_logo((600, 600)), sort_order=30, is_active=False)
    assert ra.status_code == rb.status_code == rd.status_code == 201, (ra.text, rb.text, rd.text)
    A, B, D = ra.json(), rb.json(), rd.json()
    assert A["has_logo"] and not B["has_logo"] and A["is_active"] is True and D["is_active"] is False

    shown = await public_names(c, {a, b, d})
    assert [p["name"] for p in shown] == [b, a]                                      # active only, in the chosen order
    assert set(shown[0]) == {"id", "name", "website", "has_logo", "version"}         # no internal fields leak to the public
    assert shown[1]["website"] == "https://alpha.example.com"

    # the logo: public, a PNG, still transparent, scaled down
    r = await c.get(f"/api/partners/{A['id']}/logo")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and "public" in r.headers["cache-control"]
    im = Image.open(io.BytesIO(r.content))
    assert im.mode == "RGBA" and im.size[0] <= 480 and im.size[1] <= 240 and im.size == (480, 240)
    assert im.getpixel((2, 2))[3] == 0 and im.getpixel((im.size[0] // 2, im.size[1] // 2))[3] == 255, "transparency was lost"
    assert (await c.get(f"/api/partners/{B['id']}/logo")).status_code == 404         # no logo
    assert (await c.get(f"/api/partners/{D['id']}/logo")).status_code == 404         # hidden partner: logo not public either
    assert (await c.get(f"/api/partners/{uuid.uuid4()}/logo")).status_code == 404
    assert len(logo_files(tmp_path)) == 2 and all(n.endswith(".png") and len(n) == 36 for n in logo_files(tmp_path))

    # the admin screen can preview a hidden partner's logo; nobody else can
    pv = await c.get(f"/api/admin/partners/{D['id']}/logo", headers=staff["h"])
    assert pv.status_code == 200 and pv.headers["content-type"] == "image/png"
    assert (await c.get(f"/api/admin/partners/{D['id']}/logo")).status_code in (401, 403)
    assert (await c.get(f"/api/admin/partners/{B['id']}/logo", headers=staff["h"])).status_code == 404       # no logo uploaded

    # admin sees hidden partners; editing, re-activating and re-ordering
    listing = (await c.get("/api/admin/partners", headers=staff["h"])).json()
    assert D["id"] in [p["id"] for p in listing]
    r = await c.patch(f"/api/admin/partners/{D['id']}", headers=staff["h"], data={"is_active": "true", "sort_order": "5"})
    assert r.status_code == 200 and r.json()["is_active"] is True
    assert [p["name"] for p in await public_names(c, {a, b, d})] == [d, b, a]
    old = set(logo_files(tmp_path))
    r = await c.patch(f"/api/admin/partners/{A['id']}", headers=staff["h"], data={"name": f"Alpha Two {tag}"}, files={"logo": ("n.png", transparent_logo((300, 300)), "image/png")})
    assert r.status_code == 200 and r.json()["version"] >= A["version"]
    assert len(logo_files(tmp_path)) == 2 and len(set(logo_files(tmp_path)) - old) == 1, "replaced logo must delete the old file"
    r = await c.patch(f"/api/admin/partners/{A['id']}", headers=staff["h"], data={"remove_logo": "true"})
    assert r.json()["has_logo"] is False and len(logo_files(tmp_path)) == 1

    # delete removes the row and its file; unknown ids are 404
    assert (await c.delete(f"/api/admin/partners/{D['id']}", headers=staff["h"])).json() == {"deleted": True}
    assert logo_files(tmp_path) == []
    assert (await c.delete(f"/api/admin/partners/{D['id']}", headers=staff["h"])).status_code == 404
    assert (await c.patch(f"/api/admin/partners/{uuid.uuid4()}", headers=staff["h"], data={"name": "x y"})).status_code == 404

    async with Session() as s:
        audit = (await s.execute(text("SELECT coalesce(string_agg(action, ' '), '') FROM audit_logs"))).scalar_one()
    assert "PARTNER_CREATED" in audit and "PARTNER_UPDATED" in audit and "PARTNER_DELETED" in audit


@pytest.mark.asyncio
async def test_only_admins_can_manage_partners_but_anyone_can_view_them(env, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.models.user import UserRole
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    c, Session = env
    staff = await make_staff(c, Session, UserRole.admin)
    customer = await make_user(c, Session)
    p = (await add(c, staff["h"], f"Gamma {uuid.uuid4().hex[:6]}", logo=transparent_logo())).json()
    for who, label in ((customer["h"], "customer"), ({}, "anonymous")):
        assert (await c.get("/api/admin/partners", headers=who)).status_code in (401, 403), label
        assert (await c.get(f"/api/admin/partners/{p['id']}/logo", headers=who)).status_code in (401, 403), label
        assert (await add(c, who, "Sneaky Partner")).status_code in (401, 403), label
        assert (await c.patch(f"/api/admin/partners/{p['id']}", headers=who, data={"name": "Hacked"})).status_code in (401, 403), label
        assert (await c.delete(f"/api/admin/partners/{p['id']}", headers=who)).status_code in (401, 403), label
    assert (await c.get("/api/partners")).status_code == 200                          # the public strip needs no login
    assert (await c.get(f"/api/partners/{p['id']}/logo")).status_code == 200
    assert next(x for x in (await c.get("/api/admin/partners", headers=staff["h"])).json() if x["id"] == p["id"])["name"].startswith("Gamma")


@pytest.mark.asyncio
async def test_partner_input_validation_and_hostile_files(env, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.models.user import UserRole
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    c, Session = env
    staff = await make_staff(c, Session, UserRole.admin)
    h = staff["h"]
    before = len((await c.get("/api/admin/partners", headers=h)).json())

    assert (await add(c, h, "x")).status_code == 400 and (await add(c, h, "n" * 81)).status_code == 400
    for bad in ("javascript:alert(1)", "data:text/html,<script>1</script>", "ftp://files.example.com", "https://", "not a url", "https://a b.com", "https://" + "a" * 300):
        r = await add(c, h, "Valid Name", website=bad)
        assert r.status_code == 400, bad
    assert (await add(c, h, "Valid Name", sort_order=1000)).status_code == 400
    ok = await add(c, h, f"Zeta {uuid.uuid4().hex[:6]}", website="  https://zeta.example.com/path?x=1  ")
    assert ok.status_code == 201 and ok.json()["website"] == "https://zeta.example.com/path?x=1"       # trimmed

    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="80"><script>alert(document.cookie)</script><rect width="200" height="80"/></svg>'
    gif = image_bytes("GIF"); tiny = image_bytes("PNG", (10, 10)); huge = b"\x89PNG\r\n\x1a\n" + b"0" * (settings.MAX_LOGO_BYTES + 10)
    for label, data, code in (("svg with a script", svg, 400), ("plain text", b"this is not an image", 400), ("gif", gif, 400),
                              ("too small", tiny, 400), ("too large", huge, 413), ("truncated png", b"\x89PNG\r\n\x1a\n" + b"0" * 50, 400)):
        r = await add(c, h, "Valid Name", logo=data)
        assert r.status_code == code, (label, r.status_code)
    assert logo_files(tmp_path) == [], "a refused upload must leave no file behind"
    assert len((await c.get("/api/admin/partners", headers=h)).json()) == before + 1       # only the one valid partner was created

    # a name that looks like markup is just text: it comes back as plain JSON, never as HTML
    xss = "<img src=x onerror=alert(1)>"
    r = await add(c, h, xss)
    assert r.status_code == 201 and r.json()["name"] == xss and r.headers["content-type"].startswith("application/json")
