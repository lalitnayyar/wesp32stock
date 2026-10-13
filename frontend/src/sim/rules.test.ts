import { describe, expect, it } from "vitest";
import refresh from "@shared/test_vectors/refresh_cases.json";
import rotation from "@shared/test_vectors/rotation_cases.json";
import header from "@shared/test_vectors/header_cases.json";
import fixture from "@shared/fixtures/dashboard_3page.json";
import fixtureBw from "@shared/fixtures/dashboard_3page_420_bw.json";
import fixtureBwr from "@shared/fixtures/dashboard_3page_420_bwr.json";
import fixture4c from "@shared/fixtures/dashboard_3page_420_4c.json";
import { computeRefresh, defaultConfig, formatAge, headerFooterOps, HeaderStatus, Op, PageRotator, panelSpec,
  RefreshGate, validateDashboard, validateField } from "./rules";
import { drawOp, Surface } from "./render";

describe("refresh safety (shared vectors)", () => {
  for (const c of refresh.cases) {
    it(c.name, () => {
      const r = computeRefresh(c.profile, c.requested);
      expect([r.effective_s, r.min_safe_s, r.refresh_gap_s, r.clamped, r.fallback]).toEqual(
        [c.effective, c.min_safe, c.refresh_gap, c.clamped, c.fallback]);
    });
  }
  it("verified panel: 10 s requested -> 60 s effective with reason", () => {
    const r = computeRefresh("JD79667_GDEY029F51H", 10);
    expect(r.requested_s).toBe(10);
    expect(r.effective_s).toBe(60);
    expect(r.reason).toContain("25 s");
  });
  for (const c of refresh.validation_cases) {
    it(`validate ${c.name}`, () => expect(validateField(c.field, c.input)).toEqual({ value: c.result, ok: c.ok }));
  }
  it("defaults", () => {
    const d = defaultConfig();
    expect(d.rotation_enabled).toBe(true);
    expect(d.page_duration_s).toBe(10);
  });
});

describe("rotation (shared vectors)", () => {
  for (const sc of rotation.scenarios) {
    it(sc.name, () => {
      const r = new PageRotator();
      r.init(sc.init.page_count, sc.init.page, sc.init.enabled, sc.init.effective_ms, sc.init.now);
      sc.steps.forEach((st: { op: string; now: number; arg?: number | boolean; page: number; redraw: boolean; error?: boolean }, i: number) => {
        let redraw = false, error = false;
        if (st.op === "tick") redraw = r.tick(st.now);
        else if (st.op === "next") redraw = r.next(st.now);
        else if (st.op === "goto") ({ changed: redraw, error } = r.goto(st.arg as number, st.now));
        else if (st.op === "pause") r.pause();
        else if (st.op === "resume") r.resume(st.now);
        else if (st.op === "set_count") redraw = r.setCount(st.arg as number, st.now);
        else if (st.op === "data") redraw = r.onData(st.arg as boolean, st.now);
        expect([i, r.page, redraw]).toEqual([i, st.page, st.redraw]);
        if (st.error !== undefined) expect(error).toBe(st.error);
      });
    });
  }
  it("refresh gate", () => {
    const g = new RefreshGate();
    g.gapMs = 30000;
    expect(g.canRefresh(0)).toBe(true);
    g.markStarted(1000);
    expect(g.msUntilAllowed(20000)).toBe(11000);
    expect(g.canRefresh(31000)).toBe(true);
  });
});

describe("header/footer ops (shared vectors)", () => {
  for (const a of header.age_cases) it(`age ${a.text}`, () => expect(formatAge(a.age_s)).toBe(a.text));
  for (const c of header.cases) {
    it(c.name, () => expect(headerFooterOps(c.status as HeaderStatus, (c as { profile?: string }).profile)).toEqual(c.ops));
  }
});

describe("fixture + renderer", () => {
  it("fixture is a valid 3-page dashboard", () => {
    expect(validateDashboard(fixture)).toBeNull();
    expect(fixture.pages.length).toBe(3);
  });
  it("rejects invalid responses", () => {
    expect(validateDashboard({ v: 2 })).not.toBeNull();
    expect(validateDashboard({ v: 1, pages: [], data_version: "x" })).toBe("bad page count");
  });
  it("renders all fixture ops inside the 168x384 canvas", () => {
    let maxX = 0, maxY = 0, pixels = 0;
    const s: Surface = { fillRect: (x, y, w, h) => { pixels++; maxX = Math.max(maxX, x + w); maxY = Math.max(maxY, y + h); } };
    for (const p of fixture.pages) for (const op of p.ops) drawOp(s, op as Op);
    expect(pixels).toBeGreaterThan(1000);
    expect(maxX).toBeLessThanOrEqual(168);
    expect(maxY).toBeLessThanOrEqual(384);
  });
  const panels: [string, unknown][] = [["SSD1683_GDEY042T81", fixtureBw], ["SSD1683_GDEY042Z98", fixtureBwr],
    ["HX8717_GDEY0420F51", fixture4c]];
  for (const [profile, fx] of panels) {
    it(`4.2in fixture for ${profile}: 400x300, inside the canvas, panel colours only`, () => {
      const spec = panelSpec(profile);
      expect(validateDashboard(fx, spec.layout)).toBeNull();
      expect(validateDashboard(fx)).toBe("layout is not 168x384");
      let maxX = 0, maxY = 0;
      const s: Surface = { fillRect: (x, y, w, h) => { maxX = Math.max(maxX, x + w); maxY = Math.max(maxY, y + h); } };
      for (const p of (fx as { pages: { ops: Op[] }[] }).pages) for (const op of p.ops) {
        drawOp(s, op, spec.layout);
        const col = op[0] === "F" || op[0] === "R" ? op[5] : op[4];
        expect(spec.palette).toContain(col);
      }
      expect(maxX).toBeLessThanOrEqual(400);
      expect(maxY).toBeLessThanOrEqual(spec.layout.body.bottom + 1);
    });
  }
  it("unknown panel profiles fall back to the 2.9in layout", () => {
    expect(panelSpec("BOGUS").layout.id).toBe("168x384");
    expect(panelSpec("SSD1683_GDEY042T81").roles.flag_bg).toBe("K");
  });
  it("draws the classic 'A' glyph like Adafruit GFX", () => {
    const px = new Set<string>();
    drawOp({ fillRect: (x, y) => px.add(`${x},${y}`) }, ["T", 0, 0, 1, "K", "A"]);
    // glyph 0x41 columns: 7C 12 11 12 7C
    expect(px.has("0,2") && px.has("2,0") && px.has("4,6") && !px.has("2,6")).toBe(true);
  });
});
