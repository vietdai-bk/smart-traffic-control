import type { Direction, HeadColor, Snapshot } from "@/lib/types";
import { HEAD_COLOR, INTERVAL_LABEL, LEVEL_COLOR, MODE_COLOR, tone } from "@/lib/format";

/**
 * Digital twin nút giao 4 hướng (SVG): đèn từng hướng + đếm ngược, vạch dừng, luồng di chuyển,
 * thanh hàng đợi dạng khối (mỗi khối ≈ 5 m) tô màu theo mức mật độ.
 */
const C0 = 160;
const C1 = 280;
const MID = 220;
const BLOCK_M = 5;

interface ArmGeo {
  stop: [number, number, number, number];
  queue: (i: number) => { x: number; y: number; w: number; h: number };
  flow: string;
  head: { x: number; y: number; horizontal: boolean };
  count: { x: number; y: number; anchor: "start" | "end" | "middle" };
  label: { x: number; y: number; anchor: "start" | "end" | "middle" };
}

const ARMS: Record<Direction, ArmGeo> = {
  NORTH: {
    stop: [C0, 140, MID, 140],
    queue: (i) => ({ x: 172, y: 132 - i * 9, w: 36, h: 7 }),
    flow: `M190 120 L190 ${C1 + 40}`,
    head: { x: 128, y: 100, horizontal: false },
    count: { x: 140, y: 154, anchor: "middle" },
    label: { x: 190, y: 14, anchor: "middle" },
  },
  SOUTH: {
    stop: [MID, 300, C1, 300],
    queue: (i) => ({ x: 232, y: 301 + 7 + i * 9 - 7, w: 36, h: 7 }),
    flow: `M250 320 L250 ${C0 - 40}`,
    head: { x: 292, y: 304, horizontal: false },
    count: { x: 300, y: 296, anchor: "middle" },
    label: { x: 250, y: 432, anchor: "middle" },
  },
  EAST: {
    stop: [300, C0, 300, MID],
    queue: (i) => ({ x: 301 + i * 9, y: 172, w: 7, h: 36 }),
    flow: `M320 190 L${C0 - 40} 190`,
    head: { x: 304, y: 128, horizontal: true },
    count: { x: 362, y: 140, anchor: "middle" },
    label: { x: 436, y: 186, anchor: "end" },
  },
  WEST: {
    stop: [140, MID, 140, C1],
    queue: (i) => ({ x: 132 - i * 9, y: 232, w: 7, h: 36 }),
    flow: `M120 250 L${C1 + 40} 250`,
    head: { x: 74, y: 292, horizontal: true },
    count: { x: 94, y: 326, anchor: "middle" },
    label: { x: 4, y: 264, anchor: "start" },
  },
};

function Lamp({ cx, cy, color, on, flash }: { cx: number; cy: number; color: string; on: boolean; flash?: boolean }) {
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5.2}
      fill={on ? color : "#0f1623"}
      stroke="#000"
      strokeOpacity={0.5}
      className={flash && on ? "animate-blink" : undefined}
      style={on ? { filter: `drop-shadow(0 0 4px ${color})` } : undefined}
    />
  );
}

function SignalHead({ x, y, horizontal, color }: { x: number; y: number; horizontal: boolean; color: HeadColor }) {
  const flash = color === "FLASHING_YELLOW";
  const lamps: [string, boolean][] = [
    [HEAD_COLOR.RED, color === "RED"],
    [HEAD_COLOR.YELLOW, color === "YELLOW" || flash],
    [HEAD_COLOR.GREEN, color === "GREEN"],
  ];
  const w = horizontal ? 40 : 15;
  const h = horizontal ? 15 : 40;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={3.5} fill="#0b111c" stroke="#334155" />
      {lamps.map(([c, on], i) => (
        <Lamp
          key={i}
          cx={horizontal ? x + 7.5 + i * 12.5 : x + 7.5}
          cy={horizontal ? y + 7.5 : y + 7.5 + i * 12.5}
          color={c}
          on={on}
          flash={flash}
        />
      ))}
    </g>
  );
}

export function IntersectionTwin({ snap, nsRoad, ewRoad }: { snap: Snapshot | null; nsRoad: string; ewRoad: string }) {
  const sig = snap?.signal;
  const remaining = sig?.remaining;
  const modeColor = sig ? MODE_COLOR[sig.mode] : "#64748B";
  const intervalColor =
    sig?.interval === "GREEN"
      ? HEAD_COLOR.GREEN
      : sig?.interval === "YELLOW_CLEARANCE" || sig?.interval === "FLASHING_YELLOW"
        ? HEAD_COLOR.YELLOW
        : HEAD_COLOR.RED;

  return (
    <svg viewBox="0 0 440 440" className="h-full w-full select-none" role="img" aria-label="Mô phỏng nút giao thời gian thực">
      <defs>
        <pattern id="blk" width="10" height="10" patternUnits="userSpaceOnUse">
          <path d="M10 0H0V10" fill="none" stroke="var(--twin-building-line)" strokeWidth="0.6" />
        </pattern>
        <marker id="arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0 0L10 5L0 10z" fill="#10B981" />
        </marker>
      </defs>

      {/* Khối nhà 4 góc */}
      {[
        [0, 0],
        [C1, 0],
        [0, C1],
        [C1, C1],
      ].map(([x, y], i) => (
        <g key={i}>
          <rect x={x} y={y} width={C0} height={C0} fill="var(--twin-block)" />
          <rect x={x + 8} y={y + 8} width={C0 - 16} height={C0 - 16} rx={4} fill="var(--twin-building)" stroke="var(--twin-building-line)" />
          <rect x={x + 8} y={y + 8} width={C0 - 16} height={C0 - 16} rx={4} fill="url(#blk)" />
        </g>
      ))}

      {/* Mặt đường */}
      <rect x={C0} y={0} width={C1 - C0} height={440} fill="var(--twin-road)" />
      <rect x={0} y={C0} width={440} height={C1 - C0} fill="var(--twin-road)" />
      <rect x={C0} y={C0} width={C1 - C0} height={C1 - C0} fill="var(--twin-junction)" />
      {/* Bó vỉa */}
      <g stroke="var(--twin-road-edge)" strokeWidth={1.5}>
        <line x1={C0} y1={0} x2={C0} y2={C0} />
        <line x1={C1} y1={0} x2={C1} y2={C0} />
        <line x1={C0} y1={C1} x2={C0} y2={440} />
        <line x1={C1} y1={C1} x2={C1} y2={440} />
        <line x1={0} y1={C0} x2={C0} y2={C0} />
        <line x1={0} y1={C1} x2={C0} y2={C1} />
        <line x1={C1} y1={C0} x2={440} y2={C0} />
        <line x1={C1} y1={C1} x2={440} y2={C1} />
      </g>

      {/* Vạch tim đường */}
      <g stroke="#D97706" strokeOpacity={0.8} strokeWidth={1.4}>
        <line x1={MID} y1={0} x2={MID} y2={140} />
        <line x1={MID} y1={300} x2={MID} y2={440} />
        <line x1={0} y1={MID} x2={140} y2={MID} />
        <line x1={300} y1={MID} x2={440} y2={MID} />
      </g>
      {/* Vạch chia làn */}
      <g stroke="#94A3B8" strokeOpacity={0.8} strokeWidth={1} strokeDasharray="6 7">
        <line x1={190} y1={0} x2={190} y2={140} />
        <line x1={250} y1={0} x2={250} y2={140} />
        <line x1={190} y1={300} x2={190} y2={440} />
        <line x1={250} y1={300} x2={250} y2={440} />
        <line x1={0} y1={190} x2={140} y2={190} />
        <line x1={0} y1={250} x2={140} y2={250} />
        <line x1={300} y1={190} x2={440} y2={190} />
        <line x1={300} y1={250} x2={440} y2={250} />
      </g>
      {/* Vạch người đi bộ */}
      <g fill="#94A3B8" fillOpacity={0.5}>
        {Array.from({ length: 10 }).map((_, i) => (
          <g key={i}>
            <rect x={C0 + 4 + i * 11.6} y={144} width={6} height={13} />
            <rect x={C0 + 4 + i * 11.6} y={283} width={6} height={13} />
            <rect x={144} y={C0 + 4 + i * 11.6} width={13} height={6} />
            <rect x={283} y={C0 + 4 + i * 11.6} width={13} height={6} />
          </g>
        ))}
      </g>

      {/* Tên đường */}
      <g fill="var(--twin-road-text)" fontSize={10} fontFamily="Plus Jakarta Sans, sans-serif" fontWeight={600}>
        <text x={234} y={60} transform="rotate(90 234 60)">{nsRoad}</text>
        <text x={330} y={274}>{ewRoad}</text>
      </g>

      {(["NORTH", "SOUTH", "EAST", "WEST"] as Direction[]).map((d) => {
        const g = ARMS[d];
        const m = snap?.directions[d];
        const head = sig?.heads[d];
        const color = head?.color ?? "OFF";
        const blocks = m ? Math.min(14, Math.ceil(m.queue_m / BLOCK_M)) : 0;
        const lvlColor = m ? LEVEL_COLOR[m.level] : "#334155";
        const camOff = m?.camera?.status === "OFFLINE";
        return (
          <g key={d}>
            {/* Hàng đợi dạng khối */}
            {Array.from({ length: 14 }).map((_, i) => {
              const r = g.queue(i);
              const on = i < blocks;
              return (
                <rect
                  key={i}
                  {...r}
                  rx={1.5}
                  fill={on ? lvlColor : "#E2E8F0"}
                  fillOpacity={on ? 0.9 - i * 0.03 : 0.7}
                  stroke={on ? lvlColor : "none"}
                  strokeOpacity={0.4}
                  style={{ transition: "fill 400ms" }}
                />
              );
            })}
            {/* Vạch dừng */}
            <line x1={g.stop[0]} y1={g.stop[1]} x2={g.stop[2]} y2={g.stop[3]} stroke="#334155" strokeWidth={3} />
            {/* Luồng di chuyển */}
            {(color === "GREEN" || color === "YELLOW") && (
              <path
                d={g.flow}
                stroke={color === "GREEN" ? "#10B981" : "#F59E0B"}
                strokeWidth={2.5}
                strokeDasharray="7 7"
                fill="none"
                markerEnd="url(#arrow)"
                opacity={color === "GREEN" ? 0.9 : 0.5}
              >
                <animate attributeName="stroke-dashoffset" from="28" to="0" dur="0.8s" repeatCount="indefinite" />
              </path>
            )}
            <SignalHead x={g.head.x} y={g.head.y} horizontal={g.head.horizontal} color={color} />
            {/* Đồng hồ đếm ngược dạng LED */}
            <rect x={g.count.x - 15} y={g.count.y - 13} width={30} height={17} rx={3} fill="#FFFFFF" stroke="#CBD5E1" />
            <text
              x={g.count.x}
              y={g.count.y}
              textAnchor="middle"
              fontFamily="JetBrains Mono, monospace"
              fontSize={13}
              fontWeight={600}
              style={{ fontVariantNumeric: "tabular-nums", fill: tone(HEAD_COLOR[color], 80) }}
            >
              {head?.remaining == null ? (color === "FLASHING_YELLOW" ? "~~" : "∞") : Math.ceil(head.remaining).toString().padStart(2, "0")}
            </text>
            {/* Nhãn hướng + mật độ */}
            <text
              x={g.label.x}
              y={g.label.y}
              textAnchor={g.label.anchor}
              fontFamily="JetBrains Mono, monospace"
              fontSize={10.5}
              fill={camOff ? "#DC2626" : "var(--twin-road-text)"}
            >
              {camOff ? "CAM OFFLINE" : m ? `${m.density_smoothed.toFixed(0)}% · ${m.queue_m.toFixed(0)}m` : ""}
            </text>
          </g>
        );
      })}

      {/* Trung tâm: pha & đếm ngược */}
      <g>
        <rect x={180} y={182} width={80} height={76} rx={6} fill="#FFFFFF" stroke={intervalColor} strokeWidth={1.5} />
        <text x={MID} y={198} textAnchor="middle" fontSize={9} fill="#64748B" fontFamily="Plus Jakarta Sans, sans-serif">
          {sig ? (sig.interval === "GREEN" ? `Pha ${sig.phase_id} xanh` : INTERVAL_LABEL[sig.interval]) : "Đang kết nối"}
        </text>
        <text
          x={MID}
          y={230}
          textAnchor="middle"
          fontSize={28}
          fontWeight={600}
          fontFamily="JetBrains Mono, monospace"
          style={{ fontVariantNumeric: "tabular-nums", fill: tone(intervalColor, 85) }}
        >
          {sig ? (remaining == null ? (sig.interval === "FLASHING_YELLOW" ? "--" : "GIỮ") : Math.ceil(remaining).toString().padStart(2, "0")) : "--"}
        </text>
        <rect x={192} y={239} width={56} height={13} rx={2} fill={modeColor} fillOpacity={0.18} stroke={modeColor} strokeOpacity={0.6} />
        <text x={MID} y={249} textAnchor="middle" fontSize={8.5} fontWeight={700} style={{ fill: tone(modeColor, 80) }} fontFamily="JetBrains Mono, monospace">
          {sig?.mode ?? "—"}
        </text>
      </g>

      {/* La bàn */}
      <g transform="translate(410 30)">
        <circle r={13} fill="#FFFFFF" stroke="#CBD5E1" />
        <path d="M0 -9 L4 3 L0 0 L-4 3 Z" fill="#334155" />
        <text y={10} textAnchor="middle" fontSize={7} fill="#64748B" fontWeight={700}>B</text>
      </g>
    </svg>
  );
}
