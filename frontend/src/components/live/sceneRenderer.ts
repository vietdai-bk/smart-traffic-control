/**
 * Render khung hình camera tổng hợp trên canvas (US03, US05) — phong cách ban ngày, tông sáng.
 * Dùng cùng hiệu chuẩn phối cảnh với backend để đường, làn, vạch dừng, ROI khớp với bounding box.
 */
import type { Calibration, FrameObject, FrameTrack } from "@/lib/types";

const VEHICLE_COLORS = ["#cbd5e1", "#f8fafc", "#334155", "#b91c1c", "#1d4ed8", "#64748b", "#b45309", "#047857"];
export const CLASS_NAMES = ["car", "motorbike", "bus", "truck"] as const;
// Cùng bảng màu phân loại đã kiểm định cho biểu đồ (đủ tương phản trên nền sáng)
export const CLASS_BOX_COLOR = ["#0891B2", "#65A30D", "#DB2777", "#EA580C"];

function yOf(c: Calibration, dist: number) {
  return c.y_horizon + c.A / Math.max(c.cam_offset + dist + c.d0, 1);
}
function xOf(c: Calibration, lat: number, dist: number) {
  return 0.5 + (lat * c.fx) / Math.max(c.cam_offset + dist + c.d0, 1);
}

/** Vẽ nền tĩnh (bầu trời, nhà, vỉa hè, mặt đường, vạch kẻ) vào canvas phụ. */
export function drawBackground(ctx: CanvasRenderingContext2D, w: number, h: number, c: Calibration) {
  const X = (v: number) => v * w;
  const Y = (v: number) => v * h;
  const far = c.visible_far_m;
  const half = (c.lanes * c.lane_width) / 2;
  const horizonY = yOf(c, far + 40);

  // Bầu trời
  const sky = ctx.createLinearGradient(0, 0, 0, Y(horizonY));
  sky.addColorStop(0, "#dbe7f3");
  sky.addColorStop(1, "#eef3f8");
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, w, Y(horizonY) + 1);

  // Dãy nhà phía xa
  let bx = 0;
  let seed = 7;
  const facades = ["#c9d3df", "#d7dee7", "#bfcad7", "#e1e6ed"];
  while (bx < w) {
    seed = (seed * 9301 + 49297) % 233280;
    const bw = 30 + (seed % 60);
    const bh = 18 + (seed % 46);
    ctx.fillStyle = facades[seed % facades.length];
    ctx.fillRect(bx, Y(horizonY) - bh, bw - 3, bh);
    ctx.fillStyle = "rgba(148, 163, 184, 0.55)";
    for (let i = 0; i < Math.floor((bw - 8) / 8); i++) {
      for (let j = 0; j < Math.floor((bh - 6) / 9); j++) ctx.fillRect(bx + 4 + i * 8, Y(horizonY) - bh + 4 + j * 9, 4, 4);
    }
    bx += bw;
  }

  // Vỉa hè / nền đất
  ctx.fillStyle = "#e3e8ee";
  ctx.fillRect(0, Y(horizonY), w, h - Y(horizonY));

  // Mặt đường
  const near = -10;
  const road = [
    [xOf(c, -half - 0.6, far + 40), yOf(c, far + 40)],
    [xOf(c, half + 0.6, far + 40), yOf(c, far + 40)],
    [xOf(c, half + 0.6, near), yOf(c, near)],
    [xOf(c, -half - 0.6, near), yOf(c, near)],
  ];
  const asphalt = ctx.createLinearGradient(0, Y(horizonY), 0, h);
  asphalt.addColorStop(0, "#a4adba");
  asphalt.addColorStop(1, "#8c96a4");
  ctx.fillStyle = asphalt;
  ctx.beginPath();
  road.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))));
  ctx.closePath();
  ctx.fill();

  // Bó vỉa
  ctx.strokeStyle = "#f8fafc";
  ctx.lineWidth = 2;
  for (const s of [-1, 1]) {
    ctx.beginPath();
    ctx.moveTo(X(xOf(c, s * half, far + 40)), Y(yOf(c, far + 40)));
    ctx.lineTo(X(xOf(c, s * half, near)), Y(yOf(c, near)));
    ctx.stroke();
  }

  // Vạch phân làn (nét đứt)
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  for (let l = 1; l < c.lanes; l++) {
    const lat = -half + l * c.lane_width;
    for (let d = 2; d < far + 40; d += 9) {
      ctx.lineWidth = Math.max(1, 2.4 * (c.fx / (c.cam_offset + d + c.d0)) * 12);
      ctx.beginPath();
      ctx.moveTo(X(xOf(c, lat, d)), Y(yOf(c, d)));
      ctx.lineTo(X(xOf(c, lat, d + 4)), Y(yOf(c, d + 4)));
      ctx.stroke();
    }
  }

  // Vạch người đi bộ
  ctx.fillStyle = "rgba(255,255,255,0.92)";
  const stripes = Math.round(c.lanes * 2.2);
  for (let i = 0; i < stripes; i++) {
    const a = -half + (i + 0.2) * ((2 * half) / stripes);
    const b = a + ((2 * half) / stripes) * 0.55;
    ctx.beginPath();
    ctx.moveTo(X(xOf(c, a, -1.5)), Y(yOf(c, -1.5)));
    ctx.lineTo(X(xOf(c, b, -1.5)), Y(yOf(c, -1.5)));
    ctx.lineTo(X(xOf(c, b, -5)), Y(yOf(c, -5)));
    ctx.lineTo(X(xOf(c, a, -5)), Y(yOf(c, -5)));
    ctx.fill();
  }

  // Vạch dừng
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = Math.max(3, h * 0.008);
  ctx.beginPath();
  ctx.moveTo(X(xOf(c, -half, 0)), Y(yOf(c, 0)));
  ctx.lineTo(X(xOf(c, half, 0)), Y(yOf(c, 0)));
  ctx.stroke();

  // Mũi tên mặt đường
  ctx.fillStyle = "rgba(255,255,255,0.75)";
  for (let l = 0; l < c.lanes; l++) {
    const lat = -half + (l + 0.5) * c.lane_width;
    const d0 = 12;
    const s = c.fx / (c.cam_offset + d0 + c.d0);
    const cx = X(xOf(c, lat, d0));
    const cy = Y(yOf(c, d0));
    const aw = s * w * 0.7;
    ctx.beginPath();
    ctx.moveTo(cx, cy + aw * 0.5);
    ctx.lineTo(cx - aw * 0.45, cy - aw * 0.1);
    ctx.lineTo(cx - aw * 0.15, cy - aw * 0.1);
    ctx.lineTo(cx - aw * 0.15, cy - aw * 0.9);
    ctx.lineTo(cx + aw * 0.15, cy - aw * 0.9);
    ctx.lineTo(cx + aw * 0.15, cy - aw * 0.1);
    ctx.lineTo(cx + aw * 0.45, cy - aw * 0.1);
    ctx.closePath();
    ctx.fill();
  }
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

/** Vẽ phương tiện nhìn từ phía trước-trên (xe đang tiến về camera). */
export function drawVehicle(ctx: CanvasRenderingContext2D, o: FrameObject, w: number, h: number) {
  const [x1, y1, x2, y2, cls, color] = o;
  const X1 = x1 * w;
  const Y1 = y1 * h;
  const bw = (x2 - x1) * w;
  const bh = (y2 - y1) * h;
  if (bw < 1 || bh < 1) return;
  const body = VEHICLE_COLORS[color % VEHICLE_COLORS.length];
  ctx.save();
  // bóng đổ
  ctx.fillStyle = "rgba(51,65,85,0.25)";
  ctx.fillRect(X1 + bw * 0.04, Y1 + bh * 0.92, bw * 0.96, bh * 0.1);

  if (cls === 1) {
    // xe máy + người lái
    ctx.fillStyle = "#1f2937";
    roundRect(ctx, X1 + bw * 0.3, Y1 + bh * 0.45, bw * 0.4, bh * 0.55, bw * 0.15);
    ctx.fill();
    ctx.fillStyle = body;
    roundRect(ctx, X1 + bw * 0.15, Y1 + bh * 0.3, bw * 0.7, bh * 0.38, bw * 0.2);
    ctx.fill();
    ctx.strokeStyle = "rgba(15,23,42,0.35)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = ["#ef4444", "#facc15", "#f8fafc", "#3b82f6"][color % 4];
    ctx.beginPath();
    ctx.arc(X1 + bw * 0.5, Y1 + bh * 0.18, Math.max(1.5, bw * 0.24), 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
    return;
  }

  const bodyColor = cls === 2 ? ["#facc15", "#22c55e", "#f97316", "#e2e8f0"][color % 4] : body;
  ctx.fillStyle = bodyColor;
  roundRect(ctx, X1, Y1 + bh * 0.08, bw, bh * 0.9, Math.max(2, bw * 0.12));
  ctx.fill();
  ctx.strokeStyle = "rgba(15,23,42,0.45)";
  ctx.lineWidth = 1;
  ctx.stroke();

  if (cls === 0) {
    // ô tô: mui + kính chắn gió
    ctx.fillStyle = "rgba(30,41,59,0.8)";
    roundRect(ctx, X1 + bw * 0.14, Y1 + bh * 0.2, bw * 0.72, bh * 0.38, bw * 0.08);
    ctx.fill();
    ctx.fillStyle = "rgba(226,232,240,0.45)";
    ctx.fillRect(X1 + bw * 0.2, Y1 + bh * 0.24, bw * 0.6, bh * 0.08);
  } else if (cls === 2) {
    // xe buýt: dải cửa sổ
    ctx.fillStyle = "rgba(30,41,59,0.8)";
    roundRect(ctx, X1 + bw * 0.08, Y1 + bh * 0.16, bw * 0.84, bh * 0.36, 2);
    ctx.fill();
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(X1 + bw * 0.3, Y1 + bh * 0.1, bw * 0.4, bh * 0.05);
    ctx.fillStyle = "#fbbf24";
    ctx.font = `${Math.max(6, bw * 0.12)}px JetBrains Mono, monospace`;
    ctx.textAlign = "center";
    if (bw > 30) ctx.fillText("DN", X1 + bw / 2, Y1 + bh * 0.14);
  } else {
    // xe tải: cabin + thùng hàng
    ctx.fillStyle = "rgba(100,116,139,0.95)";
    ctx.fillRect(X1 + bw * 0.04, Y1 + bh * 0.1, bw * 0.92, bh * 0.38);
    ctx.fillStyle = "rgba(30,41,59,0.8)";
    roundRect(ctx, X1 + bw * 0.16, Y1 + bh * 0.52, bw * 0.68, bh * 0.2, 2);
    ctx.fill();
  }
  // đèn pha
  ctx.fillStyle = "#fef9c3";
  ctx.strokeStyle = "rgba(15,23,42,0.4)";
  const lr = Math.max(1.2, bw * 0.06);
  ctx.beginPath();
  ctx.arc(X1 + bw * 0.16, Y1 + bh * 0.84, lr, 0, Math.PI * 2);
  ctx.arc(X1 + bw * 0.84, Y1 + bh * 0.84, lr, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

export function drawOverlay(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  roi: number[][],
  line: number[][],
  tracks: FrameTrack[],
  showRoi: boolean,
  showBoxes: boolean,
) {
  if (showRoi && roi.length >= 3) {
    ctx.save();
    ctx.fillStyle = "rgba(37,99,235,0.10)";
    ctx.strokeStyle = "#2563EB";
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    roi.forEach(([x, y], i) => (i ? ctx.lineTo(x * w, y * h) : ctx.moveTo(x * w, y * h)));
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.font = "600 10px JetBrains Mono, monospace";
    label(ctx, "ROI", roi[0][0] * w, roi[0][1] * h - 2, "#2563EB");
    if (line.length === 2) {
      ctx.strokeStyle = "#D97706";
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(line[0][0] * w, line[0][1] * h);
      ctx.lineTo(line[1][0] * w, line[1][1] * h);
      ctx.stroke();
      label(ctx, "VẠCH ĐẾM", line[1][0] * w + 4, line[1][1] * h + 6, "#D97706");
    }
    ctx.restore();
  }
  if (!showBoxes) return;
  ctx.save();
  ctx.font = "600 10px JetBrains Mono, monospace";
  for (const t of tracks) {
    const [id, x1, y1, x2, y2, cls, conf, stopped] = t;
    const col = CLASS_BOX_COLOR[cls] ?? "#0891B2";
    const X1 = x1 * w;
    const Y1 = y1 * h;
    const bw = (x2 - x1) * w;
    const bh = (Math.min(y2, 1) - y1) * h;
    ctx.strokeStyle = "rgba(255,255,255,0.85)";
    ctx.lineWidth = 3.5;
    ctx.strokeRect(X1, Y1, bw, bh);
    ctx.strokeStyle = col;
    ctx.lineWidth = 1.8;
    ctx.strokeRect(X1, Y1, bw, bh);
    if (bw > 14) {
      const text = `${CLASS_NAMES[cls] ?? "?"} ${conf.toFixed(2)}${bw > 46 ? ` #${id}` : ""}`;
      label(ctx, text, X1, Y1 - 1, col);
    }
    if (stopped) {
      ctx.fillStyle = "#DC2626";
      ctx.fillRect(X1 + bw - 6, Y1 + 2, 4, 4);
    }
  }
  ctx.restore();
}

/** Nhãn chữ trắng trên nền màu (đọc rõ trên khung hình sáng). */
function label(ctx: CanvasRenderingContext2D, text: string, x: number, yBottom: number, color: string) {
  const tw = ctx.measureText(text).width + 6;
  ctx.fillStyle = color;
  ctx.fillRect(x, yBottom - 12, tw, 12);
  ctx.fillStyle = "#ffffff";
  ctx.fillText(text, x + 3, yBottom - 3);
}

export function drawNoise(ctx: CanvasRenderingContext2D, w: number, h: number, intensity: number) {
  const n = Math.floor(w * h * 0.0012 * intensity);
  for (let i = 0; i < n; i++) {
    const g = 60 + Math.random() * 120;
    ctx.fillStyle = `rgba(${g},${g},${g},${0.05 + Math.random() * 0.1 * intensity})`;
    ctx.fillRect(Math.random() * w, Math.random() * h, 1.5, 1.5);
  }
}
