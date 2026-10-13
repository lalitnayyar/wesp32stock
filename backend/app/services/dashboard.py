"""Builds the compact ESP32 dashboard contract (docs/RENDER_CONTRACT.md).

The server paginates and lays out every page body as draw-ops so that the firmware and the
browser simulator render byte-identical pages. Header/footer (clock, Wi-Fi, API, page indicator)
are drawn on the device from the shared layout because only the device knows that state.

Two layouts exist: portrait 168x384 (2.9in 4-colour, shared/layout.json) and landscape 400x300
(4.2in panels, shared/layout_400x300.json). The panel profile picks the layout and the palette;
landscape pages only use colours the panel can show (black/white, +red, +yellow).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from .device_rules import layout, panel_spec, roles

UP, DOWN, FLAT = "\x1e", "\x1f", "="
DEFAULT_DISPLAY = {
    "rows_per_page": 8,
    "show_summary_page": True,
    "show_benchmarks_page": True,
    "page_order": ["summary", "holdings", "benchmarks"],
    "sort": "value",
}
DISCLAIMER = "Not financial advice. Market data may be delayed or inaccurate."


def _L():
    return layout()


def _right_x(text: str, size: int = 1) -> int:
    L = _L()
    return L["width"] - L["margin_x"] - len(text) * L["char_w"] * size


def _clip(text: str, n: int | None = None) -> str:
    n = n or _L()["limits"]["max_text_len"]
    text = "".join(ch if 32 <= ord(ch) < 127 or ch in (UP, DOWN) else "?" for ch in text)
    return text[:n]


def _dec(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def fmt_num(v, places: int | None = None, sep: bool = True) -> str:
    d = _dec(v)
    if d is None:
        return "--"
    if places is None:
        places = 4 if abs(d) < 1 and d != 0 else 2
    return f"{d:,.{places}f}" if sep else f"{d:.{places}f}"


def fmt_signed(v, places: int = 2, sep: bool = True) -> str:
    d = _dec(v)
    if d is None:
        return "--"
    txt = fmt_num(abs(d), places, sep)
    return ("-" if d < 0 else "+") + txt


def direction(v) -> int:
    d = _dec(v)
    if d is None or d == 0:
        return 0
    return 1 if d > 0 else -1


def _arrow(dirn: int) -> str:
    return UP if dirn > 0 else DOWN if dirn < 0 else FLAT


def _color(dirn: int) -> str:
    return "R" if dirn < 0 else "K"


def T(x, y, text, color="K", size=1):
    return ["T", int(x), int(y), size, color, _clip(text)]


def _title_ops(title: str) -> list:
    return [T(_L()["margin_x"], _L()["body"]["top"] + 2, title, "R")]


ROW_TOP = 68
ROW_H = 34


def _row_ops(i: int, sym: str, price_txt: str, left2: str, right2: str, dirn: int, stale: bool, last: bool,
             nodata: bool = False) -> list:
    m = _L()["margin_x"]
    y = ROW_TOP + i * ROW_H
    c = _color(dirn)
    price_txt = _clip(price_txt, 14)
    ops = [T(m, y, _clip(sym, 12)), T(_right_x(price_txt), y, price_txt)]
    if nodata:
        ops.append(T(m, y + 11, "no data", "R"))
    else:
        left2 = _clip(left2, 12)
        right2 = _clip(right2, 9)
        ops += [T(m, y + 11, left2, c), T(_right_x(right2), y + 11, right2, c)]
    if stale:
        ops += [["F", 79, y + 10, 34, 10, "Y"], T(81, y + 11, "STALE")]
    if not last:
        ops.append(["H", m, y + 25, _L()["width"] - 2 * m, "Y"])
    return ops


def holdings_page_ops(title: str, rows: list[dict], more: int = 0) -> list:
    ops = _title_ops(title)
    for i, r in enumerate(rows):
        dirn = direction(r.get("day_change_pct"))
        price = r.get("price")
        price_txt = (fmt_num(price) + " " + (r.get("currency") or "")).strip() if price is not None else "--"
        ops += _row_ops(i, r["ticker"], price_txt, f"{_arrow(dirn)} {fmt_signed(r.get('day_change'))}",
                        fmt_signed(r.get("day_change_pct")) + "%", dirn, bool(r.get("stale")),
                        last=(i == len(rows) - 1), nodata=price is None)
    if more:
        ops.append(T(_L()["margin_x"], _L()["body"]["bottom"] - 10, f"+{more} more holdings", "R"))
    return ops


def benchmarks_page_ops(rows: list[dict]) -> list:
    ops = _title_ops("BENCHMARKS")
    for i, r in enumerate(rows):
        dirn = direction(r.get("day_change_pct"))
        left = _arrow(dirn) + (f" 1Y {fmt_signed(r['ret_1y'], 1)}%" if r.get("ret_1y") is not None else "")
        ops += _row_ops(i, r["name"], fmt_num(r.get("level")) if r.get("level") else "--", left,
                        fmt_signed(r.get("day_change_pct")) + "%", dirn, bool(r.get("stale")),
                        last=(i == len(rows) - 1), nodata=r.get("level") is None)
    y = ROW_TOP + len(rows) * ROW_H + 4
    ops += [T(3, y, "Index levels only; not"), T(3, y + 10, "portfolio returns.")]
    return ops


def summary_page_ops(summary: dict | None, portfolio_name: str | None) -> list:
    m = _L()["margin_x"]
    ops = _title_ops("PORTFOLIO")
    if summary is None:
        ops += [T(m, 70, "No portfolio assigned", "R"), T(m, 82, "to this device.")]
    else:
        t = summary["totals"]
        ccy = summary["portfolio"]["base_currency"]
        ops.append(T(m, 68, portfolio_name or summary["portfolio"]["name"]))

        def big(y, label, value, color="K", pct=None):
            out = [T(m, y, label)]
            size = 2 if len(value) <= 13 else 1
            out.append(["T", m, y + 11, size, color, _clip(value)])
            if pct is not None:
                out.append(T(m, y + 11 + 8 * size + 2, pct, color))
            return out

        ops += big(82, f"Value ({ccy})", fmt_num(t["market_value"]))
        dday = direction(t["day_pl"])
        ops += big(116, "Today", fmt_signed(t["day_pl"]), _color(dday),
                   f"{_arrow(dday)} {fmt_signed(t['day_pct'])}%" if t["day_pct"] is not None else "--")
        dun = direction(t["unrealized_pl"])
        ops += big(160, "Unrealized", fmt_signed(t["unrealized_pl"]), _color(dun),
                   f"{_arrow(dun)} {fmt_signed(t['unrealized_pct'])}%" if t["unrealized_pct"] is not None else "--")
        ops.append(["H", m, 204, _L()["width"] - 2 * m, "Y"])
        ops.append(T(m, 210, f"Holdings: {t['active_holdings']}"))
        ops.append(T(m, 222, f"Invested: {fmt_num(t['invested'])}"))
        if summary.get("best"):
            b = summary["best"]
            ops.append(T(m, 236, f"Best : {b['ticker']} {fmt_signed(b['day_change_pct'])}%",
                         _color(direction(b["day_change_pct"]))))
        if summary.get("worst"):
            w = summary["worst"]
            ops.append(T(m, 248, f"Worst: {w['ticker']} {fmt_signed(w['day_change_pct'])}%",
                         _color(direction(w["day_change_pct"]))))
        stale = summary["freshness"]["stale_count"]
        if stale:
            ops += [["F", m, 262, 162, 11, "Y"], T(m + 2, 264, f"{stale} quote(s) stale")]
    ops += [T(m, 340, "Not financial advice."), T(m, 351, "Data may be delayed.")]
    return ops


# ----------------------------------------------------------------------------- landscape 400x300

class Landscape:
    """Page bodies for 400x300 panels. Two-line rows: size-2 symbol/price/% and a size-1 detail line."""

    ROW_TOP, ROW_H = 56, 28

    def __init__(self, L: dict, palette: str):
        self.L, self.c, self.m = L, roles(palette), L["margin_x"]

    def T(self, x, y, text, color="K", size=1):
        return ["T", int(x), int(y), size, color, _clip(text, self.L["limits"]["max_text_len"])]

    def right(self, text, size=1, edge=None):
        return (edge if edge is not None else self.L["width"] - self.m) - len(text) * self.L["char_w"] * size

    def col(self, dirn):
        return self.c["neg"] if dirn < 0 else "K"

    def title(self, text, note="", note_color="K"):
        ops = [self.T(self.m, 42, text, self.c["accent"])]
        if note:
            ops.append(self.T(self.right(note), 42, note, note_color))
        return ops

    def badge(self, x, y, text):
        w = len(text) * self.L["char_w"] + 4
        return [["F", x, y - 1, w, 10, self.c["flag_bg"]], self.T(x + 2, y, text, self.c["flag_fg"])]

    def row(self, i, name, price, pct, dirn, detail, mid="", mid_dir=0, right2="", stale=False, last=False,
            nodata=False):
        y = self.ROW_TOP + i * self.ROW_H
        name = _clip(name, 22)
        nsize = 2 if len(name) <= 8 else 1
        ops = [self.T(self.m, y if nsize == 2 else y + 4, name, "K", nsize)]
        price = _clip(price, 20)
        psize = 2 if len(price) <= 12 else 1
        ops.append(self.T(self.right(price, psize, 250), y if psize == 2 else y + 4, price, "K", psize))
        if nodata:
            ops.append(self.T(self.m, y + 18, "no data", self.c["neg"]))
        else:
            pct = _clip(pct, 12)
            psz = 2 if len(pct) <= 9 else 1
            ops.append(self.T(self.right(pct, psz), y if psz == 2 else y + 4, pct, self.col(dirn), psz))
            if detail:
                ops.append(self.T(self.m, y + 18, _clip(detail, 20)))
            if mid:
                ops.append(self.T(self.right(mid, 1, 250), y + 18, mid, self.col(mid_dir)))
            if right2:
                ops.append(self.T(self.right(right2), y + 18, right2, self.col(dirn)))
        if stale:
            ops += self.badge(130, y + 18, "STALE")
        if not last:
            ops.append(["H", self.m, y + 27, self.L["width"] - 2 * self.m, self.c["rule"]])
        return ops

    def holdings(self, title: str, rows: list[dict], more: int = 0) -> list:
        ops = self.title(title, f"+{more} more holdings" if more else "", self.c["neg"])
        for i, r in enumerate(rows):
            dirn = direction(r.get("day_change_pct"))
            price = r.get("price")
            price_txt = (fmt_num(price) + " " + (r.get("currency") or "")).strip() if price is not None else "--"
            pct = f"{_arrow(dirn)}{fmt_signed(r.get('day_change_pct'))}%"
            unrl = r.get("unrealized_pct")
            ops += self.row(i, r["ticker"], price_txt, pct, dirn, r.get("company") or "",
                            mid=f"P/L {fmt_signed(unrl)}%" if unrl is not None else "", mid_dir=direction(unrl),
                            right2=f"Day {fmt_signed(r.get('day_change'))}", stale=bool(r.get("stale")),
                            last=(i == len(rows) - 1), nodata=price is None)
        return ops

    def benchmarks(self, rows: list[dict]) -> list:
        ops = self.title("BENCHMARKS", "Index levels only; not portfolio returns.")
        for i, r in enumerate(rows):
            dirn = direction(r.get("day_change_pct"))
            rets = "  ".join(f"{k} {fmt_signed(r[f], 1)}%" for k, f in (("1M", "ret_1m"), ("YTD", "ret_ytd"),
                                                                        ("1Y", "ret_1y")) if r.get(f) is not None)
            ops += self.row(i, r["name"], fmt_num(r.get("level")) if r.get("level") else "--",
                            f"{_arrow(dirn)}{fmt_signed(r.get('day_change_pct'))}%", dirn, "",
                            stale=bool(r.get("stale")), last=(i == len(rows) - 1), nodata=r.get("level") is None)
            if rets and r.get("level") is not None:
                ops.append(self.T(self.m, self.ROW_TOP + i * self.ROW_H + 18, rets))
        return ops

    def summary(self, summary: dict | None, portfolio_name: str | None) -> list:
        m, c, W = self.m, self.c, self.L["width"]
        if summary is None:
            return self.title("PORTFOLIO") + [self.T(m, 60, "No portfolio assigned to this device.", c["neg"])]
        t = summary["totals"]
        ccy = summary["portfolio"]["base_currency"]
        ops = self.title("PORTFOLIO", _clip(portfolio_name or summary["portfolio"]["name"], 40))

        def big(y, label, value, color="K", pct=None):
            value = _clip(value, 30)
            size = 3 if len(value) <= 10 else 2 if len(value) <= 15 else 1
            out = [self.T(m, y, label), ["T", m, y + 11, size, color, value]]
            if pct is not None:
                out.append(self.T(m, y + 11 + 8 * size + 3, pct, color))
            return out

        ops += big(56, f"Value ({ccy})", fmt_num(t["market_value"]))
        dday = direction(t["day_pl"])
        ops += big(102, "Today", fmt_signed(t["day_pl"]), self.col(dday),
                   f"{_arrow(dday)} {fmt_signed(t['day_pct'])}%" if t["day_pct"] is not None else "--")
        dun = direction(t["unrealized_pl"])
        ops += big(160, "Unrealized", fmt_signed(t["unrealized_pl"]), self.col(dun),
                   f"{_arrow(dun)} {fmt_signed(t['unrealized_pct'])}%" if t["unrealized_pct"] is not None else "--")
        x2 = 236
        ops.append(["R", x2 - 6, 56, W - m - x2 + 6, 136, "K"])
        lines = [("Holdings", str(t["active_holdings"]), 0), ("Invested", fmt_num(t["invested"]), 0)]
        if t.get("realized_pl") is not None:
            lines.append(("Realized", fmt_signed(t["realized_pl"]), direction(t["realized_pl"])))
        lines += [(k, fmt_num(t[f]), 0) for k, f in (("Dividends", "dividends"), ("Cash", "cash"))
                  if t.get(f) is not None]
        for i, (k, v, d) in enumerate(lines):
            y = 62 + i * 13
            ops += [self.T(x2, y, k), self.T(self.right(v, 1, W - m - 4), y, v, self.col(d))]
        ops.append(["H", x2, 129, W - m - x2 - 4, c["rule"]])
        for i, key in enumerate(("best", "worst")):
            b = summary.get(key)
            if b:
                txt = f"{key.title():5}: {b['ticker']} {fmt_signed(b['day_change_pct'])}%"
                ops.append(self.T(x2, 136 + i * 13, txt, self.col(direction(b["day_change_pct"]))))
        stale = summary["freshness"]["stale_count"]
        if stale:
            ops += self.badge(x2, 172, f"{stale} quote(s) stale")
        ops += [["H", m, 252, W - 2 * m, c["rule"]], self.T(m, 262, "Not financial advice. Data may be delayed.")]
        return ops


def build_pages(summary: dict | None, bench_rows: list[dict], display: dict,
                panel_profile: str | None = None) -> list[dict]:
    spec = panel_spec(panel_profile)
    land = Landscape(spec["layout"], spec["palette"]) if spec["layout"]["id"] == "400x300" else None
    summary_ops = land.summary if land else summary_page_ops
    holdings_ops = land.holdings if land else holdings_page_ops
    bench_ops = land.benchmarks if land else benchmarks_page_ops
    cfg = {**DEFAULT_DISPLAY, **(display or {})}
    rpp = max(4, min(8, int(cfg["rows_per_page"])))
    max_pages = spec["layout"]["limits"]["max_pages"]
    holdings = list(summary["holdings"]) if summary else []
    sort = cfg.get("sort", "value")
    if sort == "ticker":
        holdings.sort(key=lambda r: r["ticker"])
    elif sort == "change":
        holdings.sort(key=lambda r: -float(r["day_change_pct"] or 0))
    else:
        holdings.sort(key=lambda r: -float(r["market_value_base"] or 0))

    order = [p for p in cfg["page_order"] if p in ("summary", "holdings", "benchmarks")] or DEFAULT_DISPLAY["page_order"]
    want = {"summary": cfg["show_summary_page"] or not holdings,
            "holdings": bool(holdings),
            "benchmarks": cfg["show_benchmarks_page"] and bool(bench_rows)}
    fixed = sum(1 for p in ("summary", "benchmarks") if want[p] and p in order)
    chunks = [holdings[i:i + rpp] for i in range(0, len(holdings), rpp)]
    allowed = max(0, max_pages - fixed)
    more = 0
    if len(chunks) > allowed:
        more = sum(len(c) for c in chunks[allowed:])
        chunks = chunks[:allowed]

    pages: list[dict] = []
    for kind in order:
        if not want[kind]:
            continue
        if kind == "summary":
            pages.append({"k": "summary", "ops": summary_ops(summary, summary["portfolio"]["name"] if summary else None)})
        elif kind == "holdings":
            n = len(chunks)
            for i, chunk in enumerate(chunks):
                title = "HOLDINGS" if n == 1 else f"HOLDINGS {i + 1}/{n}"
                pages.append({"k": "holdings", "ops": holdings_ops(title, chunk, more if i == n - 1 else 0)})
        elif kind == "benchmarks":
            pages.append({"k": "benchmarks", "ops": bench_ops(bench_rows[:min(rpp, 7)])})
    if not pages:
        pages.append({"k": "summary", "ops": summary_ops(summary, None)})
    return pages


def build_dashboard(*, summary: dict | None, bench_rows: list[dict], display: dict, device_uid: str,
                    device_name: str, tz: str, provider: str, now: datetime | None = None,
                    panel_profile: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    spec = panel_spec(panel_profile)
    pages = build_pages(summary, bench_rows, display, spec["profile"])
    holdings = summary["holdings"] if summary else []
    states = {h["market_state"] for h in holdings}
    market = "OPEN" if "OPEN" in states else "CLOSED" if states == {"CLOSED"} else "--"
    stale = any(h["stale"] for h in holdings)
    ages = [h["quote_age_s"] for h in holdings if h["quote_age_s"] is not None]
    status = {"market": market, "stale": stale, "delayed": True, "provider": provider,
              "quote_age_s": max(ages) if ages else None}
    version_src = json.dumps({"pages": pages, "status": {k: status[k] for k in ("market", "stale", "delayed")}},
                             sort_keys=True, separators=(",", ":"))
    return {
        "v": 1,
        "layout": spec["layout"]["id"],
        "data_version": hashlib.sha1(version_src.encode()).hexdigest()[:12],
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "tz": tz,
        "device": {"id": device_uid, "name": device_name},
        "status": status,
        "pages": pages,
        "disclaimer": DISCLAIMER,
    }


def validate_ops(dashboard: dict, panel_profile: str | None = None) -> list[str]:
    """Bounds/limits/palette check used by tests to guarantee firmware-safe output for the panel."""
    spec = panel_spec(panel_profile)
    L, palette = spec["layout"], spec["palette"]
    errs: list[str] = []
    if dashboard.get("layout") != L["id"]:
        errs.append(f"layout {dashboard.get('layout')} != {L['id']}")
    if len(dashboard["pages"]) > L["limits"]["max_pages"]:
        errs.append("too many pages")
    for pi, page in enumerate(dashboard["pages"]):
        if len(page["ops"]) > L["limits"]["max_ops_per_page"]:
            errs.append(f"page {pi}: too many ops")
        for op in page["ops"]:
            kind = op[0]
            if kind == "T":
                _, x, y, size, color, text = op
                w = len(text) * L["char_w"] * size
                h = L["char_h"] * size
                if len(text) > L["limits"]["max_text_len"]:
                    errs.append(f"page {pi}: text too long {text!r}")
            elif kind in ("F", "R"):
                _, x, y, w, h, color = op
            elif kind == "H":
                _, x, y, w, color = op
                h = 1
            else:
                errs.append(f"page {pi}: unknown op {kind}")
                continue
            if color not in palette:
                errs.append(f"page {pi}: bad color {color}")
            if x < 0 or y < L["body"]["top"] or x + w > L["width"] or y + h > L["body"]["bottom"] + 1:
                errs.append(f"page {pi}: op out of body bounds {op}")
    size = len(json.dumps(dashboard, separators=(",", ":")))
    if size > L["limits"]["max_response_bytes"]:
        errs.append(f"response too large: {size} bytes")
    return errs
