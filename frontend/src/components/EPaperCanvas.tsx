import { useEffect, useRef } from "react";
import { renderPage } from "../sim/render";
import { LAYOUT, Op } from "../sim/rules";

/** Exact 168x384 logical canvas; `scale` enlarges it with nearest-neighbour scaling only (no reflow). */
export default function EPaperCanvas({ header, body, scale = 1, waiting = false, label }: {
  header: Op[]; body: Op[] | null; scale?: number; waiting?: boolean; label?: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (ctx) renderPage(ctx, header, body, waiting);
  }, [header, body, waiting]);
  return (
    <figure className="inline-block">
      <canvas
        ref={ref}
        width={LAYOUT.width}
        height={LAYOUT.height}
        style={{ width: LAYOUT.width * scale, height: LAYOUT.height * scale, imageRendering: "pixelated" }}
        className="border-4 border-stone-700 rounded-sm shadow"
      />
      {label && <figcaption className="text-xs text-stone-500 text-center mt-1">{label}</figcaption>}
    </figure>
  );
}

export function ColorLegend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs items-center">
      {[["#1b1b1b", "Black"], ["#f2f0e8", "White"], ["#b3121b", "Red"], ["#e3b505", "Yellow"]].map(([c, n]) => (
        <span key={n} className="flex items-center gap-1"><span className="w-3 h-3 border border-stone-400 inline-block" style={{ background: c }} />{n}</span>
      ))}
      <span className="text-stone-500">Browser colours approximate the physical 4-colour pigments.</span>
    </div>
  );
}
