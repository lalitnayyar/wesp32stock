import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ago, del, get, post, put } from "../api";
import EPaperCanvas, { ColorLegend } from "../components/EPaperCanvas";
import { ErrorBox, Field, Modal, Notice, useAction, useLoad } from "../components/ui";
import { headerFooterOps, MODULES, PANELS, panelSpec } from "../sim/rules";

export function ModuleSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
      {MODULES.map((m, i) => <option key={m.profile} value={m.profile}>{i + 1}. {m.name}</option>)}
    </select>
  );
}
import { CreateKeyForm, ShowKeyOnce } from "./ApiKeys";

function DeviceForm({ initial, prefill, portfolios, onDone }: any) {
  const [f, setF] = useState<any>(initial ?? { device_uid: prefill?.device_uid ?? "", name: "", portfolio_id: "", display_config: { rows_per_page: 8, show_summary_page: true, show_benchmarks_page: true, page_order: ["summary", "holdings", "benchmarks"], sort: "value", panel_profile: prefill?.panel_profile ?? MODULES[0].profile } });
  const act = useAction();
  const dc = f.display_config;
  const setDc = (k: string, v: any) => setF({ ...f, display_config: { ...dc, [k]: v } });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = { ...f, portfolio_id: f.portfolio_id ? Number(f.portfolio_id) : null };
    const r = await act.run(() => (f.id ? put(`/api/v1/devices/${f.id}`, { name: body.name, portfolio_id: body.portfolio_id, display_config: dc }) : post("/api/v1/devices", body)));
    if (r) onDone();
  };
  return (
    <form onSubmit={submit}>
      <Field label="Device ID (shown on the setup screen, e.g. LS-A1B2C3)"><input className="input" value={f.device_uid} disabled={!!f.id} onChange={(e) => setF({ ...f, device_uid: e.target.value })} required /></Field>
      <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
      <Field label="Assigned portfolio (enforced by the server)">
        <select className="input" value={f.portfolio_id ?? ""} onChange={(e) => setF({ ...f, portfolio_id: e.target.value })}>
          <option value="">— none —</option>{portfolios.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </Field>
      <Field label="E-Paper module (flash the ESP32 with the same option in flash_esp32)">
        <ModuleSelect value={dc.panel_profile ?? MODULES[0].profile} onChange={(v) => setDc("panel_profile", v)} />
      </Field>
      <p className="text-xs text-stone-500 -mt-1 mb-1">
        {(() => { const s = panelSpec(dc.panel_profile); const i = MODULES.findIndex((m) => m.profile === s.profile);
          return <>{s.layout.width} × {s.layout.height} {s.layout.width > s.layout.height ? "landscape" : "portrait"} · colours {s.palette} · firmware build <code>{MODULES[i]?.build}</code> (wizard option {i + 1}, or <code>firmware\flash.bat COMx {MODULES[i]?.build}</code>)</>; })()}
      </p>
      <div className="grid grid-cols-2 gap-x-3">
        <Field label="Rows per page (4-8)"><input className="input" type="number" min={4} max={8} value={dc.rows_per_page} onChange={(e) => setDc("rows_per_page", Number(e.target.value))} /></Field>
        <Field label="Holding order"><select className="input" value={dc.sort} onChange={(e) => setDc("sort", e.target.value)}><option value="value">By value</option><option value="ticker">By ticker</option><option value="change">By daily change</option></select></Field>
        <Field label="Summary page"><select className="input" value={dc.show_summary_page ? "1" : "0"} onChange={(e) => setDc("show_summary_page", e.target.value === "1")}><option value="1">Show</option><option value="0">Hide</option></select></Field>
        <Field label="Benchmarks page"><select className="input" value={dc.show_benchmarks_page ? "1" : "0"} onChange={(e) => setDc("show_benchmarks_page", e.target.value === "1")}><option value="1">Show</option><option value="0">Hide</option></select></Field>
        <Field label="Page order">
          <select className="input" value={dc.page_order.join(",")} onChange={(e) => setDc("page_order", e.target.value.split(","))}>
            {["summary,holdings,benchmarks", "holdings,summary,benchmarks", "holdings,benchmarks,summary", "benchmarks,summary,holdings"].map((o) => <option key={o} value={o}>{o.replace(/,/g, " → ")}</option>)}
          </select>
        </Field>
      </div>
      {act.view}
      <button className="btn mt-3" disabled={act.busy}>Save</button>
    </form>
  );
}

function Preview({ device }: { device: any }) {
  const [panel, setPanel] = useState<string>(device.panel_profile ?? "");
  const { data, error } = useLoad(() => get(`/api/v1/devices/${device.id}/preview${panel ? `?panel=${encodeURIComponent(panel)}` : ""}`), [device.id, panel]);
  const [page, setPage] = useState(1);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <div>Rendering…</div>;
  const n = data.pages.length;
  const spec = panelSpec(data.panel_profile);
  const p = Math.min(page, n);
  const header = headerFooterOps({ datetime: "-- preview --", last_ok: null, wifi: true, api: "OK", market: data.status.market,
    flag: data.status.stale ? "STALE" : data.status.delayed ? "DELAYED" : "", page: p, pages: n, age_s: 0, offline: false }, spec.profile);
  return (
    <div className="text-center">
      <div className="flex justify-center items-center gap-2 mb-2 text-sm">Panel
        <select className="input max-w-sm" value={spec.profile} onChange={(e) => setPanel(e.target.value)}>
          {MODULES.map((m) => <option key={m.profile} value={m.profile}>{m.name}{m.profile === device.reported?.panel_profile ? " (reported by device)" : m.profile === device.panel_registered ? " (registered)" : ""}</option>)}
        </select>
      </div>
      <EPaperCanvas header={header} body={data.pages[p - 1].ops} scale={2} layout={spec.layout} label={`Server payload preview · ${spec.layout.width} × ${spec.layout.height} · data version ${data.data_version}`} />
      <div className="flex justify-center gap-1 mt-2">{data.pages.map((pg: any, i: number) => (
        <button key={i} className={i + 1 === p ? "btn" : "btn-alt"} onClick={() => setPage(i + 1)}>{i + 1}: {pg.k}</button>))}</div>
      <div className="mt-2"><ColorLegend palette={spec.palette} /></div>
    </div>
  );
}

export default function DevicesPage() {
  const { data, error, reload } = useLoad(() => Promise.all([get("/api/v1/devices"), get("/api/v1/portfolios")]));
  const [modal, setModal] = useState<any>(null);
  const [shownKey, setShownKey] = useState<any>(null);
  const act = useAction();
  const [params, setParams] = useSearchParams();
  // Arriving from "Flash ESP32" -> "Register LS-xxxxxx with this module": open the form pre-filled.
  useEffect(() => {
    const uid = params.get("register");
    if (uid) {
      const mod = params.get("module");
      setModal({ edit: {}, prefill: { device_uid: uid, panel_profile: MODULES.some((m) => m.profile === mod) ? mod : undefined } });
      setParams({}, { replace: true });
    }
  }, [params, setParams]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <div>Loading…</div>;
  const [devices, pfs] = data;
  return (
    <div>
      <div className="flex items-center mb-3"><h1 className="h1 mb-0">E-Paper Devices</h1><button className="btn ml-auto" onClick={() => setModal({ edit: {} })}>Register device</button></div>
      <Notice>Workflow: register the device ID shown on the ESP32 setup screen → assign a portfolio → generate a device API key → enter the API URL and key on the ESP32 administration page (http://192.168.4.1 during setup).</Notice>
      {act.view}
      <div className="grid lg:grid-cols-2 gap-3">
        {devices.map((d: any) => {
          const r = d.reported ?? {};
          const rc = d.refresh_check;
          return (
            <div key={d.id} className="card">
              <div className="flex items-center gap-2">
                <b>{d.name}</b><span className="font-mono text-xs">{d.device_uid}</span>
                {d.online ? <span className="badge-ok">online</span> : <span className="badge-bad">offline</span>}
                <span className="ml-auto text-xs text-stone-500">{pfs.find((p: any) => p.id === d.portfolio_id)?.name ?? "no portfolio"}</span>
              </div>
              <div className="grid grid-cols-2 text-xs gap-x-3 gap-y-0.5 mt-2">
                <span>Firmware</span><span>{d.firmware ?? "—"}</span>
                <span>Heartbeat</span><span>{ago(d.last_heartbeat_at)}</span>
                <span>Last fetch</span><span>{ago(d.last_fetch_at)}</span>
                <span>Wi-Fi RSSI</span><span>{d.rssi ?? "—"} dBm</span>
                <span>Uptime</span><span>{d.uptime_s ? `${Math.floor(d.uptime_s / 3600)} h ${Math.floor((d.uptime_s % 3600) / 60)} m` : "—"}</span>
                <span>API status</span><span>{d.api_status ?? "—"}</span>
                <span>Data version</span><span className="font-mono">{d.data_version ?? "—"}</span>
                <span>Page</span><span>{r.page ? `${r.page}/${r.pages} · rotation ${r.rotation_enabled ? "on" : "paused"}` : "—"}</span>
                <span>Page duration</span><span>{rc ? <>requested {rc.requested_s}s → effective <b>{rc.effective_s}s</b>{rc.clamped && <span className="badge-warn ml-1">clamped</span>}</> : "—"}</span>
                <span>E-Paper module</span><span>{PANELS.profiles[d.panel_profile]?.module ?? d.panel_profile}{r.panel_profile ? "" : " (registered; not reported yet)"}</span>
                <span>Display refreshes</span><span>{r.refresh_count ?? "—"}</span>
                <span>Last error</span><span className="text-red-700">{r.last_error || "—"}</span>
              </div>
              {rc?.clamped && <p className="text-xs text-amber-800 mt-1">{rc.reason}</p>}
              {d.panel_mismatch && <p className="text-xs text-red-700 mt-1">Registered as {PANELS.profiles[d.panel_registered]?.module}, but the device runs firmware for {PANELS.profiles[r.panel_profile]?.module}. The device's own panel is used; update the registration or reflash with the matching module.</p>}
              <div className="mt-2 space-x-1">
                <button className="btn-alt" onClick={() => setModal({ preview: d })}>Preview</button>
                <button className="btn-alt" onClick={() => setModal({ edit: d })}>Configure</button>
                <button className="btn-alt" onClick={() => setModal({ key: d })}>New API key</button>
                <button className="btn-danger" onClick={() => confirm(`Delete ${d.name}? Its API keys will be revoked.`) && act.run(() => del(`/api/v1/devices/${d.id}`)).then(reload)}>Delete</button>
              </div>
            </div>
          );
        })}
      </div>
      {devices.length === 0 && <p className="text-sm text-stone-500">No devices registered.</p>}
      {modal?.edit && <Modal title={modal.edit.id ? `Configure ${modal.edit.name}` : "Register device"} onClose={() => setModal(null)}>
        <DeviceForm initial={modal.edit.id ? modal.edit : undefined} prefill={modal.prefill} portfolios={pfs} onDone={() => { setModal(null); reload(); }} /></Modal>}
      {modal?.preview && <Modal wide title={`Display preview: ${modal.preview.name}`} onClose={() => setModal(null)}><Preview device={modal.preview} /></Modal>}
      {modal?.key && <Modal title={`API key for ${modal.key.name}`} onClose={() => setModal(null)}>
        <CreateKeyForm devices={devices} fixedDevice={modal.key.id} onCreated={(r) => { setModal(null); setShownKey(r); reload(); }} /></Modal>}
      {shownKey && <ShowKeyOnce data={shownKey} onClose={() => setShownKey(null)} />}
    </div>
  );
}
