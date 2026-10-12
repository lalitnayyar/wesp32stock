import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmt, get, pnlClass, post, signed } from "../api";
import { ErrorBox, Notice, Stat, useAction, useLoad } from "../components/ui";

const TASK_LABELS: Record<string, string> = {
  portfolio_summary: "Portfolio summary", daily_summary: "Daily market summary", contributors: "Contributor analysis",
  concentration: "Concentration warnings", unusual_moves: "Unusual movements", benchmark_comparison: "Benchmark comparison",
  risk: "Risk observations", question: "Ask a question",
};

function Exposure({ title, data }: { title: string; data: Record<string, string> }) {
  const rows = Object.entries(data).map(([k, v]) => ({ name: k, pct: Number(v) }));
  return (
    <div className="card">
      <h2 className="h2">{title}</h2>
      <div style={{ height: Math.max(120, rows.length * 28) }}>
        <ResponsiveContainer><BarChart data={rows} layout="vertical" margin={{ left: 20 }}>
          <XAxis type="number" unit="%" tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: number) => `${fmt(v)}%`} /><Bar dataKey="pct" fill="#b3121b" /></BarChart></ResponsiveContainer>
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const { data: pfs, error } = useLoad(() => get("/api/v1/portfolios"));
  const [pid, setPid] = useState<number | null>(null);
  const [summary, setSummary] = useState<any>(null);
  const [bench, setBench] = useState<any[]>([]);
  const [task, setTask] = useState("portfolio_summary");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<any>(null);
  const act = useAction();
  useEffect(() => { if (pfs?.length && pid === null) setPid(pfs[0].id); }, [pfs, pid]);
  useEffect(() => {
    if (pid) {
      get(`/api/v1/portfolios/${pid}/summary`).then(setSummary);
      get("/api/v1/analytics/overview").then((o) => setBench(o.benchmarks));
    }
  }, [pid]);
  if (error) return <ErrorBox error={error} />;
  const t = summary?.totals;
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h1 className="h1 mb-0">Analytics</h1>
        <select className="input max-w-xs ml-auto" value={pid ?? ""} onChange={(e) => { setPid(Number(e.target.value)); setAnswer(null); }}>
          {pfs?.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      {!pfs?.length && <Notice>Create a portfolio first.</Notice>}
      {summary && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
            <Stat label="Market value" value={fmt(t.market_value)} sub={summary.portfolio.base_currency} />
            <Stat label="Invested capital" value={fmt(t.invested)} />
            <Stat label="Unrealized" value={signed(t.unrealized_pl)} sub={`${signed(t.unrealized_pct)}%`} cls={pnlClass(t.unrealized_pl)} />
            <Stat label="Data freshness" value={summary.freshness.stale_count ? `${summary.freshness.stale_count} stale` : "Fresh"}
              sub={`Oldest quote ${summary.freshness.oldest_quote_age_s ?? "—"} s`} cls={summary.freshness.stale_count ? "text-amber-700" : "pos"} />
          </div>
          <div className="grid lg:grid-cols-2 gap-3 mb-3">
            <Exposure title="Sector exposure" data={summary.exposure.sector} />
            <Exposure title="Currency exposure" data={summary.exposure.currency} />
          </div>
          <div className="grid lg:grid-cols-2 gap-3 mb-3">
            <div className="card overflow-x-auto">
              <h2 className="h2">Performers today</h2>
              <table className="tbl"><thead><tr><th>Ticker</th><th>Day</th><th>Day P/L</th><th>Unrealized</th><th>Alloc.</th></tr></thead>
                <tbody>{[...summary.holdings].sort((a: any, b: any) => Number(b.day_change_pct ?? 0) - Number(a.day_change_pct ?? 0)).map((h: any) => (
                  <tr key={h.stock_id}><td>{h.ticker}</td><td className={pnlClass(h.day_change_pct)}>{signed(h.day_change_pct)}%</td>
                    <td className={pnlClass(h.day_pl)}>{signed(h.day_pl)} {h.currency}</td>
                    <td className={pnlClass(h.unrealized_pct)}>{signed(h.unrealized_pct)}%</td><td>{fmt(h.allocation_pct)}%</td></tr>))}</tbody></table>
            </div>
            <div className="card overflow-x-auto">
              <h2 className="h2">Benchmarks <span className="text-xs font-normal text-stone-500">separate from portfolio returns</span></h2>
              <table className="tbl"><thead><tr><th>Index</th><th>Day</th><th>1M</th><th>3M</th><th>YTD</th><th>1Y</th></tr></thead>
                <tbody>{bench.map((b) => (
                  <tr key={b.id}><td>{b.name}</td>{["day_change_pct", "ret_1m", "ret_3m", "ret_ytd", "ret_1y"].map((k) => (
                    <td key={k} className={pnlClass(b[k])}>{b[k] ? `${signed(b[k])}%` : "—"}</td>))}</tr>))}</tbody></table>
              <p className="text-xs text-stone-500 mt-2">Portfolio today: <span className={pnlClass(t.day_pct)}>{signed(t.day_pct)}%</span></p>
            </div>
          </div>
          <div className="card">
            <h2 className="h2">AI insights</h2>
            <p className="text-xs text-stone-500 mb-2">The AI receives only backend-calculated figures and must separate facts from interpretation. AI output may be wrong and is not financial advice.</p>
            <div className="flex flex-wrap gap-2">
              <select className="input max-w-xs" value={task} onChange={(e) => setTask(e.target.value)}>
                {Object.entries(TASK_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              {task === "question" && <input className="input flex-1" placeholder="e.g. Which holding drives most of my currency risk?" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} />}
              <button className="btn" disabled={act.busy} onClick={async () => setAnswer(await act.run(() => post("/api/v1/ai/insights", { portfolio_id: pid, task, question })))}>
                {act.busy ? "Thinking…" : "Generate"}
              </button>
            </div>
            {act.view}
            {answer && (
              <div className="mt-3">
                <div className="text-xs text-stone-500">{answer.provider} · {answer.model}</div>
                <div className="whitespace-pre-wrap text-sm bg-stone-50 border rounded p-3 mt-1">{answer.text}</div>
                <p className="text-xs text-amber-800 mt-1">{answer.disclaimer}</p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
