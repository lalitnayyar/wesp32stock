"""Second panel family: WeAct 4.2in 400x300 (B/W, B/W/R, 4-colour) alongside the 2.9in 4-colour portrait panel."""
import json
from pathlib import Path

import pytest

from app.services import device_rules
from app.services.dashboard import build_dashboard, validate_ops
from tests.test_api import _device_with_key, _setup_portfolio

ROOT = Path(__file__).resolve().parents[2]
FIX = json.loads((ROOT / "shared/fixtures/portfolio_fixture.json").read_text())
LANDSCAPE = ["SSD1683_GDEY042T81", "SSD1683_GDEY042Z98", "HX8717_GDEY0420F51"]


def _dash(profile, **display):
    return build_dashboard(summary=FIX["summary"], bench_rows=FIX["benchmarks"], display={**FIX["display"], **display},
                           device_uid="X", device_name="X", tz="UTC", provider="fixture", panel_profile=profile)


@pytest.mark.parametrize("profile", LANDSCAPE)
@pytest.mark.parametrize("rows", [4, 8])
def test_landscape_pages_fit_the_panel_and_its_palette(profile, rows):
    d = _dash(profile, rows_per_page=rows)
    assert d["layout"] == "400x300"
    assert validate_ops(d, profile) == []
    palette = device_rules.panel_spec(profile)["palette"]
    used = {op[5] if op[0] in "FR" else op[4] for p in d["pages"] for op in p["ops"]}
    assert used <= set(palette)


def test_black_white_panel_never_gets_red_or_yellow():
    d = _dash("SSD1683_GDEY042T81")
    colours = {op[5] if op[0] in "FR" else op[4] for p in d["pages"] for op in p["ops"]}
    assert colours <= {"K", "W"} and "K" in colours


def test_portrait_output_unchanged_by_default():
    a, b = _dash(None), _dash("JD79667_GDEY029F51H")
    assert a == b and a["layout"] == "168x384"
    # the generated 2.9in fixture still matches the portrait builder
    assert validate_ops(a) == []


def test_unknown_profile_falls_back_to_portrait():
    assert device_rules.panel_spec("BOGUS")["layout"]["id"] == "168x384"
    assert device_rules.panel_spec(None)["profile"] == "JD79667_GDEY029F51H"


def test_layout_mismatch_is_reported():
    d = _dash("SSD1683_GDEY042Z98")
    assert any("layout" in e for e in validate_ops(d, "JD79667_GDEY029F51H"))


def test_refresh_safety_for_new_panels():
    bw = device_rules.compute_refresh("SSD1683_GDEY042T81", 10)
    assert (bw.min_safe_s, bw.effective_s, bw.verified) == (32, 32, False)
    bwr = device_rules.compute_refresh("SSD1683_GDEY042Z98", 10)
    assert bwr.effective_s == 60
    c4 = device_rules.compute_refresh("HX8717_GDEY0420F51", 10)
    assert c4.effective_s == 66


def test_device_reports_panel_and_gets_landscape_layout(admin):
    pf, *_ = _setup_portfolio(admin)
    dev, k = _device_with_key(admin, pf["id"])
    hdr = {"Authorization": f"Bearer {k['key']}"}
    # old firmware: no panel parameter -> portrait
    assert admin.c.get("/api/v1/device/dashboard", headers=hdr).json()["layout"] == "168x384"
    r = admin.c.get("/api/v1/device/dashboard?panel=SSD1683_GDEY042Z98", headers=hdr)
    assert r.status_code == 200 and r.json()["layout"] == "400x300"
    d = admin.get("/api/v1/devices").json()[0]
    assert d["reported"]["panel_profile"] == "SSD1683_GDEY042Z98"
    # the admin preview follows the reported panel, and can be switched explicitly
    assert admin.get(f"/api/v1/devices/{dev['id']}/preview").json()["layout"] == "400x300"
    p = admin.get(f"/api/v1/devices/{dev['id']}/preview?panel=JD79667_GDEY029F51H").json()
    assert p["layout"] == "168x384" and p["panel_profile"] == "JD79667_GDEY029F51H"
    # an unknown panel name is ignored rather than stored
    admin.c.get("/api/v1/device/dashboard?panel=NOPE", headers=hdr)
    assert admin.get("/api/v1/devices").json()[0]["reported"]["panel_profile"] == "SSD1683_GDEY042Z98"


@pytest.mark.parametrize("profile,layout", [(None, "168x384"), ("SSD1683_GDEY042T81", "400x300"),
                                            ("HX8717_GDEY0420F51", "400x300")])
def test_simulator_fixture_per_panel(admin, profile, layout):
    q = f"?panel={profile}" if profile else ""
    r = admin.get(f"/api/v1/simulator/fixture{q}")
    assert r.status_code == 200 and r.json()["layout"] == layout


def test_register_device_with_module(admin):
    pf, *_ = _setup_portfolio(admin)
    base = {"device_uid": "LS-420", "name": "Big", "portfolio_id": pf["id"]}
    bad = admin.post("/api/v1/devices", json={**base, "display_config": {"panel_profile": "TEST_FAST_PANEL"}})
    assert bad.status_code == 422
    r = admin.post("/api/v1/devices", json={**base, "display_config": {"panel_profile": "SSD1683_GDEY042T81"}})
    assert r.status_code == 201, r.text
    dev = r.json()
    assert dev["panel_profile"] == "SSD1683_GDEY042T81" and not dev["panel_mismatch"]
    # before first contact the preview uses the registered module
    assert admin.get(f"/api/v1/devices/{dev['id']}/preview").json()["layout"] == "400x300"
    k = admin.post("/api/v1/api-keys", json={"name": "k", "device_id": dev["id"]}).json()
    hdr = {"Authorization": f"Bearer {k['key']}"}
    # the device without a panel parameter (old firmware) still gets its registered module's layout
    assert admin.c.get("/api/v1/device/dashboard", headers=hdr).json()["layout"] == "400x300"
    # the device's own firmware panel wins, and the mismatch is flagged
    assert admin.c.get("/api/v1/device/dashboard?panel=JD79667_GDEY029F51H", headers=hdr).json()["layout"] == "168x384"
    d = admin.get("/api/v1/devices").json()[0]
    assert d["panel_profile"] == "JD79667_GDEY029F51H" and d["panel_registered"] == "SSD1683_GDEY042T81"
    assert d["panel_mismatch"] is True


def test_modules_are_the_four_real_panels():
    assert list(device_rules.modules()) == ["JD79667_GDEY029F51H", "SSD1683_GDEY042T81", "SSD1683_GDEY042Z98",
                                            "HX8717_GDEY0420F51"]
