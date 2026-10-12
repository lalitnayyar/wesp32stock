import { FormEvent, useState } from "react";
import { Link, Route, Routes, useParams } from "react-router-dom";
import { del, fmt, get, pnlClass, post, put, signed } from "../api";
import { ErrorBox, Field, Modal, Notice, Stat, useAction, useLoad } from "../components/ui";

const TX_TYPES = ["BUY", "SELL", "DIVIDEND", "SPLIT", "FEE", "DEPOSIT", "WITHDRAWAL", "ADJUSTMENT"];

function PortfolioForm({ initial, brokers, onSaved, onCancel }: any) {
  const [f, setF] = useState(initial ?? { name: "", base_currency: "USD", broker_id: null, description: "", active: true });
  const act = useAction();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = { ...f, broker_id: f.broker_id ? Number(f.broker_id) : null };
    const r = await act.run(() => (f.id ? put(`/api/v1/portfolios/${f.id}`, body) : post("/api/v1/portfolios", body)));
    if (r) onSaved();
  };
  return (
    <form onSubmit={submit}>
      <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
      <Field label="Base currency"><input className="input" value={f.base_currency} maxLength={3} onChange={(e) => setF({ ...f, base_currency: e.target.value.toUpperCase() })} /></Field>
      <Field label="Default broker">
        <select className="input" value={f.broker_id ?? ""} onChange={(e) => setF({ ...f, broker_id: e.target.value || null })}>
          <option value="">—</option>
          {brokers.map((b: any) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
      </Field>
      <Field label="Description"><input className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      {act.view}
      <div className="mt-3 flex gap-2"><button className="btn" disabled={act.busy}>Save</button><button type="button" className="btn-alt" onClick={onCancel}>Cancel</button></div>
    </form>
  );
}

function Brokers() {
  const { data, error, reload } = useLoad(() => get("/api/v1/brokers"));
  const [name, setName] = useState("");
  const [ref, setRef] = useState("");
  const act = useAction();
  return (
    <div className="card mt-4">
      <h2 className="h2">Brokers / accounts</h2>
      <ErrorBox error={error} />
      <table className="tbl"><thead><tr><th>Name</th><th>Account</th><th></th></tr></thead>
        <tbody>{data?.map((b: any) => (
          <tr key={b.id}><td>{b.name}</td><td>{b.account_ref}</td>
            <td className="text-right"><button className="btn-alt" onClick={() => confirm(`Delete broker ${b.name}?`) && act.run(() => del(`/api/v1/brokers/${b.id}`)).then(reload)}>Delete</button></td></tr>
        ))}</tbody></table>
      <form className="flex gap-2 mt-2" onSubmit={async (e) => { e.preventDefault(); if (await act.run(() => post("/api/v1/brokers", { name, account_ref: ref }))) { setName(""); setRef(""); reload(); } }}>
        <input className="input" placeholder="Broker name" value={name} onChange={(e) => setName(e.target.value)} required />
        <input className="input" placeholder="Account reference" value={ref} onChange={(e) => setRef(e.target.value)} />
        <button className="btn">Add</button>
      </form>
      {act.view}
    </div>
  );
}

function List() {
  const { data, error, reload } = useLoad(() => Promise.all([get("/api/v1/portfolios"), get("/api/v1/brokers")]));
  const [editing, setEditing] = useState<any>(null);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <div>Loading…</div>;
  const [pfs, brokers] = data;
  return (
    <div>
      <div className="flex items-center mb-3"><h1 className="h1 mb-0">Portfolios</h1><button className="btn ml-auto" onClick={() => setEditing({})}>New portfolio</button></div>
      <div className="card overflow-x-auto">
        <table className="tbl"><thead><tr><th>Name</th><th>Currency</th><th>Broker</th><th>Status</th><th></th></tr></thead>
          <tbody>{pfs.map((p: any) => (
            <tr key={p.id}>
              <td><Link className="underline font-medium" to={`/portfolios/${p.id}`}>{p.name}</Link></td>
              <td>{p.base_currency}</td><td>{brokers.find((b: any) => b.id === p.broker_id)?.name ?? "—"}</td>
              <td>{p.active ? <span className="badge-ok">active</span> : <span className="badge">inactive</span>}</td>
              <td className="text-right"><button className="btn-alt" onClick={() => setEditing(p)}>Edit</button></td>
            </tr>))}
          </tbody></table>
        {pfs.length === 0 && <p className="text-sm text-stone-500 p-2">No portfolios yet.</p>}
      </div>
      <Brokers />
      {editing && (
        <Modal title={editing.id ? "Edit portfolio" : "New portfolio"} onClose={() => setEditing(null)}>
          <PortfolioForm initial={editing.id ? editing : undefined} brokers={brokers} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />
        </Modal>
      )}
    </div>
  );
}

function TxForm({ pid, stocks, brokers, initial, onDone }: any) {
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState<any>(initial ?? { type: "BUY", stock_id: "", broker_id: "", trade_date: today, quantity: "", price: "", fees: "0", amount: "0", split_ratio: "", notes: "" });
  const act = useAction();
  const needsStock = ["BUY", "SELL", "DIVIDEND", "SPLIT", "ADJUSTMENT"].includes(f.type);
  const cash = ["DEPOSIT", "WITHDRAWAL"].includes(f.type);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body: any = {
      type: f.type, trade_date: f.trade_date, notes: f.notes,
      stock_id: cash ? null : f.stock_id ? Number(f.stock_id) : null,
      broker_id: f.broker_id ? Number(f.broker_id) : null,
      quantity: f.quantity || "0", price: f.price || "0", fees: f.fees || "0", amount: f.amount || "0",
      split_ratio: f.type === "SPLIT" ? f.split_ratio : null,
    };
    const r = await act.run(() => (f.id ? put(`/api/v1/transactions/${f.id}`, body) : post(`/api/v1/portfolios/${pid}/transactions`, body)));
    if (r) onDone();
  };
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-x-3">
      <Field label="Type"><select className="input" value={f.type} onChange={set("type")}>{TX_TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
      <Field label="Date"><input className="input" type="date" value={f.trade_date} onChange={set("trade_date")} required /></Field>
      {!cash && (
        <Field label={needsStock ? "Stock" : "Stock (optional)"}>
          <select className="input" value={f.stock_id ?? ""} onChange={set("stock_id")} required={needsStock}>
            <option value="">—</option>{stocks.map((s: any) => <option key={s.id} value={s.id}>{s.ticker} — {s.company}</option>)}
          </select>
        </Field>
      )}
      <Field label="Broker"><select className="input" value={f.broker_id ?? ""} onChange={set("broker_id")}><option value="">—</option>{brokers.map((b: any) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>
      {["BUY", "SELL", "ADJUSTMENT"].includes(f.type) && <Field label={f.type === "ADJUSTMENT" ? "Quantity delta (+/-)" : "Quantity"}><input className="input" inputMode="decimal" value={f.quantity} onChange={set("quantity")} required /></Field>}
      {["BUY", "SELL"].includes(f.type) && <Field label="Price per share"><input className="input" inputMode="decimal" value={f.price} onChange={set("price")} required /></Field>}
      {["BUY", "SELL", "DIVIDEND"].includes(f.type) && <Field label="Fees"><input className="input" inputMode="decimal" value={f.fees} onChange={set("fees")} /></Field>}
      {["DIVIDEND", "FEE", "DEPOSIT", "WITHDRAWAL", "ADJUSTMENT"].includes(f.type) && <Field label={f.type === "ADJUSTMENT" ? "Cost basis delta (+/-)" : "Amount"}><input className="input" inputMode="decimal" value={f.amount} onChange={set("amount")} /></Field>}
      {f.type === "SPLIT" && <Field label="Split ratio (2 = 2-for-1)"><input className="input" inputMode="decimal" value={f.split_ratio ?? ""} onChange={set("split_ratio")} required /></Field>}
      <div className="col-span-2"><Field label={f.type === "ADJUSTMENT" ? "Reason (required, audited)" : "Notes"}><input className="input" value={f.notes} onChange={set("notes")} required={f.type === "ADJUSTMENT"} /></Field></div>
      <div className="col-span-2">{act.view}<button className="btn mt-3" disabled={act.busy}>{f.id ? "Save changes" : "Add transaction"}</button></div>
    </form>
  );
}

function Detail() {
  const { id } = useParams();
  const { data, error, reload } = useLoad(() => Promise.all([
    get(`/api/v1/portfolios/${id}/summary`), get(`/api/v1/portfolios/${id}/transactions`),
    get("/api/v1/stocks?active=true"), get("/api/v1/brokers")]), [id]);
  const [tx, setTx] = useState<any>(null);
  const act = useAction();
  if (error) return <ErrorBox error={error} />;
  if (!data) return <div>Loading…</div>;
  const [s, txs, stocks, brokers] = data;
  const t = s.totals;
  const equities = stocks.filter((x: any) => x.kind !== "fx");
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Link to="/portfolios" className="text-sm underline">Portfolios</Link><span>/</span>
        <h1 className="h1 mb-0">{s.portfolio.name}</h1><span className="badge">{s.portfolio.base_currency}</span>
        <button className="btn ml-auto" onClick={() => setTx({})}>Add transaction</button>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <Stat label="Market value" value={fmt(t.market_value)} sub={`Invested ${fmt(t.invested)}`} />
        <Stat label="Unrealized P/L" value={signed(t.unrealized_pl)} sub={`${signed(t.unrealized_pct)}%`} cls={pnlClass(t.unrealized_pl)} />
        <Stat label="Today" value={signed(t.day_pl)} sub={`${signed(t.day_pct)}%`} cls={pnlClass(t.day_pl)} />
        <Stat label="Realized P/L · dividends" value={signed(t.realized_pl)} sub={`Dividends ${fmt(t.dividends)} · Cash ${fmt(t.cash)}`} />
      </div>
      {s.warnings.length > 0 && <Notice kind="warn">{s.warnings.join(" · ")}</Notice>}
      <div className="card overflow-x-auto mb-4">
        <h2 className="h2">Holdings <span className="text-xs font-normal text-stone-500">average-cost accounting</span></h2>
        <table className="tbl"><thead><tr><th>Ticker</th><th>Qty</th><th>Avg cost</th><th>Price</th><th>Day</th><th>Market value</th><th>Value ({s.portfolio.base_currency})</th><th>Unrealized</th><th>Alloc.</th><th>Data</th></tr></thead>
          <tbody>{s.holdings.map((h: any) => (
            <tr key={h.stock_id}>
              <td><b>{h.ticker}</b> <span className="text-xs text-stone-400">{h.currency}</span></td>
              <td>{h.quantity}</td><td>{fmt(h.avg_cost, 4)}</td><td>{fmt(h.price)}</td>
              <td className={pnlClass(h.day_change_pct)}>{signed(h.day_change_pct)}%</td>
              <td>{fmt(h.market_value)}</td><td>{fmt(h.market_value_base)}</td>
              <td className={pnlClass(h.unrealized_pl)}>{signed(h.unrealized_pl)} ({signed(h.unrealized_pct)}%)</td>
              <td>{h.allocation_pct ? `${fmt(h.allocation_pct)}%` : "—"}</td>
              <td>{h.stale ? <span className="badge-warn">stale</span> : <span className="badge-ok">{h.market_state.toLowerCase()}</span>}</td>
            </tr>))}</tbody></table>
        {s.holdings.length === 0 && <p className="text-sm text-stone-500 p-2">No open positions.</p>}
      </div>
      <div className="card overflow-x-auto">
        <h2 className="h2">Transaction ledger</h2>
        {act.view}
        <table className="tbl"><thead><tr><th>Date</th><th>Type</th><th>Stock</th><th>Qty</th><th>Price</th><th>Fees</th><th>Amount</th><th>Notes</th><th></th></tr></thead>
          <tbody>{txs.map((x: any) => (
            <tr key={x.id}>
              <td>{x.trade_date}</td><td><span className="badge">{x.type}</span></td><td>{x.ticker ?? "—"}</td>
              <td>{x.type === "SPLIT" ? `×${x.split_ratio}` : x.quantity}</td><td>{x.price}</td><td>{x.fees}</td><td>{x.amount}</td>
              <td className="max-w-[16rem] truncate">{x.notes}</td>
              <td className="text-right space-x-1">
                <button className="btn-alt" onClick={() => setTx(x)}>Edit</button>
                <button className="btn-alt" onClick={() => confirm("Delete this transaction? (audited)") && act.run(() => del(`/api/v1/transactions/${x.id}`)).then(reload)}>Delete</button>
              </td>
            </tr>))}</tbody></table>
      </div>
      {tx && (
        <Modal title={tx.id ? "Edit transaction" : "Add transaction"} onClose={() => setTx(null)}>
          <TxForm pid={id} stocks={equities} brokers={brokers} initial={tx.id ? tx : undefined} onDone={() => { setTx(null); reload(); }} />
        </Modal>
      )}
    </div>
  );
}

export default function PortfoliosPage() {
  return (
    <Routes>
      <Route index element={<List />} />
      <Route path=":id" element={<Detail />} />
    </Routes>
  );
}
