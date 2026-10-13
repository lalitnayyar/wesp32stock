// Flash an ESP32 from the browser (Web Serial + Espressif esptool-js), with the same choices as the
// flash_esp32 wizard: E-Paper module, wiring, firmware or display test. Binaries come from
// firmware/dist (built by ./manage.sh firmware) served at /firmware/. Not financial advice.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBox, Notice } from "../components/ui";
import {
  BootInfo, fetchParts, findTarget, Manifest, parseBootLog, refreshLooksWrong, Sketch, totalSize, Wiring, WIRINGS,
} from "../flash/firmware";
import { MODULES, PANELS, panelSpec } from "../sim/rules";

type Phase = "idle" | "busy" | "done" | "error";
const FLASH_BAUD = 460800;
const LOG_SECONDS = 25;

export default function FlashPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [build, setBuild] = useState(MODULES[0].build);
  const [wiring, setWiring] = useState<Wiring>("standard");
  const [sketch, setSketch] = useState<Sketch>("firmware");
  const [eraseAll, setEraseAll] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [step, setStep] = useState("");
  const [progress, setProgress] = useState<{ part: number; written: number; total: number } | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [boot, setBoot] = useState<BootInfo>({});
  const [error, setError] = useState<string | null>(null);
  const portRef = useRef<SerialPort | null>(null);
  const logRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    fetch("/firmware/manifest.json", { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const m = (await r.json()) as Manifest;
        if (!Array.isArray(m.targets)) throw new Error("not a firmware manifest");
        setManifest(m);
      })
      .catch((e) => setManifestError(String(e.message ?? e)));
  }, []);
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [lines]);

  const supported = typeof navigator !== "undefined" && "serial" in navigator && window.isSecureContext;
  const target = findTarget(manifest, sketch, build, wiring);
  const module = MODULES.find((m) => m.build === build)!;
  const spec = panelSpec(module.profile);
  const say = (s: string) => setLines((l) => [...l.slice(-400), s]);

  // After flashing (or on demand): reset the board via RTS and capture its boot log over the same port.
  async function readBootLog(port: SerialPort) {
    setStep(`Reading the device log for ${LOG_SECONDS} s…`);
    await port.open({ baudRate: 115200 });
    let text = "";
    try {
      await port.setSignals({ dataTerminalReady: false, requestToSend: true });
      await new Promise((r) => setTimeout(r, 150));
      await port.setSignals({ dataTerminalReady: false, requestToSend: false });
      const reader = port.readable!.getReader();
      const decoder = new TextDecoder();
      const stop = setTimeout(() => reader.cancel().catch(() => undefined), LOG_SECONDS * 1000);
      let pending = "";
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          text += chunk;
          pending += chunk;
          const parts = pending.split(/\r?\n/);
          pending = parts.pop() ?? "";
          for (const p of parts) if (p.trim()) say(p);
          setBoot(parseBootLog(text));
        }
      } finally {
        clearTimeout(stop);
        reader.releaseLock();
      }
    } finally {
      await port.close().catch(() => undefined);
    }
    return parseBootLog(text);
  }

  async function flash() {
    if (!target) return;
    setError(null);
    setLines([]);
    setBoot({});
    setProgress(null);
    setPhase("busy");
    let port: SerialPort | null = null;
    try {
      setStep("Choose the ESP32's serial port in the browser dialog…");
      port = await navigator.serial.requestPort(); // needs the click's user activation: ask first
      portRef.current = port;
      setStep("Downloading and verifying firmware files…");
      const files = await fetchParts(target);
      say(`Verified ${files.length} parts (${totalSize(target).toLocaleString()} bytes) for ${target.id}`);
      const { ESPLoader, Transport } = await import("esptool-js");
      const transport = new Transport(port, false);
      const terminal = { clean: () => undefined, writeLine: (d: string) => say(d), write: (d: string) => say(d) };
      const loader = new ESPLoader({ transport, baudrate: FLASH_BAUD, romBaudrate: 115200, terminal });
      setStep("Connecting to the ESP32 bootloader (hold BOOT if it does not connect)…");
      const chip = await loader.main();
      say(`Connected: ${chip}`);
      setStep(eraseAll ? "Erasing flash and writing firmware…" : "Writing firmware…");
      await loader.writeFlash({
        fileArray: files, flashMode: "keep", flashFreq: "keep", flashSize: "keep", eraseAll, compress: true,
        reportProgress: (part, written, total) => setProgress({ part, written, total }),
      });
      say("Flash written and verified by the bootloader. Resetting…");
      await loader.after("hard_reset");
      await transport.disconnect();
      const info = await readBootLog(port);
      setPhase("done");
      setStep(info.deviceId || info.testPanel ? "Done." : "Flashed. No boot log seen yet; use Read device log.");
    } catch (e: any) {
      const msg = e?.name === "NotFoundError" ? "No serial port was selected." : String(e?.message ?? e);
      setError(msg);
      setPhase("error");
      setStep("");
      if (port) await port.close().catch(() => undefined);
    }
  }

  async function readLogOnly() {
    setError(null);
    setLines([]);
    setBoot({});
    setPhase("busy");
    try {
      const port = portRef.current ?? (await navigator.serial.requestPort());
      portRef.current = port;
      await readBootLog(port);
      setPhase("done");
      setStep("Done.");
    } catch (e: any) {
      setError(e?.name === "NotFoundError" ? "No serial port was selected." : String(e?.message ?? e));
      setPhase("error");
    }
  }

  const busy = phase === "busy";
  const pct = progress && progress.total ? Math.round((progress.written / progress.total) * 100) : 0;
  const badRefresh = refreshLooksWrong(boot.refreshUs);
  const radio = "flex items-start gap-2 p-2 rounded border cursor-pointer";

  return (
    <div>
      <h1 className="h1">Flash ESP32</h1>
      <Notice>
        Flash the Lalit Stock firmware (or the display test) straight from this browser over USB, with the same choices as
        the <code>flash_esp32</code> wizard. Works in Chrome or Edge on a desktop (Web Serial), over HTTPS or localhost.
        Saved Wi-Fi and API settings are kept unless you choose to erase them.
      </Notice>
      {!supported && <Notice kind="warn">This browser cannot flash: use desktop Chrome or Edge, and open the site over HTTPS (or http://localhost).</Notice>}
      {manifestError && (
        <Notice kind="warn">
          No firmware files on this server yet ({manifestError}). Build them once on the server with <code>./manage.sh firmware</code>
          (menu 23), then reload this page.
        </Notice>
      )}

      <div className="grid xl:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="h2">1. E-Paper module</h2>
          <div className="grid gap-1">
            {MODULES.map((m, i) => (
              <label key={m.build} className={`${radio} ${build === m.build ? "border-stone-800 bg-stone-50" : "border-stone-200"}`}>
                <input type="radio" name="module" checked={build === m.build} onChange={() => setBuild(m.build)} disabled={busy} />
                <span className="text-sm">{i + 1}. {m.name}
                  {PANELS.profiles[m.profile]?.verified && <span className="badge-ok ml-2">hardware-verified</span>}
                  <span className="block text-xs text-stone-500">{PANELS.profiles[m.profile]?.label} · build <code>{m.build}</code></span>
                </span>
              </label>
            ))}
          </div>

          <h2 className="h2 mt-4">2. Wiring <span className="text-xs font-normal text-stone-500">BUSY 4, CS 5, SCK 18, MOSI 23 in both</span></h2>
          <div className="grid gap-1">
            {WIRINGS.map((w, i) => (
              <label key={w.id} className={`${radio} ${wiring === w.id ? "border-stone-800 bg-stone-50" : "border-stone-200"}`}>
                <input type="radio" name="wiring" checked={wiring === w.id} onChange={() => setWiring(w.id)} disabled={busy} />
                <span className="text-sm">{i + 1}. {w.name}<span className="block text-xs text-stone-500">{w.detail}</span></span>
              </label>
            ))}
          </div>

          <h2 className="h2 mt-4">3. What to flash</h2>
          <div className="grid gap-1">
            {([["firmware", "Lalit Stock firmware", "Normal use: setup portal, portfolio pages, admin page"],
               ["test", "Display test (Hello World)", "Recommended first on a new module: checks wiring and driver"]] as const).map(([id, name, detail]) => (
              <label key={id} className={`${radio} ${sketch === id ? "border-stone-800 bg-stone-50" : "border-stone-200"}`}>
                <input type="radio" name="sketch" checked={sketch === id} onChange={() => setSketch(id)} disabled={busy} />
                <span className="text-sm">{name}<span className="block text-xs text-stone-500">{detail}</span></span>
              </label>
            ))}
          </div>
          <label className="flex gap-2 items-center text-sm mt-3">
            <input type="checkbox" checked={eraseAll} onChange={(e) => setEraseAll(e.target.checked)} disabled={busy} />
            Erase all settings first (Wi-Fi, API key, admin password: like a factory reset)
          </label>
        </div>

        <div className="card">
          <h2 className="h2">4. Connect &amp; flash</h2>
          <div className="text-sm grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
            <span className="text-stone-500">Module</span><span>{module.name} · {spec.layout.width} × {spec.layout.height}</span>
            <span className="text-stone-500">Wiring</span><span>{WIRINGS.find((w) => w.id === wiring)?.name} ({WIRINGS.find((w) => w.id === wiring)?.detail})</span>
            <span className="text-stone-500">Image</span>
            <span>{target ? <>{target.id} · {(totalSize(target) / 1024).toFixed(0)} KB · firmware {manifest?.version} ({manifest?.commit}) built {manifest && new Date(manifest.built_at).toLocaleString()}</>
              : manifest ? <span className="neg">not built on this server (run ./manage.sh firmware)</span> : "—"}</span>
          </div>
          <p className="text-xs text-stone-500 mt-2">Plug the ESP32 into this computer by USB and close any serial monitor. The browser asks which port to use.</p>
          <div className="flex flex-wrap gap-2 mt-2">
            <button className="btn" disabled={!supported || !target || busy} onClick={flash}>{busy ? "Working…" : "Connect & flash"}</button>
            <button className="btn-alt" disabled={!supported || busy} onClick={readLogOnly}>Read device log</button>
          </div>
          {step && <div className="text-sm mt-2">{step}</div>}
          {progress && (
            <div className="mt-2">
              <div className="h-3 bg-stone-200 rounded overflow-hidden"><div className="h-3 bg-red-700" style={{ width: `${pct}%` }} /></div>
              <div className="text-xs text-stone-500 mt-0.5">Part {progress.part + 1} of {target?.parts.length}: {pct}%</div>
            </div>
          )}
          {error && <div className="mt-2"><ErrorBox error={error} /></div>}

          {(boot.deviceId || boot.testPanel || boot.firmware) && (
            <div className="mt-3 border rounded p-2 text-sm bg-stone-50">
              {boot.firmware && <div>Firmware <b>{boot.firmware}</b>{boot.panel && <> · panel <code>{boot.panel}</code></>}{boot.wiring && <> · wiring {boot.wiring}</>}</div>}
              {boot.testPanel && <div>Display test running: <b>{boot.testPanel}</b>. The panel should show HELLO WORLD.</div>}
              {boot.deviceId && <div>Device ID <b className="font-mono">{boot.deviceId}</b></div>}
              {boot.setupSsid && <div>Setup Wi-Fi <b>{boot.setupSsid}</b>, password <b className="font-mono">{boot.setupPassword}</b>, then open http://192.168.4.1</div>}
              {boot.refreshUs !== undefined && (badRefresh
                ? <div className="neg">Panel refresh finished in {boot.refreshUs} µs: the ESP32 is not seeing BUSY. Check the wiring option and the panel power, then flash again.</div>
                : <div className="pos">Panel refresh took {(boot.refreshUs / 1e6).toFixed(1)} s: the panel is responding.</div>)}
              {boot.deviceId && (
                <Link className="btn mt-2 inline-block" to={`/devices?register=${encodeURIComponent(boot.deviceId)}&module=${encodeURIComponent(module.profile)}`}>
                  Register {boot.deviceId} with this module
                </Link>
              )}
            </div>
          )}

          <pre ref={logRef} className="mt-3 text-xs bg-stone-900 text-stone-100 rounded p-2 h-64 overflow-auto whitespace-pre-wrap">{lines.join("\n") || "Device output appears here."}</pre>
        </div>
      </div>
    </div>
  );
}
