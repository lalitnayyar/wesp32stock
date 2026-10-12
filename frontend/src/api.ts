// Minimal API client: same-origin cookie session + CSRF double-submit header.
export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
  }
}

function csrf(): string {
  const m = document.cookie.match(/(?:^|;\s*)ls_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrf();
  const r = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (r.status === 304) return null as T;
  let data: any = null;
  try {
    data = await r.json();
  } catch {
    /* empty body */
  }
  if (!r.ok) {
    if (r.status === 401 && !path.endsWith("/auth/login")) window.dispatchEvent(new Event("ls:unauthorized"));
    const msg = data?.error?.message ?? `HTTP ${r.status}`;
    const det = data?.error?.details;
    throw new ApiError(r.status, det ? `${msg}: ${det.map((d: any) => `${d.loc.slice(1).join(".")} ${d.message}`).join("; ")}` : msg, det);
  }
  return data as T;
}

export const get = <T = any>(p: string) => api<T>(p);
export const post = <T = any>(p: string, body: unknown = {}) => api<T>(p, { method: "POST", body });
export const put = <T = any>(p: string, body: unknown) => api<T>(p, { method: "PUT", body });
export const del = <T = any>(p: string, body?: unknown) => api<T>(p, { method: "DELETE", body });

export const fmt = (v: string | number | null | undefined, digits = 2) => {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
};
export const signed = (v: string | number | null | undefined, digits = 2) => {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  return (n > 0 ? "+" : "") + fmt(n, digits);
};
export const pnlClass = (v: string | number | null | undefined) =>
  v === null || v === undefined ? "" : Number(v) > 0 ? "pos" : Number(v) < 0 ? "neg" : "";
export const ago = (iso: string | null | undefined) => {
  if (!iso) return "never";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
