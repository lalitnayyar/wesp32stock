import { FormEvent, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { get, post } from "./api";
import { ErrorBox } from "./components/ui";
import AIPage from "./pages/AI";
import AnalyticsPage from "./pages/Analytics";
import ApiKeysPage from "./pages/ApiKeys";
import DashboardPage from "./pages/Dashboard";
import DevicesPage from "./pages/Devices";
import PortfoliosPage from "./pages/Portfolios";
import SettingsPage from "./pages/Settings";
import SimulatorPage from "./pages/Simulator";
import StocksPage from "./pages/Stocks";
import AboutPage from "./pages/About";
import FlashPage from "./pages/Flash";

export interface About {
  application: string;
  version: string;
  owner: { name: string; email: string; phone: string };
  disclaimer: string;
  environment: string;
  simulator_enabled: boolean;
  market_provider: string;
}

function Login({ onDone }: { onDone: () => void }) {
  const [u, setU] = useState("admin");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await post("/api/v1/auth/login", { username: u, password: p });
      onDone();
    } catch (ex: any) {
      setErr(ex.message);
    }
  };
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm">
        <div className="bg-brand text-white -m-4 mb-4 p-4 rounded-t-lg font-semibold">Lalit Stock Application</div>
        <label className="label">Username</label>
        <input className="input" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" />
        <label className="label">Password</label>
        <input className="input" type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" />
        <ErrorBox error={err} />
        <button className="btn w-full justify-center mt-4">Sign in</button>
        <p className="text-xs text-stone-500 mt-3">Not financial advice. Market data may be delayed or inaccurate.</p>
      </form>
    </div>
  );
}

const NAV: [string, string][] = [
  ["/", "Dashboard"],
  ["/portfolios", "Portfolios"],
  ["/stocks", "Stocks"],
  ["/analytics", "Analytics"],
  ["/devices", "E-Paper Devices"],
  ["/simulator", "E-Paper Simulator"],
  ["/api-keys", "API Management"],
  ["/ai", "AI Settings"],
  ["/settings", "Settings"],
  ["/flash", "Flash ESP32"],
  ["/about", "About"],
];

export default function App() {
  const [user, setUser] = useState<string | null | undefined>(undefined);
  const [about, setAbout] = useState<About | null>(null);
  const [open, setOpen] = useState(false);

  const check = () =>
    get("/api/v1/auth/me")
      .then((r) => setUser(r.username))
      .catch(() => setUser(null));

  useEffect(() => {
    check();
    get<About>("/api/v1/about").then(setAbout).catch(() => undefined);
    const h = () => setUser(null);
    window.addEventListener("ls:unauthorized", h);
    return () => window.removeEventListener("ls:unauthorized", h);
  }, []);

  if (user === undefined) return <div className="p-6 text-stone-500">Loading…</div>;
  if (user === null) return <Login onDone={check} />;

  const logout = async () => {
    await post("/api/v1/auth/logout").catch(() => undefined);
    setUser(null);
  };

  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <aside className={`md:w-56 bg-stone-900 text-stone-200 md:min-h-screen ${open ? "" : "max-md:hidden"}`}>
        <div className="p-4 font-semibold text-white border-b border-stone-700 hidden md:block">
          Lalit Stock<span className="text-brand"> ▮</span>
        </div>
        <nav className="flex flex-col p-2 gap-0.5">
          {NAV.filter(([to]) => to !== "/simulator" || about?.simulator_enabled !== false).map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `px-3 py-2 rounded text-sm ${isActive ? "bg-brand text-white" : "hover:bg-stone-800"}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-stone-200 px-4 py-2 flex items-center gap-3">
          <button className="btn-alt md:hidden" onClick={() => setOpen(!open)}>☰</button>
          <span className="font-semibold md:hidden">Lalit Stock</span>
          <span className="ml-auto text-sm text-stone-500">
            {about && <span className="badge mr-2">{about.environment} · {about.market_provider}</span>}
            {user}
          </span>
          <button className="btn-alt" onClick={logout}>Sign out</button>
        </header>
        <main className="p-4 flex-1 min-w-0">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/portfolios/*" element={<PortfoliosPage />} />
            <Route path="/stocks" element={<StocksPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/simulator" element={<SimulatorPage />} />
            <Route path="/api-keys" element={<ApiKeysPage />} />
            <Route path="/ai" element={<AIPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/flash" element={<FlashPage />} />
            <Route path="/about" element={<AboutPage about={about} />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
        <footer className="text-xs text-stone-500 px-4 py-3 border-t border-stone-200 bg-white">
          Lalit Stock Application {about?.version} · Owner: Lalit Nayyar · consult@lalit.cloud · +971568391973 ·{" "}
          <b>Not financial advice.</b> Market data may be delayed, incomplete or inaccurate. AI output may be wrong.
        </footer>
      </div>
    </div>
  );
}
