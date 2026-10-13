import { ReactNode, useCallback, useEffect, useState } from "react";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fn());
      setError(null);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, error, loading, reload, setData };
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="my-2 rounded border border-red-200 bg-red-50 text-red-800 text-sm px-3 py-2">{error}</div>;
}

export function Notice({ children, kind = "info" }: { children: ReactNode; kind?: "info" | "warn" | "ok" }) {
  const cls = {
    info: "border-sky-200 bg-sky-50 text-sky-900",
    warn: "border-amber-300 bg-amber-50 text-amber-900",
    ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
  }[kind];
  return <div className={`my-2 rounded border text-sm px-3 py-2 ${cls}`}>{children}</div>;
}

export function Stat({ label, value, sub, cls = "" }: { label: string; value: ReactNode; sub?: ReactNode; cls?: string }) {
  return (
    <div className="card">
      <div className="text-xs text-stone-500">{label}</div>
      <div className={`text-xl font-semibold ${cls}`}>{value}</div>
      {sub && <div className="text-xs text-stone-500 mt-0.5">{sub}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className={`card ${wide ? "max-w-4xl" : "max-w-lg"} w-full max-h-[90vh] overflow-auto`} onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-2">
          <h3 className="h2 mb-0">{title}</h3>
          <button className="btn-alt" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; bad: boolean } | null>(null);
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fn();
      if (ok) setMsg({ text: ok, bad: false });
      return r;
    } catch (e: any) {
      setMsg({ text: e.message ?? String(e), bad: true });
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  const view = msg ? (
    <div className={`text-sm my-1 ${msg.bad ? "text-red-700" : "text-emerald-700"}`}>{msg.text}</div>
  ) : null;
  return { busy, run, view, setMsg };
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
