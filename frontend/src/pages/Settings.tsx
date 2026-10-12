import { FormEvent, useState } from "react";
import { ago, get, post, put } from "../api";
import { ErrorBox, Field, Notice, useAction, useLoad } from "../components/ui";

function SettingsForm() {
  const { data, error, reload } = useLoad(() => get("/api/v1/settings"));
  const [vals, setVals] = useState<Record<string, any> | null>(null);
  const act = useAction();
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const v = vals ?? data.values;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (await act.run(() => put("/api/v1/settings", v), "Settings saved")) { setVals(null); reload(); }
  };
  const groups: [string, string[]][] = [
    ["General", ["timezone"]],
    ["Market data", ["quote_refresh_s", "request_timeout_s", "retry_attempts", "backoff_base_s", "market_hours_optimization", "closed_market_poll_s", "stale_after_s", "history_enabled", "history_days"]],
    ["Devices & security", ["heartbeat_timeout_s", "device_rate_limit_per_min"]],
  ];
  const spec = Object.fromEntries(data.schema.map((s: any) => [s.key, s]));
  return (
    <form className="card" onSubmit={submit}>
      <h2 className="h2">Application settings</h2>
      {groups.map(([g, keys]) => (
        <div key={g} className="mb-3">
          <div className="text-sm font-semibold mt-2">{g}</div>
          <div className="grid md:grid-cols-3 gap-x-3">
            {keys.map((k) => {
              const s = spec[k];
              return (
                <Field key={k} label={`${s.description}${s.min !== null ? ` (${s.min}-${s.max})` : ""}`}>
                  {s.type === "bool" ? (
                    <select className="input" value={v[k] ? "1" : "0"} onChange={(e) => setVals({ ...v, [k]: e.target.value === "1" })}><option value="1">On</option><option value="0">Off</option></select>
                  ) : (
                    <input className="input" type={s.type === "str" ? "text" : "number"} step={s.type === "float" ? "0.1" : "1"} value={v[k]}
                      onChange={(e) => setVals({ ...v, [k]: s.type === "str" ? e.target.value : Number(e.target.value) })} />
                  )}
                </Field>
              );
            })}
          </div>
        </div>
      ))}
      {act.view}
      <button className="btn">Save settings</button>
    </form>
  );
}

function MarketStatus() {
  const { data, reload } = useLoad(() => get("/api/v1/market/status"));
  const act = useAction();
  if (!data) return null;
  const q = data.scheduler.jobs.quotes;
  return (
    <div className="card mt-4 overflow-x-auto">
      <div className="flex items-center gap-2"><h2 className="h2 mb-0">Market-data engine</h2>
        <button className="btn-alt ml-auto" disabled={act.busy} onClick={() => act.run(() => post("/api/v1/market/refresh"), "Refreshed").then(reload)}>Refresh now</button>
        <button className="btn-alt" disabled={act.busy} onClick={() => act.run(() => post("/api/v1/market/history"), "History refreshed").then(reload)}>Refresh history</button></div>
      {act.view}
      <div className="text-sm text-stone-600 my-2">
        Provider <b>{data.provider}</b> · every <b>{data.quote_refresh_s}s</b> · scheduler {data.scheduler.running ? "running" : "stopped"}
        {q && <> · next run {q.next_run_at ? new Date(q.next_run_at).toLocaleTimeString() : "—"}</>} · last poll {ago(data.last_poll.finished_at)} ({data.last_poll.ok} ok, {data.last_poll.failed} failed, {data.last_poll.skipped} skipped) · last success {ago(data.last_poll.last_success_at)}
      </div>
      <table className="tbl"><thead><tr><th>Symbol</th><th>Quality</th><th>Market</th><th>Last poll</th><th>Last success</th><th>Quote time</th><th>Error</th></tr></thead>
        <tbody>{data.symbols.map((s: any) => (
          <tr key={s.ticker}><td>{s.ticker}</td><td><span className={s.stale ? "badge-warn" : "badge-ok"}>{s.stale ? "stale" : s.data_quality}</span></td><td>{s.market_state}</td>
            <td>{ago(s.last_poll_at)}</td><td>{ago(s.last_success_at)}</td><td className="text-xs">{s.quote_time ? new Date(s.quote_time).toLocaleString() : "—"}</td>
            <td className="text-xs text-red-700 max-w-xs truncate" title={s.last_error ?? ""}>{s.last_error ?? ""}</td></tr>))}</tbody></table>
    </div>
  );
}

function Security() {
  const { data: sessions, reload } = useLoad(() => get("/api/v1/auth/sessions"));
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const act = useAction();
  return (
    <div className="card mt-4">
      <h2 className="h2">Security</h2>
      <form className="grid md:grid-cols-3 gap-2 items-end" onSubmit={async (e) => { e.preventDefault(); await act.run(() => post("/api/v1/auth/password", pw), "Password changed. Sign in again."); }}>
        <Field label="Current password"><input className="input" type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
        <Field label="New password (min 12)"><input className="input" type="password" minLength={12} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
        <button className="btn h-9">Change password</button>
      </form>
      {act.view}
      <div className="text-sm font-semibold mt-3">Sessions</div>
      <table className="tbl"><tbody>{sessions?.map((s: any) => (
        <tr key={s.id}><td className="text-xs">{new Date(s.created_at).toLocaleString()}</td><td className="text-xs">{s.ip}</td><td className="text-xs truncate max-w-xs">{s.user_agent}</td>
          <td>{s.revoked_at ? <span className="badge">revoked</span> : <button className="btn-alt" onClick={() => act.run(() => post(`/api/v1/auth/sessions/${s.id}/revoke`)).then(reload)}>Revoke</button>}</td></tr>))}</tbody></table>
    </div>
  );
}

function Maintenance() {
  const act = useAction();
  return (
    <div className="card mt-4">
      <h2 className="h2">Demo data, backup &amp; restore</h2>
      <div className="space-x-2">
        <button className="btn-alt" onClick={() => act.run(() => post("/api/v1/demo/seed"), "Demo data loaded (fixture prices in fixture mode)")}>Load demo data</button>
        <button className="btn-danger" onClick={() => confirm("Remove all demo portfolios, demo stocks and their transactions?") && act.run(() => post("/api/v1/demo/remove", { confirm: true }), "Demo data removed")}>Remove demo data</button>
      </div>
      {act.view}
      <Notice>Database backups and restores are run on the server with <code>./manage.sh backup</code> / <code>./manage.sh restore</code> (timestamped, restore asks for confirmation). See docs/BACKUP_RESTORE.md.</Notice>
    </div>
  );
}

function Audit() {
  const { data } = useLoad(() => get("/api/v1/audit?limit=100"));
  return (
    <div className="card mt-4 overflow-x-auto">
      <h2 className="h2">Audit log</h2>
      <table className="tbl"><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
        <tbody>{data?.map((r: any) => (
          <tr key={r.id}><td className="text-xs">{new Date(r.ts).toLocaleString()}</td><td>{r.actor}</td><td>{r.action}</td><td>{r.entity}{r.entity_id && `#${r.entity_id}`}</td>
            <td className="text-xs font-mono max-w-md truncate" title={JSON.stringify(r.details)}>{JSON.stringify(r.details)}</td></tr>))}</tbody></table>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <div>
      <h1 className="h1">Settings</h1>
      <SettingsForm />
      <MarketStatus />
      <Security />
      <Maintenance />
      <Audit />
    </div>
  );
}
