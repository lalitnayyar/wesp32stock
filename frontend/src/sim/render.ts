// Pixel renderer for the 168x384 E-Paper canvas. Reproduces Adafruit GFX classic-font drawing
// (5x7 glyphs in a 6x8 cell, transparent background, integer text size) so the browser preview is
// pixel-identical to the firmware for the same draw-ops. Colours approximate the physical pigments.
import font from "@shared/glcdfont.json";
import { LAYOUT, Op } from "./rules";

export const PANEL_COLORS: Record<string, string> = {
  K: "#1b1b1b", // black pigment
  W: "#f2f0e8", // paper white
  R: "#b3121b", // red pigment
  Y: "#e3b505", // yellow pigment
};

const GLYPHS: number[] = (font as { data: number[] }).data;

export interface Surface {
  fillRect(x: number, y: number, w: number, h: number, color: string): void;
}

export function drawChar(s: Surface, x: number, y: number, ch: number, color: string, size: number) {
  for (let i = 0; i < 5; i++) {
    let line = GLYPHS[ch * 5 + i] ?? 0;
    for (let j = 0; j < 8; j++, line >>= 1) {
      if (line & 1) s.fillRect(x + i * size, y + j * size, size, size, color);
    }
  }
}

export function drawOp(s: Surface, op: Op) {
  const c = (k: string) => PANEL_COLORS[k] ?? PANEL_COLORS.K;
  switch (op[0]) {
    case "T": {
      const [, x, y, size0, color, text] = op;
      const size = Math.min(3, Math.max(1, size0));
      let cx = x;
      for (let i = 0; i < text.length && i < LAYOUT.limits.max_text_len; i++) {
        drawChar(s, cx, y, text.charCodeAt(i) & 0xff, c(color), size);
        cx += LAYOUT.char_w * size;
      }
      break;
    }
    case "F":
      s.fillRect(op[1], op[2], op[3], op[4], c(op[5]));
      break;
    case "R": {
      const [, x, y, w, h, col] = op;
      s.fillRect(x, y, w, 1, c(col));
      s.fillRect(x, y + h - 1, w, 1, c(col));
      s.fillRect(x, y, 1, h, c(col));
      s.fillRect(x + w - 1, y, 1, h, c(col));
      break;
    }
    case "H":
      s.fillRect(op[1], op[2], op[3], 1, c(op[4]));
      break;
  }
}

/** Renders a full page (header/footer + body) onto a canvas 2D context at logical 1:1 pixels. */
export function renderPage(ctx: CanvasRenderingContext2D, header: Op[], body: Op[] | null, waiting = false) {
  const surface: Surface = {
    fillRect: (x, y, w, h, color) => {
      ctx.fillStyle = color;
      ctx.fillRect(x, y, w, h);
    },
  };
  surface.fillRect(0, 0, LAYOUT.width, LAYOUT.height, PANEL_COLORS.W);
  for (const op of header) drawOp(surface, op);
  if (body) for (const op of body.slice(0, LAYOUT.limits.max_ops_per_page)) drawOp(surface, op);
  else if (waiting) {
    drawOp(surface, ["T", 3, 70, 1, "K", "Waiting for data..."]);
    drawOp(surface, ["T", 3, 82, 1, "K", "Check Wi-Fi / API settings"]);
  }
}
