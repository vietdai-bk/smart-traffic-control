"""US13 — Thống kê giao thông: lọc theo nút giao / hướng / thời gian, biểu đồ, bảng, xuất CSV/JSON."""
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import CurrentUser, client_ip, require
from app.core.rbac import Perm
from app.db.session import get_db
from app.models.intersection import Intersection
from app.models.traffic import TrafficStat
from app.services.stats import local_midnight_utc

router = APIRouter(prefix="/stats", tags=["Statistics"])
CLASSES = ("car", "motorbike", "bus", "truck")
DIR_VI = {"NORTH": "Bắc", "SOUTH": "Nam", "EAST": "Đông", "WEST": "Tây"}


def _range(preset: str, start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if preset == "today":
        return local_midnight_utc(now), now
    if preset == "24h":
        return now - timedelta(hours=24), now
    if preset == "7d":
        return now - timedelta(days=7), now
    if preset == "custom":
        if not start or not end:
            raise HTTPException(422, "Khoảng thời gian tuỳ chọn cần start và end")
        s = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        e = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        if s >= e:
            raise HTTPException(422, "Thời điểm bắt đầu phải trước thời điểm kết thúc")
        if e - s > timedelta(days=62):
            raise HTTPException(422, "Khoảng thời gian tối đa 62 ngày")
        return s, e
    raise HTTPException(422, "preset phải là today | 24h | 7d | custom")


def _query(db: Session, intersection_id: int | None, direction: str | None, s: datetime, e: datetime):
    q = db.query(TrafficStat).filter(TrafficStat.bucket_start >= s, TrafficStat.bucket_start < e)
    if intersection_id:
        q = q.filter(TrafficStat.intersection_id == intersection_id)
    if direction:
        q = q.filter(TrafficStat.direction == direction)
    return q.order_by(TrafficStat.bucket_start).all()


class _Agg:
    __slots__ = ("counts", "pcu", "d_sum", "q_sum", "w_sum", "w_n", "n", "d_max", "q_max")

    def __init__(self) -> None:
        self.counts = defaultdict(int)
        self.pcu = 0.0
        self.d_sum = self.q_sum = self.w_sum = 0.0
        self.w_n = self.n = 0
        self.d_max = self.q_max = 0.0

    def add(self, r: TrafficStat) -> None:
        for c in CLASSES:
            self.counts[c] += getattr(r, c)
        self.pcu += r.pcu
        self.d_sum += r.avg_density
        self.q_sum += r.avg_queue_m
        self.d_max = max(self.d_max, r.max_density)
        self.q_max = max(self.q_max, r.max_queue_m)
        if r.total:
            self.w_sum += r.avg_wait_s * r.total
            self.w_n += r.total
        self.n += 1

    def out(self) -> dict:
        total = sum(self.counts.values())
        return {
            **{c: self.counts[c] for c in CLASSES},
            "total": total,
            "pcu": round(self.pcu, 1),
            "avg_density": round(self.d_sum / self.n, 1) if self.n else 0,
            "max_density": round(self.d_max, 1),
            "avg_queue_m": round(self.q_sum / self.n, 1) if self.n else 0,
            "max_queue_m": round(self.q_max, 1),
            "avg_wait_s": round(self.w_sum / self.w_n, 1) if self.w_n else 0,
        }


def _bucket_key(ts: datetime, granularity: str) -> datetime:
    if granularity == "5min":
        return ts
    if granularity == "day":
        local = ts.astimezone()
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return ts.replace(minute=0, second=0, microsecond=0)


Filters = dict


def filters(intersection_id: int | None = None, direction: str | None = None,
            preset: str = Query("24h", pattern="^(today|24h|7d|custom)$"),
            start: datetime | None = None, end: datetime | None = None) -> Filters:
    s, e = _range(preset, start, end)
    return {"intersection_id": intersection_id, "direction": direction, "start": s, "end": e, "preset": preset}


@router.get("/overview")
def overview(f: Filters = Depends(filters), db: Session = Depends(get_db),
             _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    rows = _query(db, f["intersection_id"], f["direction"], f["start"], f["end"])
    agg = _Agg()
    hourly = defaultdict(int)
    for r in rows:
        agg.add(r)
        hourly[_bucket_key(r.bucket_start, "hour")] += r.total
    peak = max(hourly.items(), key=lambda kv: kv[1]) if hourly else None
    hours = max((f["end"] - f["start"]).total_seconds() / 3600, 1 / 12)
    out = agg.out()
    return {
        **out,
        "range": {"start": f["start"].isoformat(), "end": f["end"].isoformat()},
        "peak_hour": peak[0].isoformat() if peak else None,
        "peak_hour_total": peak[1] if peak else 0,
        "avg_flow_vph": round(out["total"] / hours),
        "samples": len(rows),
    }


@router.get("/timeseries")
def timeseries(granularity: str = Query("hour", pattern="^(5min|hour|day)$"), f: Filters = Depends(filters),
               db: Session = Depends(get_db), _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    rows = _query(db, f["intersection_id"], f["direction"], f["start"], f["end"])
    buckets: dict[datetime, _Agg] = defaultdict(_Agg)
    for r in rows:
        buckets[_bucket_key(r.bucket_start, granularity)].add(r)
    return [{"time": k.isoformat(), **v.out()} for k, v in sorted(buckets.items())]


@router.get("/by-direction")
def by_direction(f: Filters = Depends(filters), db: Session = Depends(get_db),
                 _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    rows = _query(db, f["intersection_id"], f["direction"], f["start"], f["end"])
    by: dict[str, _Agg] = defaultdict(_Agg)
    for r in rows:
        by[r.direction].add(r)
    return [{"direction": d, "label": DIR_VI[d], **by[d].out()} for d in DIR_VI if d in by]


@router.get("/composition")
def composition(f: Filters = Depends(filters), db: Session = Depends(get_db),
                _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    rows = _query(db, f["intersection_id"], f["direction"], f["start"], f["end"])
    agg = _Agg()
    for r in rows:
        agg.add(r)
    total = sum(agg.counts.values()) or 1
    labels = {"car": "Ô tô", "motorbike": "Xe máy", "bus": "Xe buýt", "truck": "Xe tải"}
    return [{"cls": c, "label": labels[c], "count": agg.counts[c], "pct": round(agg.counts[c] / total * 100, 1)}
            for c in CLASSES]


def _table_rows(db: Session, f: Filters) -> list[dict]:
    rows = _query(db, f["intersection_id"], f["direction"], f["start"], f["end"])
    names = {i.id: i.name for i in db.query(Intersection).all()}
    groups: dict[tuple, _Agg] = defaultdict(_Agg)
    for r in rows:
        groups[(_bucket_key(r.bucket_start, "hour"), r.intersection_id, r.direction)].add(r)
    out = []
    for (t, iid, d), agg in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]), reverse=True):
        out.append({"time": t.isoformat(), "intersection_id": iid, "intersection": names.get(iid, str(iid)),
                    "direction": d, "direction_label": DIR_VI.get(d, d), **agg.out()})
    return out


@router.get("/table")
def table(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), f: Filters = Depends(filters),
          db: Session = Depends(get_db), _: CurrentUser = Depends(require(Perm.STATS_VIEW))):
    rows = _table_rows(db, f)
    return {"items": rows[(page - 1) * page_size: page * page_size], "total": len(rows), "page": page,
            "page_size": page_size}


@router.get("/export")
def export(request: Request, format: str = Query("csv", pattern="^(csv|json)$"), f: Filters = Depends(filters),
           db: Session = Depends(get_db), cur: CurrentUser = Depends(require(Perm.STATS_EXPORT))):
    rows = _table_rows(db, f)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    audit(db, "SYSTEM", "EXPORT_STATS", f"Xuất báo cáo thống kê {format.upper()} ({len(rows)} dòng)",
          username=cur.username, role=cur.role, ip=client_ip(request),
          details={"preset": f["preset"], "intersection_id": f["intersection_id"], "direction": f["direction"]})
    if format == "json":
        agg = _Agg()
        for r in _query(db, f["intersection_id"], f["direction"], f["start"], f["end"]):
            agg.add(r)
        payload = {
            "report": "STCS — Báo cáo thống kê lưu lượng giao thông",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": cur.username,
            "filters": {"intersection_id": f["intersection_id"], "direction": f["direction"], "preset": f["preset"],
                        "start": f["start"].isoformat(), "end": f["end"].isoformat()},
            "summary": agg.out(),
            "rows": rows,
        }
        return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="stcs_thong_ke_{stamp}.json"'})
    buf = io.StringIO()
    buf.write("﻿")  # BOM để Excel hiển thị đúng tiếng Việt
    w = csv.writer(buf)
    w.writerow(["Thời gian (UTC)", "Nút giao", "Hướng", "Ô tô", "Xe máy", "Xe buýt", "Xe tải", "Tổng", "PCU",
                "Mật độ TB (%)", "Mật độ max (%)", "Hàng đợi TB (m)", "Hàng đợi max (m)", "Chờ TB (s)"])
    for r in rows:
        w.writerow([r["time"], r["intersection"], r["direction_label"], r["car"], r["motorbike"], r["bus"], r["truck"],
                    r["total"], r["pcu"], r["avg_density"], r["max_density"], r["avg_queue_m"], r["max_queue_m"],
                    r["avg_wait_s"]])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="stcs_thong_ke_{stamp}.csv"'})
