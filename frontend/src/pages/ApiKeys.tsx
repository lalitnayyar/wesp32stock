import { FormEvent, useState } from "react";
import { ago, get, post } from "../api";
import { ErrorBox, Field, Modal, Notice, useAction, useLoad } from "../components/ui";

export function ShowKeyOnce({ data, onClose }: { data: any; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <Modal title="New API key - copy it now" onClose={onClose}>
      <Notice kind="warn">{data.warning}</Notice>
      <div className="font-mono text-sm break-all bg-stone-100 p-2 rounded border select-all">{data.key}</div>
      <button className="btn mt-2" onClick={() => navigator.clipboard.writeText(data.key).then(() => setCopied(true))}>{copied ? "Copied" : "Copy to clipboard"}</button>
      <p className="text-xs text-stone-500 mt-2">Enter this key in the ESP32 administration page (Device API key). The server stores only a hash.</p>
    </Modal>
  );
}

export function CreateKeyForm({ devices, fixedDevice, onCreated }: { devices: any[]; fixedDevice?: number; onCreated: (d: any) => void }) {
  const { data: scopes } = useLoad(() => get("/api/v1/api-keys/scopes"));
  const [f, setF] = useState<any>({ name: "", device_id: fixedDevice ?? "", expires_in_days: 365, scopes: ["device:dashboard", "device:heartbeat"] });
  const act = useAction();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const r = await act.run(() => post("/api/v1/api-keys", { ...f, device_id: f.device_id ? Number(f.device_id) : null, expires_in_days: f.expires_in_days ? Number(f.expires_in_days) : null }));
    if (r) onCreated(r);
  };
  return (
    <form onSubmit={submit}>
      <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
      <Field label="Bound device">
        <select className="input" value={f.device_id} disabled={!!fixedDevice} onChange={(e) => setF({ ...f, device_id: e.target.value })}>
          <option value="">— none (cannot read dashboards) —</option>{devices.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.device_uid})</option>)}
        </select>
      </Field>
      <Field label="Expires in days (blank = never)"><input className="input" type="number" min={1} max={3650} value={f.expires_in_days ?? ""} onChange={(e) => setF({ ...f, expires_in_days: e.target.value })} /></Field>
      <span className="label">Scopes</span>
      {scopes && Object.entries(scopes).map(([s, d]) => (
        <label key={s} className="flex gap-2 items-center text-sm">
          <input type="checkbox" checked={f.scopes.includes(s)} onChange={(e) => setF({ ...f, scopes: e.target.checked ? [...f.scopes, s] : f.scopes.filter((x: string) => x !== s) })} />
          <code>{s}</code> <span className="text-stone-500">{d as string}</span>
        </label>
      ))}
      {act.view}
      <button className="btn mt-3" disabled={act.busy}>Generate key</button>
    </form>
  );
}

export default function ApiKeysPage() {
  const { data, error, reload } = useLoad(() => Promise.all([get("/api/v1/api-keys"), get("/api/v1/devices"), get("/api/v1/access-logs?limit=100")]));
  const [creating, setCreating] = useState(false);
  const [shown, setShown] = useState<any>(null);
  const [logs, setLogs] = useState<any>(null);
  const act = useAction();
  if (error) return <ErrorBox error={error} />;
  if (!data) return <div>Loading…</div>;
  const [keys, devices, access] = data;
  const devName = (id: number | null) => devices.find((d: any) => d.id === id)?.name ?? "—";
  return (
    <div>
      <div className="flex items-center mb-3"><h1 className="h1 mb-0">API Management</h1><button className="btn ml-auto" onClick={() => setCreating(true)}>Create API key</button></div>
      <Notice>Device keys are shown once, stored only as a hash, scoped, rate-limited, revocable, rotatable and expiry-aware. Admin sign-in and device keys are separate.</Notice>
      {act.view}
      <div className="card overflow-x-auto mb-4">
        <table className="tbl"><thead><tr><th>Name</th><th>Key</th><th>Device</th><th>Scopes</th><th>State</th><th>Expires</th><th>Last used</th><th></th></tr></thead>
          <tbody>{keys.map((k: any) => (
            <tr key={k.id}>
              <td>{k.name}</td><td className="font-mono text-xs">{k.prefix}</td><td>{devName(k.device_id)}</td>
              <td className="text-xs">{k.scopes.join(", ")}</td>
              <td><span className={k.state === "active" ? "badge-ok" : "badge-bad"}>{k.state}</span></td>
              <td className="text-xs">{k.expires_at ? new Date(k.expires_at).toLocaleDateString() : "never"}</td>
              <td className="text-xs">{ago(k.last_used_at)} {k.last_used_ip && <span className="text-stone-400">{k.last_used_ip}</span>}</td>
              <td className="text-right space-x-1 whitespace-nowrap">
                <button className="btn-alt" onClick={async () => setLogs({ key: k, rows: await get(`/api/v1/api-keys/${k.id}/logs`) })}>Logs</button>
                {k.state === "active" && <>
                  <button className="btn-alt" onClick={async () => { if (confirm("Rotate: a new key is issued and this one is revoked immediately.")) { const r = await act.run(() => post(`/api/v1/api-keys/${k.id}/rotate`)); if (r) setShown(r); reload(); } }}>Rotate</button>
                  <button className="btn-danger" onClick={() => confirm(`Revoke ${k.name}?`) && act.run(() => post(`/api/v1/api-keys/${k.id}/revoke`)).then(reload)}>Revoke</button>
                </>}
              </td>
            </tr>))}</tbody></table>
      </div>
      <div className="card overflow-x-auto">
        <h2 className="h2">Recent device API access</h2>
        <table className="tbl"><thead><tr><th>Time</th><th>Key</th><th>Request</th><th>Status</th><th>IP</th></tr></thead>
          <tbody>{access.map((r: any, i: number) => (
            <tr key={i}><td className="text-xs">{new Date(r.ts).toLocaleString()}</td><td>{keys.find((k: any) => k.id === r.api_key_id)?.name ?? "unknown"}</td>
              <td className="font-mono text-xs">{r.method} {r.path}</td><td><span className={r.status < 300 ? "badge-ok" : "badge-bad"}>{r.status}</span></td><td className="text-xs">{r.ip}</td></tr>))}</tbody></table>
      </div>
      {creating && <Modal title="Create API key" onClose={() => setCreating(false)}><CreateKeyForm devices={devices} onCreated={(r) => { setCreating(false); setShown(r); reload(); }} /></Modal>}
      {shown && <ShowKeyOnce data={shown} onClose={() => setShown(null)} />}
      {logs && (
        <Modal title={`Access log: ${logs.key.name}`} onClose={() => setLogs(null)}>
          <table className="tbl"><tbody>{logs.rows.map((r: any, i: number) => (
            <tr key={i}><td className="text-xs">{new Date(r.ts).toLocaleString()}</td><td className="font-mono text-xs">{r.method} {r.path}</td><td>{r.status}</td><td className="text-xs">{r.ip}</td></tr>))}</tbody></table>
          {logs.rows.length === 0 && <p className="text-sm text-stone-500">No requests yet.</p>}
        </Modal>
      )}
    </div>
  );
}
