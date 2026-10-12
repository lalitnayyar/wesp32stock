"""Shared-contract tests: the same vectors are run by the simulator (vitest) and firmware (g++ host test)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services import device_rules
from app.services.dashboard import build_dashboard, validate_ops

ROOT = Path(__file__).resolve().parents[2]
VEC = json.loads((ROOT / "shared/test_vectors/refresh_cases.json").read_text())
FIX = json.loads((ROOT / "shared/fixtures/portfolio_fixture.json").read_text())


@pytest.mark.parametrize("case", VEC["cases"], ids=lambda c: c["name"])
def test_refresh_vectors(case):
    r = device_rules.compute_refresh(case["profile"], case["requested"])
    assert (r.effective_s, r.min_safe_s, r.refresh_gap_s, r.clamped, r.fallback) == (
        case["effective"], case["min_safe"], case["refresh_gap"], case["clamped"], case["fallback"])
    assert r.requested_s == case["requested"]
    if r.clamped:
        assert str(r.min_safe_s) in r.reason


def test_verified_panel_10s_is_clamped_to_60_with_reason():
    r = device_rules.compute_refresh("JD79667_GDEY029F51H", 10)
    assert r.requested_s == 10 and r.effective_s == 60 and r.verified
    assert "25 s" in r.reason and "60 s" in r.reason


@pytest.mark.parametrize("case", VEC["validation_cases"], ids=lambda c: c["name"])
def test_validation_vectors(case):
    assert device_rules.validate_field(case["field"], case["input"]) == (case["result"], case["ok"])


def test_defaults_rotation_enabled_10s():
    cfg = device_rules.default_config()
    assert cfg["rotation_enabled"] is True and cfg["page_duration_s"] == 10 and cfg["selected_page"] == 1


def test_validate_config_rejects_malformed():
    cfg, warn = device_rules.validate_config({"page_duration_s": "x", "rotation_enabled": "yes", "selected_page": -3,
                                             "panel_profile": "BOGUS"})
    assert cfg["page_duration_s"] == 10 and cfg["rotation_enabled"] is True and cfg["selected_page"] == 1
    assert cfg["panel_profile"] == "JD79667_GDEY029F51H"
    assert set(warn) == {"page_duration_s", "rotation_enabled", "selected_page", "panel_profile"}


def _fixture_dash(**display):
    return build_dashboard(summary=FIX["summary"], bench_rows=FIX["benchmarks"], display={**FIX["display"], **display},
                           device_uid="X", device_name="X", tz="Asia/Dubai", provider="fixture")


def test_fixture_three_pages_and_bounds():
    d = _fixture_dash()
    assert [p["k"] for p in d["pages"]] == ["summary", "holdings", "benchmarks"]
    assert validate_ops(d) == []


def test_pagination_splits_holdings_and_respects_options():
    d = _fixture_dash(rows_per_page=4)
    kinds = [p["k"] for p in d["pages"]]
    assert kinds == ["summary", "holdings", "holdings", "benchmarks"]
    titles = [op[5] for p in d["pages"] for op in p["ops"] if op[0] == "T" and op[2] == 56]
    assert "HOLDINGS 1/2" in titles and "HOLDINGS 2/2" in titles
    d2 = _fixture_dash(show_summary_page=False, show_benchmarks_page=False)
    assert [p["k"] for p in d2["pages"]] == ["holdings"]
    assert validate_ops(d2) == []


def test_many_holdings_capped_at_max_pages():
    many = dict(FIX["summary"])
    many["holdings"] = [{**FIX["summary"]["holdings"][0], "ticker": f"T{i:03d}"} for i in range(80)]
    d = build_dashboard(summary=many, bench_rows=FIX["benchmarks"], display={"rows_per_page": 4}, device_uid="X",
                        device_name="X", tz="UTC", provider="fixture")
    assert len(d["pages"]) == 8
    assert validate_ops(d) == []
    assert any("more holdings" in op[5] for op in d["pages"][-2]["ops"] if op[0] == "T")


def test_data_version_stable_and_content_sensitive():
    a, b = _fixture_dash(), _fixture_dash()
    assert a["data_version"] == b["data_version"]
    changed = json.loads(json.dumps(FIX))
    changed["summary"]["holdings"][0]["price"] = "190.0000"
    c = build_dashboard(summary=changed["summary"], bench_rows=FIX["benchmarks"], display=FIX["display"],
                        device_uid="X", device_name="X", tz="Asia/Dubai", provider="fixture")
    assert c["data_version"] != a["data_version"]


def test_no_portfolio_assigned_page():
    d = build_dashboard(summary=None, bench_rows=[], display={}, device_uid="X", device_name="X", tz="UTC", provider="f")
    assert len(d["pages"]) == 1
    assert any(op[0] == "T" and "No portfolio" in op[5] for op in d["pages"][0]["ops"])


def test_generated_files_up_to_date():
    r = subprocess.run([sys.executable, str(ROOT / "tools/gen_shared.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
