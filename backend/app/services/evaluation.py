"""Evaluation Service (US14): so sánh Trước (FIXED_TIME) và Sau (AUTO — AI Adaptive)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.intersection import Intersection
from app.models.signal import SignalCycle
from app.models.traffic import TrafficStat

MODES = ("FIXED_TIME", "AUTO")


def _pct_change(before: float | None, after: float | None) -> float | None:
    if before in (None, 0) or after is None:
        return None
    return round((after - before) / before * 100.0, 1)


def _rows(db: Session, intersection_id: int | None, since: datetime):
    q = db.query(TrafficStat).filter(TrafficStat.bucket_start >= since, TrafficStat.mode.in_(MODES))
    if intersection_id:
        q = q.filter(TrafficStat.intersection_id == intersection_id)
    return q.all()


def summary(db: Session, intersection_id: int | None, days: int, tz_offset_min: int = 420) -> dict:
    """So sánh có ghép cặp theo giờ trong ngày (matched hour-of-day).

    Hai giai đoạn thường chứa số giờ cao điểm khác nhau; nếu cộng dồn thô, giai đoạn nhiều giờ cao điểm sẽ có lưu lượng
    và thời gian chờ cao hơn bất kể chế độ điều khiển. Vì vậy mỗi chỉ số được tính riêng cho từng giờ (0–23h) rồi lấy
    trung bình trên các giờ mà CẢ HAI chế độ đều có dữ liệu.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = _rows(db, intersection_id, since)
    mediums = {i.id: i.density_medium for i in db.query(Intersection).all()}

    per = {m: defaultdict(lambda: defaultdict(float)) for m in MODES}  # mode -> hour -> metrics
    slots = {m: defaultdict(set) for m in MODES}  # mode -> hour -> {(iid, bucket)}
    totals = {m: defaultdict(float) for m in MODES}
    for r in rows:
        h = (r.bucket_start + timedelta(minutes=tz_offset_min)).hour
        a = per[r.mode][h]
        a["vehicles"] += r.total
        a["pcu"] += r.pcu
        a["wait_w"] += r.avg_wait_s * r.total
        a["queue"] += r.avg_queue_m
        a["density"] += r.avg_density
        a["n"] += 1
        a["busy"] += 1 if r.avg_density >= mediums.get(r.intersection_id, 40) else 0
        slots[r.mode][h].add((r.intersection_id, r.bucket_start, r.bucket_minutes))
        totals[r.mode]["vehicles"] += r.total
        totals[r.mode]["n"] += 1

    matched = sorted(set(per["FIXED_TIME"]) & set(per["AUTO"]))
    weight = {h: per["FIXED_TIME"][h]["vehicles"] + per["AUTO"][h]["vehicles"] for h in matched}
    wsum = sum(weight.values()) or 1.0

    out_modes = {}
    for m in MODES:
        hours_total = sum(b[2] for hh in slots[m].values() for b in hh) / 60.0
        n_int = len({b[0] for hh in slots[m].values() for b in hh}) or 1
        res = {
            "samples": int(totals[m]["n"]),
            "hours": round(hours_total / n_int, 1),
            "vehicles": int(totals[m]["vehicles"]),
            "matched_hours": len(matched),
        }
        if matched:
            def hour_val(h, f):
                return f(per[m][h], sum(b[2] for b in slots[m][h]) / 60.0)

            waits = [(hour_val(h, lambda a, _: a["wait_w"] / a["vehicles"] if a["vehicles"] else 0.0), weight[h]) for h in matched]
            res.update({
                "avg_wait_s": round(sum(v * w for v, w in waits) / wsum, 1),
                "avg_queue_m": round(sum(hour_val(h, lambda a, _: a["queue"] / a["n"]) for h in matched) / len(matched), 1),
                "avg_density": round(sum(hour_val(h, lambda a, _: a["density"] / a["n"]) for h in matched) / len(matched), 1),
                "congestion_rate": round(sum(hour_val(h, lambda a, _: a["busy"] / a["n"] * 100) for h in matched) / len(matched), 1),
                # lưu lượng thông qua trung bình của một nút giao (4 hướng) mỗi giờ
                "throughput_vph": round(sum(hour_val(h, lambda a, hrs: a["vehicles"] / hrs if hrs else 0) for h in matched) / len(matched), 0),
                "throughput_pcu_h": round(sum(hour_val(h, lambda a, hrs: a["pcu"] / hrs if hrs else 0) for h in matched) / len(matched), 0),
            })
        else:
            res.update({k: None for k in ("avg_wait_s", "avg_queue_m", "avg_density", "congestion_rate", "throughput_vph", "throughput_pcu_h")})
        out_modes[m] = res

    cq = db.query(SignalCycle).filter(SignalCycle.started_at >= since, SignalCycle.mode.in_(MODES))
    if intersection_id:
        cq = cq.filter(SignalCycle.intersection_id == intersection_id)
    cyc = defaultdict(lambda: defaultdict(float))
    for c in cq.all():
        d = cyc[c.mode]
        d["n"] += 1
        d["cycle"] += c.cycle_length_s
        d["g_ns"] += c.green_ns_s
        d["g_ew"] += c.green_ew_s
    for m in MODES:
        d = cyc[m]
        n = d["n"]
        out_modes[m]["cycles"] = int(n)
        out_modes[m]["avg_cycle_s"] = round(d["cycle"] / n, 1) if n else None
        out_modes[m]["avg_green_ns_s"] = round(d["g_ns"] / n, 1) if n else None
        out_modes[m]["avg_green_ew_s"] = round(d["g_ew"] / n, 1) if n else None

    b, a = out_modes["FIXED_TIME"], out_modes["AUTO"]
    wait = _pct_change(b["avg_wait_s"], a["avg_wait_s"])
    queue = _pct_change(b["avg_queue_m"], a["avg_queue_m"])
    cong = _pct_change(b["congestion_rate"], a["congestion_rate"])
    dens = _pct_change(b["avg_density"], a["avg_density"])
    thr = _pct_change(b["throughput_vph"], a["throughput_vph"])
    return {
        "days": days,
        "intersection_id": intersection_id,
        "method": "matched_hour_of_day",
        "before": b,
        "after": a,
        "improvement": {
            "wait_reduction_pct": None if wait is None else -wait,
            "queue_reduction_pct": None if queue is None else -queue,
            "congestion_reduction_pct": None if cong is None else -cong,
            "density_reduction_pct": None if dens is None else -dens,
            "throughput_increase_pct": thr,
        },
    }


def hourly(db: Session, intersection_id: int | None, days: int, tz_offset_min: int) -> list[dict]:
    """Hồ sơ theo giờ trong ngày (giờ địa phương) cho từng chế độ."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = _rows(db, intersection_id, since)
    acc = defaultdict(lambda: defaultdict(float))
    for r in rows:
        local = r.bucket_start + timedelta(minutes=tz_offset_min)
        key = (local.hour, r.mode)
        a = acc[key]
        a["veh"] += r.total
        a["wait_w"] += r.avg_wait_s * r.total
        a["queue"] += r.avg_queue_m
        a["density"] += r.avg_density
        a["n"] += 1
        a["minutes"] += r.bucket_minutes
    out = []
    for h in range(24):
        item = {"hour": h}
        for m, prefix in (("FIXED_TIME", "fixed"), ("AUTO", "auto")):
            a = acc.get((h, m))
            if not a or not a["n"]:
                item.update({f"{prefix}_wait": None, f"{prefix}_queue": None, f"{prefix}_density": None,
                             f"{prefix}_flow": None})
                continue
            hours_per_dir = a["minutes"] / 60.0
            item.update({
                f"{prefix}_wait": round(a["wait_w"] / a["veh"], 1) if a["veh"] else None,
                f"{prefix}_queue": round(a["queue"] / a["n"], 1),
                f"{prefix}_density": round(a["density"] / a["n"], 1),
                f"{prefix}_flow": round(a["veh"] / hours_per_dir * 4) if hours_per_dir else None,
            })
        out.append(item)
    return out
