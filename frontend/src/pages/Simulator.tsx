// Docker-served E-Paper simulator (development/QA only). Mirrors the ESP32 firmware contract:
// same shared config schema, same dashboard payload, same rotation/refresh rules (src/sim/rules.ts),
// same header/footer ops and pixel renderer. It does NOT reproduce ghosting, wear, power, BUSY timing
// or thermal behaviour - those remain hardware-in-the-loop concerns.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { get, post, put } from "../api";
import EPaperCanvas, { ColorLegend } from "../components/EPaperCanvas";
import { ErrorBox, Field, Notice, useAction } from "../components/ui";
import {
  CONFIG_FIELDS, computeRefresh, Dashboard, headerFooterOps, HeaderStatus, MODULES, PageRotator, PANELS, panelSpec, RefreshGate,
  validateDashboard, validateField,
} from "../sim/rules";

type Cfg = Record<string, any>;
interface Faults { wifi_down: boolean; api_offline: boolean; stale: boolean; delay_s: number; invalid: boolean; ntp_fail: boolean }
const NO_FAULTS: Faults = { wifi_down: false, api_offline: false, stale: false, delay_s: 0, invalid: false, ntp_fail: false };
const FW = "SIM-1.0.0";
const SIM_SCAN = [{ ssid: "Simulated-WiFi", rssi: -52 }, { ssid: "Office-2.4G", rssi: -67 }, { ssid: "Guest", rssi: -80 }];

interface Sim {
  bootMs: number;
  rot: PageRotator;
  gate: RefreshGate;
  dash: Dashboard | null;
  pendingDraw: boolean;
  api: "OK" | "ERR" | "OFF";
  lastOkMs: number | null;
  lastOkWall: Date | null;
  lastError: string;
  fetchCount: number;
  fetchOk: number;
  inFlight: boolean;
  lastFetchAttempt: number;
  fetchFailures: number;
  lastHb: number;
  hbCount: number;
  refreshCount: number;
  pageChanges: number;
  drawnVersion: string;
  busyUntil: number;
  drawnApi: string;
}

const millisNow = () => performance.now();

function newSim(): Sim {
  return { bootMs: millisNow(), rot: new PageRotator(), gate: new RefreshGate(), dash: null, pendingDraw: true, api: "OFF",
    lastOkMs: null, lastOkWall: null, lastError: "", fetchCount: 0, fetchOk: 0, inFlight: false, lastFetchAttempt: -1e12,
    fetchFailures: 0, lastHb: 0, hbCount: 0, refreshCount: 0, pageChanges: 0, drawnVersion: "", busyUntil: 0, drawnApi: "" };
}

function fmtTime(d: Date, tz: string, withDate: boolean) {
  const safeTz = (() => { try { new Intl.DateTimeFormat("en", { timeZone: tz }); return tz; } catch { return "Asia/Dubai"; } })();
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: safeTz, day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })
    .formatToParts(d).reduce<Record<string, string>>((a, p) => ({ ...a, [p.type]: p.value }), {});
  return withDate ? `${parts.day} ${parts.month} ${parts.year} ${parts.hour}:${parts.minute}` : `${parts.hour}:${parts.minute}`;
}

export default function SimulatorPage() {
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [draft, setDraft] = useState<Cfg | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [faults, setFaults] = useState<Faults>(NO_FAULTS);
  const [portfolios, setPortfolios] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scale, setScale] = useState(2);
  const [gotoInput, setGotoInput] = useState("");
  const [msg, setMsg] = useState<{ text: string; bad?: boolean } | null>(null);
  const [scan, setScan] = useState<typeof SIM_SCAN>([]);
  const [, force] = useState(0);
  const sim = useRef<Sim>(newSim());
  const cfgRef = useRef<Cfg | null>(null);
  const faultsRef = useRef<Faults>(NO_FAULTS);
  const shown = useRef<{ header: any[]; body: any[] | null; waiting: boolean }>({ header: [], body: null, waiting: true });
  const act = useAction();
  cfgRef.current = cfg;
  faultsRef.current = faults;

  const refresh = useMemo(() => (cfg ? computeRefresh(cfg.panel_profile, cfg.page_duration_s) : null), [cfg]);

  const logEvent = useCallback((kind: string, message: string) => {
    post("/api/v1/simulator/events", { kind, message }).catch(() => undefined);
  }, []);
  const loadEvents = useCallback(() => get("/api/v1/simulator/events?limit=40").then(setEvents).catch(() => undefined), []);
  const persistRuntime = useCallback(() => {
    const s = sim.current;
    put("/api/v1/simulator/runtime", { selected_page: s.rot.page, rotation_enabled: s.rot.enabled, faults: faultsRef.current,
      fetch_count: s.fetchCount, refresh_count: s.refreshCount }).catch(() => undefined);
  }, []);

  // ---------------------------------------------------------------- boot / restart (like an ESP32 reboot)
  const boot = useCallback(async () => {
    try {
      const r = await get("/api/v1/simulator/config");
      const c = r.config;
      sim.current = newSim();
      const ref = computeRefresh(c.panel_profile, c.page_duration_s);
      sim.current.rot.init(1, c.selected_page, c.rotation_enabled, ref.effective_s * 1000, 0);
      sim.current.gate.gapMs = ref.refresh_gap_s * 1000;
      setCfg(c);
      setDraft(c);
      setFaults({ ...NO_FAULTS, ...(r.runtime?.faults ?? {}) });
      setError(null);
      logEvent("restart", `Simulation booted: page ${c.selected_page}, rotation ${c.rotation_enabled ? "on" : "off"}, requested ${ref.requested_s}s effective ${ref.effective_s}s`);
    } catch (e: any) {
      setError(e.message);
    }
  }, [logEvent]);

  useEffect(() => {
    boot();
    get("/api/v1/portfolios").then(setPortfolios).catch(() => undefined);
    loadEvents();
    const t = setInterval(loadEvents, 5000);
    return () => clearInterval(t);
  }, [boot, loadEvents]);

  // ---------------------------------------------------------------- independent fetch (never triggered by rotation)
  const doFetch = useCallback(async (reason: string) => {
    const s = sim.current, c = cfgRef.current, f = faultsRef.current;
    if (!c || s.inFlight) return;
    s.inFlight = true;
    s.fetchCount++;
    s.lastFetchAttempt = millisNow() - s.bootMs;
    const finish = (ok: boolean, err = "") => {
      s.inFlight = false;
      const prev = s.api;
      if (ok) { s.api = "OK"; s.fetchOk++; s.lastOkMs = millisNow() - s.bootMs; s.lastOkWall = new Date(); s.lastError = ""; s.fetchFailures = 0; }
      else { s.api = f.wifi_down || f.api_offline ? "OFF" : "ERR"; s.lastError = err; s.fetchFailures++; }
      if (prev !== s.api) logEvent("connection", `API ${prev} -> ${s.api}${err ? `: ${err}` : ""}`);
      logEvent("fetch", `${reason}: ${ok ? "OK" : err}`);
      force((x) => x + 1);
    };
    try {
      if (f.delay_s > 0) await new Promise((r) => setTimeout(r, f.delay_s * 1000));
      if (f.wifi_down) return finish(false, "Wi-Fi not connected");
      if (f.api_offline) return finish(false, "connection failed: simulated API offline");
      let data: any;
      const panel = encodeURIComponent(c.panel_profile);
      if (c.mode === "live") {
        const q = new URLSearchParams({ rows: String(c.rows_per_page), summary: String(c.show_summary_page), bench: String(c.show_benchmarks_page), panel: c.panel_profile });
        if (c.portfolio_id) q.set("portfolio_id", String(c.portfolio_id));
        data = await get(`/api/v1/simulator/dashboard?${q}`);
      } else {
        data = await get(`/api/v1/simulator/fixture?panel=${panel}`);
      }
      if (f.invalid) data = { v: 1, layout: panelSpec(c.panel_profile).layout.id, pages: "corrupted", data_version: 42 };
      const why = validateDashboard(data, panelSpec(c.panel_profile).layout);
      if (why) return finish(false, `invalid response: ${why}`);
      if (f.stale) data = { ...data, status: { ...data.status, stale: true } };
      const now = millisNow() - s.bootMs;
      const oldVer = s.dash?.data_version ?? "";
      s.dash = data;
      if (s.rot.setCount(data.pages.length, now)) s.pendingDraw = true;
      if (data.data_version !== oldVer && s.rot.onData(c.reset_page_on_data, now)) s.pendingDraw = true;
      finish(true);
    } catch (e: any) {
      finish(false, e.message ?? "request failed");
    }
  }, [logEvent]);

  // ---------------------------------------------------------------- main loop (rotation, redraw gate, timers)
  useEffect(() => {
    const t = setInterval(() => {
      const s = sim.current, c = cfgRef.current;
      if (!c || !refresh) return;
      const now = millisNow() - s.bootMs;
      s.rot.effectiveMs = refresh.effective_s * 1000;
      s.gate.gapMs = refresh.refresh_gap_s * 1000;
      // fetch timer with the firmware's backoff rule
      let interval = c.fetch_interval_s * 1000;
      if (s.fetchFailures) interval = Math.min(interval, 30000 * 2 ** Math.min(5, s.fetchFailures - 1));
      if (!s.inFlight && now - s.lastFetchAttempt >= interval) doFetch("scheduled fetch");
      // heartbeat timer (simulated; recorded only)
      if (now - s.lastHb >= c.heartbeat_interval_s * 1000) { s.lastHb = now; s.hbCount++; }
      // rotation timer
      if (s.rot.tick(now)) { s.pendingDraw = true; s.pageChanges++; logEvent("page_change", `auto -> page ${s.rot.page}/${s.rot.count}`); persistRuntime(); }
      if (s.drawnApi && s.drawnApi !== s.api) s.pendingDraw = true;
      if (s.pendingDraw && s.gate.canRefresh(now)) {
        s.pendingDraw = false;
        s.gate.markStarted(now);
        s.refreshCount++;
        s.drawnApi = s.api;
        s.busyUntil = now + (PANELS.profiles[c.panel_profile]?.full_refresh_ms ?? 25000);
        s.drawnVersion = s.dash?.data_version ?? "";
        shown.current = render(s, c);
        s.rot.lastChangeMs = now; // firmware restarts the dwell timer after the blocking refresh
      }
      force((x) => x + 1);
    }, 250);
    return () => clearInterval(t);
  }, [refresh, doFetch, logEvent, persistRuntime]);

  function render(s: Sim, c: Cfg) {
    const f = faultsRef.current;
    const now = millisNow() - s.bootMs;
    const offline = s.api !== "OK";
    const st: HeaderStatus = {
      datetime: f.ntp_fail ? null : fmtTime(new Date(), c.timezone, true),
      last_ok: s.lastOkWall && !f.ntp_fail ? fmtTime(s.lastOkWall, c.timezone, false) : null,
      wifi: !f.wifi_down,
      api: s.api,
      market: s.dash?.status.market ?? "--",
      flag: !s.dash ? "" : offline ? "CACHED" : s.dash.status.stale ? "STALE" : s.dash.status.delayed ? "DELAYED" : "",
      page: s.rot.page,
      pages: s.rot.count,
      age_s: s.lastOkMs === null ? null : Math.floor((now - s.lastOkMs) / 1000),
      offline,
    };
    // A dashboard laid out for another panel (just after switching panels) is never drawn, as on the ESP32.
    const dash = s.dash && (s.dash.layout ?? "168x384") === panelSpec(c.panel_profile).layout.id ? s.dash : null;
    return { header: headerFooterOps(st, c.panel_profile), body: dash ? (dash.pages[s.rot.page - 1]?.ops as any[]) ?? null : null, waiting: !dash };
  }

  // ---------------------------------------------------------------- controls
  const say = (text: string, bad = false) => setMsg({ text, bad });
  const queued = () => {
    const s = sim.current, now = millisNow() - s.bootMs;
    const w = s.gate.msUntilAllowed(now);
    return w ? ` (queued behind refresh guard: ${Math.ceil(w / 1000)} s)` : "";
  };
  const control = (action: string, arg?: string) => {
    const s = sim.current, now = millisNow() - s.bootMs;
    if (action === "pause") { s.rot.pause(); say(`Rotation paused on page ${s.rot.page}`); }
    if (action === "resume") { s.rot.resume(now); say(`Rotation resumed; next change in ${refresh?.effective_s} s`); }
    if (action === "next") { if (s.rot.next(now)) s.pendingDraw = true; say(`Showing page ${s.rot.page}/${s.rot.count}${queued()}`); }
    if (action === "first" || action === "goto") {
      const target = action === "first" ? 1 : (validateField("selected_page", arg ?? "").ok ? Number(arg) : NaN);
      const r = s.rot.goto(target, now);
      if (r.error) return say(`Page must be a whole number between 1 and ${s.rot.count}`, true);
      if (r.changed) s.pendingDraw = true;
      say(`Showing page ${s.rot.page}/${s.rot.count}${queued()}`);
    }
    logEvent("control", `${action}${arg ? ` ${arg}` : ""} -> page ${s.rot.page}, rotation ${s.rot.enabled ? "on" : "paused"}`);
    persistRuntime();
    force((x) => x + 1);
  };

  const saveConfig = async () => {
    if (!draft) return;
    const body: Cfg = { ...draft };
    if (apiKeyInput) body.api_key = apiKeyInput;
    const r: any = await act.run(() => put("/api/v1/simulator/config", { config: body, runtime: { faults } }));
    if (r) {
      setCfg(r.config);
      setDraft(r.config);
      setApiKeyInput("");
      const s = sim.current;
      if (r.config.rotation_enabled !== s.rot.enabled) r.config.rotation_enabled ? s.rot.resume(millisNow() - s.bootMs) : s.rot.pause();
      const warn = Object.values(r.warnings ?? {});
      say(warn.length ? `Saved with corrections: ${warn.join("; ")}` : `Saved. Requested ${r.refresh.requested_s}s → effective ${r.refresh.effective_s}s`, warn.length > 0);
      doFetch("config saved");
      loadEvents();
    }
  };

  // Switching the E-Paper module is like reflashing the ESP32 with another build: save and reboot.
  const switchModule = async (profile: string) => {
    if (!cfg || profile === cfg.panel_profile) return;
    const r: any = await act.run(() => put("/api/v1/simulator/config", { config: { ...cfg, panel_profile: profile }, runtime: { faults } }));
    if (r) {
      logEvent("module", `E-Paper module -> ${PANELS.profiles[profile]?.module ?? profile}`);
      await boot();
      say(`Now simulating ${PANELS.profiles[profile]?.module}: requested ${r.refresh.requested_s}s → effective ${r.refresh.effective_s}s`);
    }
  };

  if (error) return <ErrorBox error={error} />;
  if (!cfg || !draft || !refresh) return <div>Loading simulator…</div>;
  const s = sim.current;
  const now = millisNow() - s.bootMs;
  const spec = panelSpec(cfg.panel_profile);
  const draftRefresh = computeRefresh(draft.panel_profile, validateField("page_duration_s", Number(draft.page_duration_s)).value as number);
  const set = (k: string, v: any) => setDraft({ ...draft, [k]: v });
  const num = (k: string) => (
    <Field label={`${k.replace(/_/g, " ")} (${CONFIG_FIELDS[k].min}-${CONFIG_FIELDS[k].max})`}>
      <input className="input" type="number" value={draft[k]} onChange={(e) => set(k, e.target.value === "" ? "" : Number(e.target.value))} />
    </Field>
  );
  const bool = (k: string, label: string) => (
    <Field label={label}><select className="input" value={draft[k] ? "1" : "0"} onChange={(e) => set(k, e.target.value === "1")}><option value="1">Yes / On</option><option value="0">No / Off</option></select></Field>
  );

  return (
    <div>
      <div className="bg-amber-400 text-black font-semibold px-3 py-2 rounded mb-3">Simulation mode — no physical E-Paper connected (testing/QA only)</div>
      {msg && <div className={`text-sm mb-2 ${msg.bad ? "text-red-700" : "text-emerald-700"}`}>{msg.text}</div>}
      <div className="card mb-3">
        <div className="text-sm font-semibold mb-1">E-Paper module</div>
        <div className="flex flex-wrap gap-1">
          {MODULES.map((m, i) => (
            <button key={m.profile} type="button" disabled={act.busy}
              className={m.profile === cfg.panel_profile ? "btn" : "btn-alt"} onClick={() => switchModule(m.profile)}>
              {i + 1}. {m.name}
            </button>
          ))}
        </div>
        <p className="text-xs text-stone-500 mt-1">Same four options as Register device and the flash_esp32 wizard. Switching reboots the simulation with that panel's layout, colours and refresh timing.</p>
      </div>
      <div className="grid xl:grid-cols-[auto_1fr] gap-4">
        {/* ---------------- preview column */}
        <div>
          <div className="flex gap-4 items-start">
            <EPaperCanvas header={shown.current.header} body={shown.current.body} waiting={shown.current.waiting} scale={1} layout={spec.layout} label={`Exact ${spec.layout.width} × ${spec.layout.height}`} />
            {spec.layout.width < 300 && <EPaperCanvas header={shown.current.header} body={shown.current.body} waiting={shown.current.waiting} scale={scale} layout={spec.layout} label={`Scaled ×${scale} (same pixels)`} />}
          </div>
          {spec.layout.width >= 300 && (
            <div className="mt-2"><EPaperCanvas header={shown.current.header} body={shown.current.body} waiting={shown.current.waiting} scale={scale} layout={spec.layout} label={`Scaled ×${scale} (same pixels)`} /></div>
          )}
          <div className="text-xs text-stone-600 mt-1">Panel: {PANELS.profiles[spec.profile]?.label ?? spec.profile} · {spec.layout.width > spec.layout.height ? "landscape" : "portrait"} · palette {spec.palette}
            {PANELS.profiles[spec.profile]?.build && <> · firmware build <code>{PANELS.profiles[spec.profile].build}</code></>}</div>
          <div className="flex gap-2 items-center mt-2 text-sm">
            Zoom <input type="range" min={1} max={3} value={scale} onChange={(e) => setScale(Number(e.target.value))} />
          </div>
          <ColorLegend palette={spec.palette} />
          <div className="card mt-3">
            <h2 className="h2">Page controls (same as ESP32 admin page)</h2>
            <div className="text-sm mb-2">
              <b>PAGE {s.rot.page}/{s.rot.count}</b> · {s.rot.enabled ? <span className="pos">rotation running</span> : <span className="neg">paused</span>}
              {s.rot.enabled && s.rot.count > 1 && <> · next change in {Math.ceil(s.rot.msUntilNext(now) / 1000)} s</>}
              {s.pendingDraw && <> · redraw queued ({Math.ceil(s.gate.msUntilAllowed(now) / 1000)} s)</>}
              {now < s.busyUntil && <span className="badge-warn ml-1">simulated BUSY {Math.ceil((s.busyUntil - now) / 1000)} s</span>}
            </div>
            <div className="flex flex-wrap gap-1">
              <button className="btn" disabled={!s.rot.enabled} onClick={() => control("pause")}>Pause</button>
              <button className="btn" disabled={s.rot.enabled} onClick={() => control("resume")}>Resume</button>
              <button className="btn" onClick={() => control("next")}>Next page</button>
              <button className="btn-alt" onClick={() => control("first")}>Page 1</button>
              <input className="input w-24" type="number" min={1} max={s.rot.count} placeholder="Page #" value={gotoInput} onChange={(e) => setGotoInput(e.target.value)} />
              <button className="btn" onClick={() => control("goto", gotoInput)}>Go to page</button>
            </div>
          </div>
        </div>

        {/* ---------------- admin column */}
        <div className="min-w-0">
          <div className="card">
            <h2 className="h2">Refresh safety</h2>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>Requested page duration</div><b>{refresh.requested_s} s</b>
              <div>Effective hardware-safe duration</div><b className={refresh.clamped ? "neg" : "pos"}>{refresh.effective_s} s{refresh.clamped && " (clamped)"}</b>
              <div>Panel / driver assumption</div><span>{refresh.profileLabel} {refresh.verified ? <span className="badge-ok">verified</span> : <span className="badge-warn">unverified</span>}</span>
              <div>Min. gap between full refreshes</div><span>{refresh.refresh_gap_s} s</span>
            </div>
            <Notice kind={refresh.clamped ? "warn" : "ok"}>{refresh.reason}</Notice>
            <p className="text-xs text-stone-500">Evidence: {refresh.evidence}</p>
          </div>

          <div className="card mt-3">
            <h2 className="h2">Simulated ESP32 administration</h2>
            <div className="grid md:grid-cols-3 gap-x-3">
              <Field label="Device ID"><input className="input" value={draft.device_id} onChange={(e) => set("device_id", e.target.value)} /></Field>
              <Field label="Device name"><input className="input" value={draft.device_name} onChange={(e) => set("device_name", e.target.value)} /></Field>
              <Field label="Data source">
                <select className="input" value={draft.mode} onChange={(e) => set("mode", e.target.value)}>
                  <option value="fixture">Fixture (no API key needed)</option><option value="live">Live (same payload as /device/dashboard)</option>
                </select>
              </Field>
              {draft.mode === "live" && (
                <Field label="Portfolio (live mode)">
                  <select className="input" value={draft.portfolio_id ?? ""} onChange={(e) => set("portfolio_id", e.target.value ? Number(e.target.value) : null)}>
                    <option value="">— none —</option>{portfolios.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </Field>
              )}
              <Field label="Wi-Fi SSID">
                <div className="flex gap-1"><input className="input" list="simnets" value={draft.wifi_ssid} onChange={(e) => set("wifi_ssid", e.target.value)} />
                  <button className="btn-alt" type="button" onClick={() => { setScan(SIM_SCAN); logEvent("scan", "simulated network scan"); }}>Scan</button></div>
                <datalist id="simnets">{scan.map((n) => <option key={n.ssid} value={n.ssid}>{n.rssi} dBm</option>)}</datalist>
              </Field>
              <Field label="Stock API URL"><input className="input" value={draft.api_url} onChange={(e) => set("api_url", e.target.value)} /></Field>
              <Field label={`Device API key (${cfg.api_key_set ? "saved - masked" : "not set"})`}>
                <input className="input" type="password" autoComplete="off" placeholder={cfg.api_key_set ? "••••••••  (blank = keep)" : "not required in fixture mode"} value={apiKeyInput} onChange={(e) => setApiKeyInput(e.target.value)} />
              </Field>
              {num("fetch_interval_s")}
              {num("api_timeout_ms")}
              {num("heartbeat_interval_s")}
              {bool("rotation_enabled", "Automatic page rotation")}
              {num("page_duration_s")}
              {num("selected_page")}
              {num("rows_per_page")}
              {bool("show_summary_page", "Summary page")}
              {bool("show_benchmarks_page", "Benchmarks page")}
              {bool("reset_page_on_data", "Reset to page 1 on new data")}
              <Field label="Orientation (fixed by the panel)"><input className="input" readOnly value={panelSpec(draft.panel_profile).layout.width > panelSpec(draft.panel_profile).layout.height ? "landscape 400 × 300" : "portrait 168 × 384"} /></Field>
              <Field label="Panel profile">
                <select className="input" value={draft.panel_profile} onChange={(e) => set("panel_profile", e.target.value)}>
                  {(CONFIG_FIELDS.panel_profile.values ?? []).map((p) => <option key={p} value={p}>{PANELS.profiles[p]?.label ?? p}{PANELS.profiles[p]?.simulation_only ? " (simulation only)" : ""}</option>)}
                </select>
              </Field>
              <Field label="Timezone"><input className="input" value={draft.timezone} onChange={(e) => set("timezone", e.target.value)} /></Field>
              <Field label="POSIX TZ"><input className="input" value={draft.posix_tz} onChange={(e) => set("posix_tz", e.target.value)} /></Field>
              <Field label="NTP server"><input className="input" value={draft.ntp_server} onChange={(e) => set("ntp_server", e.target.value)} /></Field>
            </div>
            <p className="text-xs mt-2">Preview of this draft: requested {draftRefresh.requested_s} s → effective <b>{draftRefresh.effective_s} s</b>{draftRefresh.clamped && " (clamped)"}.</p>
            {act.view}
            <div className="flex flex-wrap gap-1 mt-2">
              <button className="btn" onClick={saveConfig} disabled={act.busy}>Save configuration</button>
              <button className="btn-alt" onClick={() => boot().then(() => say("Persisted configuration reloaded"))}>Reload persisted</button>
              <button className="btn-alt" onClick={() => say(faults.wifi_down ? "Test Wi-Fi failed: simulated Wi-Fi down" : `Wi-Fi OK: ${draft.wifi_ssid} (simulated -55 dBm)`, faults.wifi_down)}>Test Wi-Fi</button>
              <button className="btn-alt" onClick={() => doFetch("test API").then(() => say(sim.current.api === "OK" ? "API OK" : `API test failed: ${sim.current.lastError}`, sim.current.api !== "OK"))}>Test API</button>
              <button className="btn-alt" onClick={() => boot().then(() => say("Simulation restarted (like an ESP32 reboot)"))}>Restart simulation</button>
              <button className="btn-danger" onClick={async () => { if (confirm("Reset the simulator? This clears saved simulator configuration and events (real devices are not affected).")) { await act.run(() => post("/api/v1/simulator/reset", { confirm: true })); boot(); loadEvents(); } }}>Reset simulator</button>
            </div>
          </div>

          <div className="card mt-3">
            <h2 className="h2">Fault injection</h2>
            <div className="flex flex-wrap gap-4 text-sm">
              {([["wifi_down", "Wi-Fi down"], ["api_offline", "API offline"], ["stale", "Stale data"], ["invalid", "Invalid response"], ["ntp_fail", "NTP failure"]] as const).map(([k, l]) => (
                <label key={k} className="flex gap-1 items-center">
                  <input type="checkbox" checked={faults[k]} onChange={(e) => { const nf = { ...faults, [k]: e.target.checked }; setFaults(nf); faultsRef.current = nf; logEvent("fault", `${l} ${e.target.checked ? "on" : "off"}`); persistRuntime(); sim.current.pendingDraw = true; }} />{l}
                </label>
              ))}
              <label className="flex gap-1 items-center">Response delay (s)
                <input className="input w-20" type="number" min={0} max={60} value={faults.delay_s} onChange={(e) => setFaults({ ...faults, delay_s: Math.max(0, Math.min(60, Number(e.target.value))) })} />
              </label>
              <button className="btn-alt" onClick={() => doFetch("manual fetch")}>Fetch now</button>
            </div>
            <p className="text-xs text-stone-500 mt-1">Rotation keeps running while a delayed fetch is pending; page changes never trigger fetches.</p>
          </div>

          <div className="card mt-3">
            <h2 className="h2">Diagnostics</h2>
            <div className="grid md:grid-cols-3 gap-2 text-sm">
              <div>Firmware <b>{FW}</b></div>
              <div>Uptime <b>{Math.floor(now / 1000)} s</b></div>
              <div>Wi-Fi <b>{faults.wifi_down ? "disconnected" : `${cfg.wifi_ssid} (-55 dBm)`}</b></div>
              <div>API <b className={s.api === "OK" ? "pos" : "neg"}>{s.api}</b></div>
              <div>Fetches (ok/total) <b>{s.fetchOk}/{s.fetchCount}</b></div>
              <div>Page changes <b>{s.pageChanges}</b></div>
              <div>Display refreshes <b>{s.refreshCount}</b></div>
              <div>Heartbeats <b>{s.hbCount}</b></div>
              <div>Last fetch <b>{s.lastFetchAttempt < 0 ? "never" : `${Math.floor((now - s.lastFetchAttempt) / 1000)} s ago`}</b></div>
              <div>Cached data age <b>{s.lastOkMs === null ? "—" : `${Math.floor((now - s.lastOkMs) / 1000)} s`}</b></div>
              <div>Displayed data version <b>{s.drawnVersion || "—"}</b></div>
              <div>NTP <b>{faults.ntp_fail ? "failed" : `${cfg.timezone} synced`}</b></div>
              <div className="md:col-span-3 text-red-700">{s.lastError}</div>
            </div>
          </div>

          <div className="card mt-3 overflow-x-auto">
            <h2 className="h2">Simulation events</h2>
            <table className="tbl"><tbody>{events.map((e) => (
              <tr key={e.id}><td className="text-xs">{new Date(e.ts).toLocaleTimeString()}</td><td><span className="badge">{e.kind}</span></td><td className="text-xs">{e.message}</td></tr>))}</tbody></table>
          </div>
        </div>
      </div>
    </div>
  );
}
