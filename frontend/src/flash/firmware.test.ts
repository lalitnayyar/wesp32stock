import { describe, expect, it } from "vitest";
import { findTarget, Manifest, parseBootLog, refreshLooksWrong, sha256Hex, totalSize } from "./firmware";

const part = (path: string, offset: number, size: number) => ({ path, offset, size, sha256: "x" });
const manifest: Manifest = {
  name: "n", version: "1.1.0", commit: "abc", built_at: "2026-10-14T00:00:00+00:00", chip: "ESP32",
  targets: [
    { id: "firmware-420_bwr-uart2", sketch: "firmware", build: "420_bwr", profile: "SSD1683_GDEY042Z98", module: "m", wiring: "uart2",
      parts: [part("a", 0x1000, 10), part("b", 0x8000, 20), part("c", 0xe000, 30), part("d", 0x10000, 40)] },
    { id: "test-420_bwr-uart2", sketch: "test", build: "420_bwr", profile: "SSD1683_GDEY042Z98", module: "m", wiring: "uart2", parts: [] },
  ],
};

describe("web flasher helpers", () => {
  it("finds the target for module, wiring and sketch", () => {
    expect(findTarget(manifest, "firmware", "420_bwr", "uart2")?.id).toBe("firmware-420_bwr-uart2");
    expect(findTarget(manifest, "test", "420_bwr", "uart2")?.id).toBe("test-420_bwr-uart2");
    expect(findTarget(manifest, "firmware", "420_bwr", "standard")).toBeNull();
    expect(findTarget(null, "firmware", "290_4c", "standard")).toBeNull();
    expect(totalSize(manifest.targets[0])).toBe(100);
  });

  it("parses the firmware boot log", () => {
    const log = [
      "Lalit Stock Application firmware 1.1.0 - not financial advice",
      "[hw] panel SSD1683_GDEY042Z98 (400x300), wiring uart2 (RES 16, D/C 17)",
      "[id] device LS-546EA8 (MAC 04:B2:47:54:6E:A8)",
      "[web] setup AP 'LalitStock-Setup-6EA8' password 'gbus9fhkfe54' at 192.168.4.1",
      "_Update_Fast : 10028003",
    ].join("\r\n");
    expect(parseBootLog(log)).toEqual({ firmware: "1.1.0", panel: "SSD1683_GDEY042Z98", wiring: "uart2 (RES 16, D/C 17)",
      deviceId: "LS-546EA8", setupSsid: "LalitStock-Setup-6EA8", setupPassword: "gbus9fhkfe54", refreshUs: 10028003 });
    expect(refreshLooksWrong(10028003)).toBe(false);
    expect(refreshLooksWrong(parseBootLog("_Update_Fast : 5").refreshUs)).toBe(true);
    expect(parseBootLog("ESP32 E-PAPER TEST (4.2in black/white/red, wiring uart2 (RES 16, D/C 17))").testPanel)
      .toBe("4.2in black/white/red, wiring uart2 (RES 16, D/C 17)");
  });

  it("hashes like sha256sum", async () => {
    expect(await sha256Hex(new TextEncoder().encode("abc")))
      .toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});
