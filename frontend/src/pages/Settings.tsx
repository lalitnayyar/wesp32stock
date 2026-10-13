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

function TelegramBot() {
  const { data, error, reload } = useLoad(() => get("/api/v1/telegram/config"));
  const { data: pfs } = useLoad(() => get("/api/v1/portfolios"));
  const [f, setF] = useState<any>(null);
  const act = useAction();
  if (error) return <div className="card mt-4"><ErrorBox error={error} /></div>;
  if (!data) return null;
  const v = f ?? { enabled: data.enabled, bot_token: "", chats: data.allowed_chat_ids.join(", "), default_portfolio_id: data.default_portfolio_id ?? "" };
  const st = data.status;
  const save = async (e: FormEvent) => {
    e.preventDefault();
    const ids = v.chats.split(/[\s,]+/).filter(Boolean);
    if (ids.some((x: string) => !/^-?\d+$/.test(x))) { act.setMsg({ text: "Chat IDs must be numbers (group IDs start with -)", bad: true }); return; }
    const body: any = { enabled: v.enabled, allowed_chat_ids: ids.map(Number), default_portfolio_id: v.default_portfolio_id === "" ? null : Number(v.default_portfolio_id) };
    if (v.bot_token) body.bot_token = v.bot_token.trim();
    if (await act.run(() => put("/api/v1/telegram/config", body), "Telegram settings saved")) { setF(null); reload(); }
  };
  return (
    <form className="card mt-4" onSubmit={save}>
      <div className="flex items-center gap-2">
        <h2 className="h2 mb-0">Telegram bot</h2>
        <span className={data.enabled && st.polling ? "badge-ok" : data.enabled ? "badge-warn" : "badge"}>
          {data.enabled ? (st.polling ? `polling${st.bot_username ? ` @${st.bot_username}` : ""}` : "starting / error") : "off"}
        </span>
      </div>
      <p className="text-sm text-stone-600 my-2">
        Talk to your portfolios from Telegram with slash commands, and send AI insights from Analytics.
        The server polls Telegram over outbound HTTPS, so no public domain or port forwarding is needed. Only the chat IDs below get answers.
      </p>
      <ol className="text-xs text-stone-600 list-decimal ml-5 mb-2">
        <li>In Telegram, message <b>@BotFather</b>, send <code>/newbot</code> and copy the token.</li>
        <li>Paste the token here, tick Enabled and Save.</li>
        <li>Send <code>/start</code> to your bot. It replies with your chat ID (it is not authorised yet).</li>
        <li>Add that chat ID below, Save, then press <b>Test &amp; greet</b>.</li>
      </ol>
      <div className="grid md:grid-cols-3 gap-x-3">
        <Field label={data.has_token ? `Bot token (saved: ${data.token_masked}; blank = keep)` : "Bot token from @BotFather"}>
          <input className="input" type="password" autoComplete="off" placeholder="123456789:AA…" value={v.bot_token} onChange={(e) => setF({ ...v, bot_token: e.target.value })} />
        </Field>
        <Field label="Allowed chat IDs (comma separated)">
          <input className="input" placeholder="e.g. 123456789, -1001234567890" value={v.chats} onChange={(e) => setF({ ...v, chats: e.target.value })} />
        </Field>
        <Field label="Default portfolio (chats can change it with /use)">
          <select className="input" value={v.default_portfolio_id} onChange={(e) => setF({ ...v, default_portfolio_id: e.target.value })}>
            <option value="">First portfolio</option>
            {pfs?.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
      </div>
      <label className="flex gap-2 items-center text-sm mt-2"><input type="checkbox" checked={v.enabled} onChange={(e) => setF({ ...v, enabled: e.target.checked })} /> Enabled</label>
      {st.last_error && data.enabled && <div className="text-xs text-red-700 mt-1">Last error: {st.last_error}</div>}
      <div className="text-xs text-stone-500 mt-1">Last poll {ago(st.last_poll_at)} · {st.messages_handled} messages handled since start</div>
      {act.view}
      <div className="space-x-2 mt-2">
        <button className="btn" disabled={act.busy}>Save</button>
        <button type="button" className="btn-alt" disabled={act.busy || !data.has_token}
          onClick={async () => { const r: any = await act.run(() => post("/api/v1/telegram/test")); if (r) act.setMsg({ text: r.message, bad: false }); reload(); }}>Test &amp; greet</button>
        {data.has_token && <button type="button" className="btn-danger" disabled={act.busy}
          onClick={() => confirm("Remove the bot token and disable the bot?") && act.run(() => put("/api/v1/telegram/config", { clear_token: true, enabled: false }), "Token removed").then(reload)}>Remove token</button>}
      </div>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-stone-600">Bot commands</summary>
        <table className="tbl mt-1"><tbody>{data.commands.map((c: any) => <tr key={c.command}><td><code>/{c.command}</code></td><td>{c.description}</td></tr>)}</tbody></table>
        <p className="text-xs text-stone-500 mt-1">Insight tasks: summary, daily, contributors, concentration, unusual, benchmarks, risk (e.g. <code>/insight risk</code>). AI output is not financial advice.</p>
      </details>
    </form>
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
      <TelegramBot />
      <Security />
      <Maintenance />
      <Audit />
    </div>
  );
}
