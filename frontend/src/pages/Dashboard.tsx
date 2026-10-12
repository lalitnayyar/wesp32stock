import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ago, fmt, get, pnlClass, signed } from "../api";
import { ErrorBox, Notice, Stat, useLoad } from "../components/ui";

export default function DashboardPage() {
  const { data, error } = useLoad(() =>
    Promise.all([
      get("/api/v1/analytics/overview"),
      get("/api/v1/market/status"),
      get("/api/v1/devices"),
      get("/api/v1/ai/providers"),
    ]),
  );
  const [history, setHistory] = useState<{ date: string; value: number }[]>([]);
  const overview = data?.[0];
  const firstId = overview?.portfolios?.[0]?.portfolio?.id;
  useEffect(() => {
    if (firstId)
      get(`/api/v1/portfolios/${firstId}/history?days=90`).then((h) =>
        setHistory(h.map((r: any) => ({ date: r.date, value: Number(r.value) }))),
      );
  }, [firstId]);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <div className="text-stone-500">Loading…</div>;
  const [ov, market, devices, ai] = data;
  const symbols = market.symbols as any[];
  const stale = symbols.filter((s) => s.stale).length;
  const online = devices.filter((d: any) => d.online).length;
  const aiDefault = ai.providers.find((p: any) => p.is_default);
  const open = symbols.filter((s) => s.market_state === "OPEN").length;

  return (
    <div>
      <h1 className="h1">Dashboard</h1>
      {ov.portfolios.length === 0 && (
        <Notice>
          No portfolios yet. <Link className="underline" to="/portfolios">Create one</Link> or load demo data from{" "}
          <Link className="underline" to="/settings">Settings</Link>.
        </Notice>
      )}
      {ov.portfolios.map((p: any) => (
        <div key={p.portfolio.id} className="mb-4">
          <div className="flex items-baseline gap-2 mb-2">
            <h2 className="h2 mb-0">{p.portfolio.name}</h2>
            <span className="text-xs text-stone-500">{p.portfolio.base_currency}</span>
            {p.freshness.stale_count > 0 && <span className="badge-warn">{p.freshness.stale_count} stale quotes</span>}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <Stat label="Portfolio value" value={fmt(p.totals.market_value)} />
            <Stat label="Today's gain/loss" value={signed(p.totals.day_pl)} sub={`${signed(p.totals.day_pct)}%`} cls={pnlClass(p.totals.day_pl)} />
            <Stat label="Unrealized gain/loss" value={signed(p.totals.unrealized_pl)} sub={`${signed(p.totals.unrealized_pct)}%`} cls={pnlClass(p.totals.unrealized_pl)} />
            <Stat label="Active holdings" value={p.totals.active_holdings} sub={`Invested ${fmt(p.totals.invested)}`} />
            <Stat label="Best / worst today" value={<span className="text-base">{p.best ? `${p.best.ticker} ${signed(p.best.day_change_pct)}%` : "—"}</span>}
              sub={p.worst ? `${p.worst.ticker} ${signed(p.worst.day_change_pct)}%` : ""} />
          </div>
          {p.warnings.length > 0 && <Notice kind="warn">{p.warnings.join(" · ")}</Notice>}
        </div>
      ))}
      {history.length > 1 && (
        <div className="card mb-4">
          <h2 className="h2">{ov.portfolios[0].portfolio.name} — value (90 days, reconstructed from ledger and daily closes)</h2>
          <div className="h-64">
            <ResponsiveContainer>
              <AreaChart data={history}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={30} />
                <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} width={70} />
                <Tooltip formatter={(v: number) => fmt(v)} />
                <Area type="monotone" dataKey="value" stroke="#b3121b" fill="#b3121b22" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Market status" value={`${open} open`} sub={`${symbols.length} active symbols · approximate regular hours`} />
        <Stat label="Data health" value={stale ? `${stale} stale` : "Fresh"} cls={stale ? "text-amber-700" : "pos"}
          sub={`Last poll ${ago(market.last_poll.finished_at)} · every ${market.quote_refresh_s}s`} />
        <Stat label="E-Paper devices" value={`${online}/${devices.length} online`} sub={<Link className="underline" to="/devices">Manage</Link>} />
        <Stat label="AI status" value={aiDefault ? aiDefault.name : "Not configured"}
          sub={aiDefault ? (aiDefault.last_test_ok === null ? "Not tested" : aiDefault.last_test_ok ? `OK · ${aiDefault.last_test_latency_ms} ms` : "Last test failed") : <Link className="underline" to="/ai">Configure</Link>} />
      </div>
      {ov.benchmarks.length > 0 && (
        <div className="card mt-4 overflow-x-auto">
          <h2 className="h2">Benchmarks <span className="text-xs font-normal text-stone-500">(index levels, separate from portfolio returns)</span></h2>
          <table className="tbl">
            <thead><tr><th>Index</th><th>Level</th><th>Day</th><th>1M</th><th>YTD</th><th>1Y</th><th>Status</th></tr></thead>
            <tbody>
              {ov.benchmarks.map((b: any) => (
                <tr key={b.id}>
                  <td>{b.name} <span className="text-xs text-stone-400">{b.symbol}</span></td>
                  <td>{fmt(b.level)}</td>
                  <td className={pnlClass(b.day_change_pct)}>{signed(b.day_change_pct)}%</td>
                  <td className={pnlClass(b.ret_1m)}>{b.ret_1m ? `${signed(b.ret_1m)}%` : "—"}</td>
                  <td className={pnlClass(b.ret_ytd)}>{b.ret_ytd ? `${signed(b.ret_ytd)}%` : "—"}</td>
                  <td className={pnlClass(b.ret_1y)}>{b.ret_1y ? `${signed(b.ret_1y)}%` : "—"}</td>
                  <td>{b.stale ? <span className="badge-warn">stale</span> : <span className="badge-ok">ok</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
