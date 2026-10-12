// Lalit Stock Application - simulator rules (mirror of firmware/LalitStockFirmware/logic.h and
// backend/app/services/device_rules.py). Verified against shared/test_vectors by rules.test.ts.
// Owner: Lalit Nayyar <consult@lalit.cloud>. Not financial advice.
import deviceConfig from "@shared/device_config.json";
import layout from "@shared/layout.json";
import panelProfiles from "@shared/panel_profiles.json";

export const LAYOUT = layout;
export const CONFIG_FIELDS = deviceConfig.fields as Record<string, FieldSpec>;
export const PANELS = panelProfiles as {
  fallback_s: number;
  profiles: Record<string, PanelProfile>;
};

export interface FieldSpec {
  type: "bool" | "int" | "enum" | "string";
  default: unknown;
  min?: number;
  max?: number;
  values?: string[];
  max_len?: number;
  description?: string;
}

export interface PanelProfile {
  label: string;
  full_refresh_ms: number;
  safety_margin_pct: number;
  min_dwell_s: number;
  verified: boolean;
  evidence: string;
  simulation_only: boolean;
}

export interface RefreshResult {
  profile: string;
  profileLabel: string;
  requested_s: number;
  effective_s: number;
  min_safe_s: number;
  refresh_gap_s: number;
  clamped: boolean;
  fallback: boolean;
  verified: boolean;
  reason: string;
  evidence: string;
}

export function computeRefresh(profileName: string, requested: number): RefreshResult {
  const prof = PANELS.profiles[profileName];
  let gap: number, minSafe: number;
  if (!prof) {
    gap = minSafe = PANELS.fallback_s;
  } else {
    // integer ceil identical to firmware: ceil(ms * (100 + margin) / 100000)
    gap = Math.ceil((prof.full_refresh_ms * (100 + prof.safety_margin_pct)) / 100000);
    minSafe = gap + prof.min_dwell_s;
  }
  const effective = Math.max(requested, minSafe);
  const clamped = effective !== requested;
  let reason: string;
  if (!prof) {
    reason = clamped
      ? `Panel timing unknown: conservative fallback minimum of ${minSafe} s applied.`
      : `Panel timing unknown; requested ${requested} s is above the ${minSafe} s fallback minimum.`;
  } else if (clamped) {
    reason =
      `Requested ${requested} s is below the hardware-safe minimum of ${minSafe} s: a full refresh takes up to ` +
      `${prof.full_refresh_ms / 1000} s (+${prof.safety_margin_pct}% margin) plus ${prof.min_dwell_s} s minimum reading time.`;
  } else {
    reason = `Requested ${requested} s is at or above the hardware-safe minimum of ${minSafe} s.`;
  }
  return {
    profile: profileName,
    profileLabel: prof ? prof.label : "Unknown panel/driver",
    requested_s: requested,
    effective_s: effective,
    min_safe_s: minSafe,
    refresh_gap_s: gap,
    clamped,
    fallback: !prof,
    verified: prof ? prof.verified : false,
    reason,
    evidence: prof ? prof.evidence : "No verified timing for this profile.",
  };
}

export function validateField(name: string, value: unknown): { value: unknown; ok: boolean } {
  const spec = CONFIG_FIELDS[name];
  if (!spec) throw new Error(`unknown field ${name}`);
  switch (spec.type) {
    case "bool":
      return typeof value === "boolean" ? { value, ok: true } : { value: spec.default, ok: false };
    case "int": {
      let v: number | null = null;
      if (typeof value === "number" && Number.isInteger(value)) v = value;
      else if (typeof value === "string" && /^[+-]?\d+$/.test(value.trim())) v = parseInt(value, 10);
      if (v === null) return { value: spec.default, ok: false };
      if (v < spec.min!) return { value: spec.min, ok: false };
      if (v > spec.max!) return { value: spec.max, ok: false };
      return { value: v, ok: true };
    }
    case "enum":
      return spec.values!.includes(value as string) ? { value, ok: true } : { value: spec.default, ok: false };
    case "string":
      return typeof value === "string" && value.length > 0 && value.length <= (spec.max_len ?? 64)
        ? { value, ok: true }
        : { value: spec.default, ok: false };
  }
}

export function defaultConfig(): Record<string, unknown> {
  return Object.fromEntries(Object.entries(CONFIG_FIELDS).map(([k, f]) => [k, f.default]));
}

/** Page rotation state machine - identical semantics to ls::PageRotator (millis()-style clock). */
export class PageRotator {
  page = 1;
  count = 1;
  enabled = true;
  lastChangeMs = 0;
  effectiveMs = 60000;

  init(count: number, page: number, enabled: boolean, effectiveMs: number, now: number) {
    this.count = Math.max(1, count);
    this.page = page < 1 || page > this.count ? 1 : page;
    this.enabled = enabled;
    this.effectiveMs = effectiveMs;
    this.lastChangeMs = now;
  }
  msUntilNext(now: number) {
    if (!this.enabled || this.count <= 1) return 0;
    const el = now - this.lastChangeMs;
    return el >= this.effectiveMs ? 0 : this.effectiveMs - el;
  }
  tick(now: number) {
    if (!this.enabled || this.count <= 1) return false;
    if (now - this.lastChangeMs < this.effectiveMs) return false;
    this.page = (this.page % this.count) + 1;
    this.lastChangeMs = now;
    return true;
  }
  next(now: number) {
    const before = this.page;
    this.page = (this.page % this.count) + 1;
    this.lastChangeMs = now;
    return this.page !== before;
  }
  goto(target: number, now: number): { changed: boolean; error: boolean } {
    if (!Number.isInteger(target) || target < 1 || target > this.count) return { changed: false, error: true };
    const before = this.page;
    this.page = target;
    this.lastChangeMs = now;
    return { changed: this.page !== before, error: false };
  }
  pause() {
    this.enabled = false;
  }
  resume(now: number) {
    this.enabled = true;
    this.lastChangeMs = now;
  }
  setCount(n: number, now: number) {
    this.count = Math.max(1, n);
    if (this.page > this.count) {
      this.page = 1;
      this.lastChangeMs = now;
      return true;
    }
    return false;
  }
  onData(resetToFirst: boolean, now: number) {
    if (resetToFirst && this.page !== 1) {
      this.page = 1;
      this.lastChangeMs = now;
    }
    return true;
  }
}

export class RefreshGate {
  everRefreshed = false;
  lastStartMs = 0;
  gapMs = 30000;
  canRefresh(now: number) {
    return !this.everRefreshed || now - this.lastStartMs >= this.gapMs;
  }
  msUntilAllowed(now: number) {
    return this.canRefresh(now) ? 0 : this.gapMs - (now - this.lastStartMs);
  }
  markStarted(now: number) {
    this.everRefreshed = true;
    this.lastStartMs = now;
  }
}

// ---------------------------------------------------------------- draw-ops

export type Op =
  | ["T", number, number, number, string, string]
  | ["F" | "R", number, number, number, number, string]
  | ["H", number, number, number, string];

export interface HeaderStatus {
  datetime: string | null;
  last_ok: string | null;
  wifi: boolean;
  api: "OK" | "ERR" | "OFF";
  market: string;
  flag: "" | "STALE" | "CACHED" | "DELAYED";
  page: number;
  pages: number;
  age_s: number | null;
  offline: boolean;
}

export function formatAge(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 172800) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

const clip = (t: string) => t.slice(0, LAYOUT.limits.max_text_len);
const rightX = (t: string, size = 1) => LAYOUT.width - LAYOUT.margin_x - t.length * LAYOUT.char_w * size;

export function headerFooterOps(s: HeaderStatus): Op[] {
  const L = LAYOUT,
    H = L.header,
    m = L.margin_x;
  const ops: Op[] = [
    ["F", 0, 0, L.width, H.bar_h, "R"],
    ["T", m, H.title_y, 1, "W", H.title],
    s.datetime ? ["T", m, H.datetime_y, 1, "K", clip(s.datetime)] : ["T", m, H.datetime_y, 1, "R", "NO TIME SYNC"],
    ["T", m, H.status_y, 1, "K", `Upd ${s.last_ok ?? "--:--"}`],
    ["T", H.wifi_x, H.status_y, 1, s.wifi ? "K" : "R", s.wifi ? "WiFi:OK" : "WiFi:--"],
    ["T", H.api_x, H.status_y, 1, s.api === "OK" ? "K" : "R", `API:${s.api}`],
    ["T", m, H.market_y, 1, "K", `Mkt:${s.market || "--"}`],
  ];
  if (s.flag) {
    const w = s.flag.length * L.char_w + 4;
    const x = L.width - m - w;
    ops.push(["F", x, H.market_y - 2, w, 11, "Y"], ["T", x + 2, H.market_y, 1, "K", s.flag]);
  }
  ops.push(["H", 0, H.sep_y, L.width, "K"], ["H", 0, L.footer.sep_y, L.width, "K"]);
  ops.push(["T", m, L.footer.text_y, 1, "K", `PAGE ${s.page}/${s.pages}`]);
  const age = s.age_s === null || s.age_s < 0 ? "--" : formatAge(s.age_s);
  const txt = s.offline ? `OFFLINE ${age}` : `Age ${age}`;
  ops.push(["T", rightX(txt), L.footer.text_y, 1, s.offline ? "R" : "K", txt]);
  return ops;
}

export interface Dashboard {
  v: number;
  data_version: string;
  generated_at: string;
  tz: string;
  device: { id: string; name: string };
  status: { market: string; stale: boolean; delayed: boolean; provider?: string; quote_age_s?: number | null };
  pages: { k: string; ops: Op[] }[];
  disclaimer?: string;
}

/** Same structural validation as the firmware (net_client.cpp validDashboard). */
export function validateDashboard(d: unknown): string | null {
  const x = d as Dashboard;
  if (!x || typeof x !== "object" || x.v !== 1) return "unsupported contract version";
  if (!Array.isArray(x.pages) || x.pages.length < 1 || x.pages.length > LAYOUT.limits.max_pages) return "bad page count";
  for (const p of x.pages) {
    if (!Array.isArray(p.ops) || p.ops.length > LAYOUT.limits.max_ops_per_page) return "bad ops";
    for (const op of p.ops) if (!["T", "F", "R", "H"].includes(op?.[0] as string)) return "unknown op";
  }
  if (typeof x.data_version !== "string") return "missing data_version";
  return null;
}
