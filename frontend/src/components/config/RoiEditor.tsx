import { useRef, useState } from "react";

/** Trình chỉnh ROI (đa giác 4 điểm) và vạch đếm (2 điểm) bằng kéo-thả trên khung 16:9 (US06-T01, US15-T03). */
export function RoiEditor({
  roi,
  line,
  onChange,
  readOnly,
}: {
  roi: number[][];
  line: number[][];
  onChange: (roi: number[][], line: number[][]) => void;
  readOnly?: boolean;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<{ kind: "roi" | "line"; i: number } | null>(null);
  const W = 640;
  const H = 360;

  const toNorm = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
    return [Math.round(x * 10000) / 10000, Math.round(y * 10000) / 10000];
  };

  const onMove = (e: React.PointerEvent) => {
    if (!drag || readOnly) return;
    const p = toNorm(e);
    if (drag.kind === "roi") onChange(roi.map((q, i) => (i === drag.i ? p : q)), line);
    else onChange(roi, line.map((q, i) => (i === drag.i ? p : q)));
  };

  return (
    <svg
      ref={ref}
      viewBox={`0 0 ${W} ${H}`}
      className="w-full touch-none select-none rounded-ctl border border-line bg-[#e3e8ee]"
      onPointerMove={onMove}
      onPointerUp={() => setDrag(null)}
      onPointerLeave={() => setDrag(null)}
      role="application"
      aria-label="Chỉnh vùng ROI và vạch đếm"
    >
      <defs>
        <linearGradient id="road" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#a4adba" />
          <stop offset="1" stopColor="#8c96a4" />
        </linearGradient>
      </defs>
      <rect width={W} height={H * 0.28} fill="#dbe7f3" />
      <polygon points={`${W * 0.47},${H * 0.28} ${W * 0.53},${H * 0.28} ${W * 0.85},${H} ${W * 0.15},${H}`} fill="url(#road)" />
      {[0.16, 0.32, 0.48, 0.64, 0.8].map((y) => (
        <line key={y} x1={0} x2={W} y1={H * y} y2={H * y} stroke="#64748B" strokeOpacity={0.15} />
      ))}
      {roi.length >= 3 && (
        <polygon
          points={roi.map(([x, y]) => `${x * W},${y * H}`).join(" ")}
          fill="rgba(37,99,235,0.12)"
          stroke="#2563EB"
          strokeDasharray="6 4"
          strokeWidth={2}
        />
      )}
      {line.length === 2 && (
        <line x1={line[0][0] * W} y1={line[0][1] * H} x2={line[1][0] * W} y2={line[1][1] * H} stroke="#D97706" strokeWidth={3} />
      )}
      {!readOnly &&
        roi.map(([x, y], i) => (
          <g key={`r${i}`} onPointerDown={(e) => { (e.target as Element).setPointerCapture?.(e.pointerId); setDrag({ kind: "roi", i }); }} className="cursor-grab">
            <circle cx={x * W} cy={y * H} r={12} fill="transparent" />
            <circle cx={x * W} cy={y * H} r={6} fill="#FFFFFF" stroke="#2563EB" strokeWidth={2} />
            <text x={x * W + 9} y={y * H - 8} fontSize={10} fill="#1E40AF" fontFamily="JetBrains Mono, monospace">
              R{i + 1}
            </text>
          </g>
        ))}
      {!readOnly &&
        line.map(([x, y], i) => (
          <g key={`l${i}`} onPointerDown={(e) => { (e.target as Element).setPointerCapture?.(e.pointerId); setDrag({ kind: "line", i }); }} className="cursor-grab">
            <circle cx={x * W} cy={y * H} r={12} fill="transparent" />
            <rect x={x * W - 6} y={y * H - 6} width={12} height={12} fill="#FFFFFF" stroke="#D97706" strokeWidth={2} />
          </g>
        ))}
      <text x={10} y={18} fontSize={11} fill="#475569" fontFamily="Plus Jakarta Sans, sans-serif">
        {readOnly ? "Chỉ xem" : "Kéo các điểm tròn (ROI) và vuông (vạch đếm)"}
      </text>
    </svg>
  );
}
