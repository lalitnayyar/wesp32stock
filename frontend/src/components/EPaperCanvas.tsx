import { useEffect, useRef } from "react";
import { renderPage } from "../sim/render";
import { Layout, LAYOUT, Op } from "../sim/rules";

/** Exact logical canvas (168x384 or 400x300); `scale` enlarges it with nearest-neighbour scaling only (no reflow). */
export default function EPaperCanvas({ header, body, scale = 1, waiting = false, label, layout = LAYOUT }: {
  header: Op[]; body: Op[] | null; scale?: number; waiting?: boolean; label?: string; layout?: Layout;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const L = layout;
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (ctx) renderPage(ctx, header, body, waiting, L);
  }, [header, body, waiting, L]);
  return (
    <figure className="inline-block">
      <canvas
        ref={ref}
        width={L.width}
        height={L.height}
        style={{ width: L.width * scale, height: L.height * scale, imageRendering: "pixelated" }}
        className="border-4 border-stone-700 rounded-sm shadow"
      />
      {label && <figcaption className="text-xs text-stone-500 text-center mt-1">{label}</figcaption>}
    </figure>
  );
}

export function ColorLegend({ palette = "KWRY" }: { palette?: string }) {
  const all: [string, string, string][] = [["K", "#1b1b1b", "Black"], ["W", "#f2f0e8", "White"], ["R", "#b3121b", "Red"], ["Y", "#e3b505", "Yellow"]];
  return (
    <div className="flex flex-wrap gap-3 text-xs items-center">
      {all.filter(([k]) => palette.includes(k)).map(([, c, n]) => (
        <span key={n} className="flex items-center gap-1"><span className="w-3 h-3 border border-stone-400 inline-block" style={{ background: c }} />{n}</span>
      ))}
      <span className="text-stone-500">Browser colours approximate the physical pigments of this {palette.length}-colour panel.</span>
    </div>
  );
}
