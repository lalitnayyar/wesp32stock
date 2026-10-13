// Web flasher helpers: firmware manifest (firmware/dist/manifest.json, served at /firmware/) and boot-log parsing.
// Lalit Stock Application - Owner: Lalit Nayyar. Not financial advice.

export type Sketch = "firmware" | "test";
export type Wiring = "standard" | "uart2";

export interface Part {
  path: string;
  offset: number;
  size: number;
  sha256: string;
}

export interface Target {
  id: string;
  sketch: Sketch;
  build: string;
  profile: string;
  module: string;
  wiring: Wiring;
  parts: Part[];
}

export interface Manifest {
  name: string;
  version: string;
  commit: string;
  built_at: string;
  chip: string;
  targets: Target[];
}

export const WIRINGS: { id: Wiring; name: string; detail: string }[] = [
  { id: "standard", name: "Standard", detail: "D/C → GPIO25, RES → GPIO26" },
  { id: "uart2", name: "TX2/RX2", detail: "D/C → TX2 (GPIO17), RES → RX2 (GPIO16), as in ESP32-Epaper-Wiring.png" },
];

export function findTarget(m: Manifest | null, sketch: Sketch, build: string, wiring: Wiring): Target | null {
  return m?.targets.find((t) => t.sketch === sketch && t.build === build && t.wiring === wiring) ?? null;
}

export function totalSize(t: Target): number {
  return t.parts.reduce((n, p) => n + p.size, 0);
}

export async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new Uint8Array(data));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Download every part and verify its size and SHA-256 against the manifest before anything is written. */
export async function fetchParts(t: Target, base = "/firmware/"): Promise<{ data: Uint8Array; address: number }[]> {
  const out = [];
  for (const p of t.parts) {
    const r = await fetch(base + p.path, { cache: "no-store" });
    if (!r.ok) throw new Error(`Download failed for ${p.path}: HTTP ${r.status}`);
    const data = new Uint8Array(await r.arrayBuffer());
    if (data.length !== p.size) throw new Error(`${p.path}: size ${data.length} does not match the manifest (${p.size})`);
    if ((await sha256Hex(data)) !== p.sha256) throw new Error(`${p.path}: checksum does not match the manifest`);
    out.push({ data, address: p.offset });
  }
  return out;
}

export interface BootInfo {
  firmware?: string;
  panel?: string;
  wiring?: string;
  deviceId?: string;
  setupSsid?: string;
  setupPassword?: string;
  refreshUs?: number;
  testPanel?: string;
}

/** Pull the useful facts out of the firmware / display-test serial log. */
export function parseBootLog(log: string): BootInfo {
  const info: BootInfo = {};
  const m = (re: RegExp) => log.match(re);
  let x;
  if ((x = m(/Lalit Stock Application firmware (\S+)/))) info.firmware = x[1];
  if ((x = m(/\[hw\] panel (\S+) \([^)]*\), wiring (.+)/))) { info.panel = x[1]; info.wiring = x[2].trim(); }
  if ((x = m(/\[id\] device (LS-[0-9A-F]{6})/))) info.deviceId = x[1];
  if ((x = m(/\[web\] setup AP '([^']+)' password '([^']+)'/))) { info.setupSsid = x[1]; info.setupPassword = x[2]; }
  const refreshes = [...log.matchAll(/_Update_\w+ : (\d+)/g)].map((r) => Number(r[1]));
  if (refreshes.length) info.refreshUs = refreshes[refreshes.length - 1];
  if ((x = m(/ESP32 E-PAPER TEST \(([^)]*\))\)/))) info.testPanel = x[1];
  return info;
}

/**
 * GxEPD2 prints refresh time in microseconds (or milliseconds for some drivers). A full refresh that
 * "finishes" in under 0.2 s means the ESP32 never saw BUSY: usually wrong wiring option or no panel power.
 */
export function refreshLooksWrong(us?: number): boolean {
  return us !== undefined && us < 200000 && us > 0;
}
