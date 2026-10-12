import { FormEvent, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ago, del, fmt, get, pnlClass, post, put, signed } from "../api";
import { ErrorBox, Field, Modal, Notice, useAction, useLoad } from "../components/ui";

function AddStock({ onDone }: { onDone: () => void }) {
  const [ticker, setTicker] = useState("");
  const [check, setCheck] = useState<any>(null);
  const [skip, setSkip] = useState(false);
  const [extra, setExtra] = useState({ sector: "", notes: "" });
  const act = useAction();
  const validate = async () => setCheck(await act.run(() => post("/api/v1/stocks/validate", { ticker })));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (await act.run(() => post("/api/v1/stocks", { ticker, skip_validation: skip, ...extra }))) onDone();
  };
  return (
    <form onSubmit={submit}>
      <Notice>Use the provider symbol including the exchange suffix, e.g. <code>AAPL</code>, <code>EMAAR.AE</code> (DFM). Symbols are validated against the market-data provider before they are added.</Notice>
      <Field label="Ticker / provider symbol">
        <div className="flex gap-2">
          <input className="input" value={ticker} onChange={(e) => { setTicker(e.target.value.toUpperCase()); setCheck(null); }} required />
          <button type="button" className="btn-alt" onClick={validate} disabled={!ticker || act.busy}>Validate</button>
        </div>
      </Field>
      {check && (check.valid ? (
        <Notice kind="ok">{check.info.company} · {check.info.exchange} · {check.info.currency} · {check.info.sector || "no sector"} · market {check.market}</Notice>
      ) : <Notice kind="warn">{check.message}. {check.hint}</Notice>)}
      <Field label="Sector override (optional)"><input className="input" value={extra.sector} onChange={(e) => setExtra({ ...extra, sector: e.target.value })} /></Field>
      <Field label="Notes"><input className="input" value={extra.notes} onChange={(e) => setExtra({ ...extra, notes: e.target.value })} /></Field>
      <label className="flex gap-2 items-center text-sm mt-2"><input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} /> Add without provider validation (marked "unvalidated")</label>
      {act.view}
      <button className="btn mt-3" disabled={act.busy}>Add stock</button>
    </form>
  );
}

function EditStock({ stock, onDone }: any) {
  const [f, setF] = useState({ company: stock.company, exchange: stock.exchange, market: stock.market, currency: stock.currency,
    sector: stock.sector, industry: stock.industry, country: stock.country, notes: stock.notes });
  const act = useAction();
  const { data: hist } = useLoad(() => get(`/api/v1/stocks/${stock.id}/history?days=180`), [stock.id]);
  return (
    <div>
      {hist && hist.length > 1 && (
        <div className="h-40 mb-2"><ResponsiveContainer><LineChart data={hist.map((h: any) => ({ ...h, close: Number(h.close) }))}>
          <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} /><YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} width={50} />
          <Tooltip /><Line dataKey="close" dot={false} stroke="#b3121b" /></LineChart></ResponsiveContainer></div>
      )}
      <form onSubmit={async (e) => { e.preventDefault(); if (await act.run(() => put(`/api/v1/stocks/${stock.id}`, f))) onDone(); }} className="grid grid-cols-2 gap-x-3">
        {Object.keys(f).map((k) => (
          <Field key={k} label={k}><input className="input" value={(f as any)[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>
        ))}
        <div className="col-span-2">{act.view}<button className="btn mt-3">Save</button></div>
      </form>
    </div>
  );
}

function Benchmarks() {
  const { data, error, reload } = useLoad(() => get("/api/v1/benchmarks"));
  const [f, setF] = useState({ name: "", ticker: "" });
  const act = useAction();
  return (
    <div className="card mt-4 overflow-x-auto">
      <h2 className="h2">Benchmarks</h2>
      <p className="text-xs text-stone-500 mb-2">Only provider-supported symbols can be activated. Benchmark performance is shown separately from portfolio returns.</p>
      <ErrorBox error={error} />{act.view}
      <table className="tbl"><thead><tr><th>Name</th><th>Symbol</th><th>Level</th><th>Day</th><th>Status</th><th></th></tr></thead>
        <tbody>{data?.map((b: any) => (
          <tr key={b.id}>
            <td>{b.name}</td><td>{b.ticker}</td><td>{fmt(b.performance?.level)}</td>
            <td className={pnlClass(b.performance?.day_change_pct)}>{b.performance ? `${signed(b.performance.day_change_pct)}%` : "—"}</td>
            <td>{b.active ? <span className="badge-ok">active</span> : <span className="badge-warn" title={b.notes}>inactive</span>} <span className="text-xs text-stone-400">{b.notes}</span></td>
            <td className="text-right space-x-1">
              <button className="btn-alt" onClick={() => act.run(() => put(`/api/v1/benchmarks/${b.id}`, { active: !b.active })).then(reload)}>{b.active ? "Deactivate" : "Validate & activate"}</button>
              <button className="btn-alt" onClick={() => confirm("Remove benchmark?") && act.run(() => del(`/api/v1/benchmarks/${b.id}`)).then(reload)}>Remove</button>
            </td>
          </tr>))}</tbody></table>
      <form className="flex gap-2 mt-2" onSubmit={async (e) => { e.preventDefault(); if (await act.run(() => post("/api/v1/benchmarks", f))) { setF({ name: "", ticker: "" }); reload(); } }}>
        <input className="input" placeholder="Display name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required maxLength={64} />
        <input className="input" placeholder="Provider symbol, e.g. ^GSPC" value={f.ticker} onChange={(e) => setF({ ...f, ticker: e.target.value.toUpperCase() })} required />
        <button className="btn">Add</button>
      </form>
    </div>
  );
}

export default function StocksPage() {
  const [q, setQ] = useState("");
  const { data, error, reload } = useLoad(() => get(`/api/v1/stocks?q=${encodeURIComponent(q)}`), [q]);
  const [modal, setModal] = useState<any>(null);
  const act = useAction();
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h1 className="h1 mb-0">Stocks</h1>
        <input className="input max-w-xs ml-auto" placeholder="Search ticker or company" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn-alt" onClick={() => act.run(() => post("/api/v1/market/refresh"), "Quotes refreshed").then(reload)} disabled={act.busy}>Refresh quotes</button>
        <button className="btn" onClick={() => setModal({ add: true })}>Add stock</button>
      </div>
      <ErrorBox error={error} />{act.view}
      <div className="card overflow-x-auto">
        <table className="tbl"><thead><tr><th>Ticker</th><th>Company</th><th>Kind</th><th>Exchange</th><th>Ccy</th><th>Sector</th><th>Price</th><th>Day</th><th>Market</th><th>Last update</th><th>Quality</th><th></th></tr></thead>
          <tbody>{data?.map((s: any) => (
            <tr key={s.id} className={s.active ? "" : "opacity-50"}>
              <td className="font-medium">{s.ticker}</td><td className="max-w-[14rem] truncate">{s.company}</td><td>{s.kind}</td>
              <td>{s.exchange}</td><td>{s.currency}</td><td>{s.sector}</td>
              <td>{fmt(s.quote?.price)}</td>
              <td className={pnlClass(s.quote?.change_pct)}>{s.quote?.change_pct ? `${signed(s.quote.change_pct)}%` : "—"}</td>
              <td>{s.quote?.market_state ?? "—"}</td>
              <td title={s.quote?.last_error ?? ""}>{ago(s.quote?.last_success_at)}{s.quote?.last_error && <span className="badge-bad ml-1">err</span>}</td>
              <td><span className={s.data_quality === "ok" ? "badge-ok" : s.data_quality === "unavailable" ? "badge-bad" : "badge-warn"}>{s.data_quality}</span>{s.quote?.delayed && <span className="badge ml-1">delayed</span>}</td>
              <td className="text-right space-x-1 whitespace-nowrap">
                <button className="btn-alt" onClick={() => setModal({ edit: s })}>Edit</button>
                <button className="btn-alt" onClick={() => act.run(() => post(`/api/v1/stocks/${s.id}/refresh`)).then(reload)}>↻</button>
                <button className="btn-alt" onClick={() => act.run(() => put(`/api/v1/stocks/${s.id}`, { active: !s.active })).then(reload)}>{s.active ? "Deactivate" : "Activate"}</button>
              </td>
            </tr>))}</tbody></table>
      </div>
      <Benchmarks />
      {modal?.add && <Modal title="Add stock" onClose={() => setModal(null)}><AddStock onDone={() => { setModal(null); reload(); }} /></Modal>}
      {modal?.edit && <Modal title={`Edit ${modal.edit.ticker}`} onClose={() => setModal(null)}><EditStock stock={modal.edit} onDone={() => { setModal(null); reload(); }} /></Modal>}
    </div>
  );
}
