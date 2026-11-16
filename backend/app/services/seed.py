"""Seed dữ liệu mẫu: tài khoản, nút giao, camera và lịch sử 7 ngày (thống kê, chu kỳ đèn, cảnh báo, sự cố, nhật ký).

Lịch sử được chia làm hai giai đoạn để phục vụ đối sánh US14:
  * 7 → 3.5 ngày trước: chế độ FIXED_TIME ("Trước khi áp dụng")
  * 3.5 ngày gần nhất:  chế độ AUTO — AI Adaptive ("Sau khi áp dụng")
"""
from __future__ import annotations

import logging
import os
import random
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR, settings
from app.core.rbac import Role
from app.core.security import hash_password, verify_password
from app.models import (
    Alert,
    AuditLog,
    Camera,
    DeviceIncident,
    Intersection,
    SignalCommand,
    SignalCycle,
    TrafficStat,
    User,
)
from app.services.stats import align_bucket
from app.vision_engine.geometry import CameraCalibration
from app.vision_engine.simulator import MIX, TOD_PROFILE

log = logging.getLogger("stcs.seed")
DIRS = ("NORTH", "SOUTH", "EAST", "WEST")
DIR_VI = {"NORTH": "Bắc", "SOUTH": "Nam", "EAST": "Đông", "WEST": "Tây"}
ASYM = {"NORTH": 1.08, "SOUTH": 0.92, "EAST": 1.05, "WEST": 0.95}

USERS = [
    ("admin", "admin123", "Thái Viết Đại", Role.ADMIN, "admin@stcs.danang.gov.vn", True),
    ("operator", "operator123", "Đoàn Thanh Tuyển", Role.OPERATOR, "operator@stcs.danang.gov.vn", True),
    ("manager", "manager123", "Nguyễn Thị Hà Tiên", Role.MANAGER, "manager@stcs.danang.gov.vn", True),
    ("viewer", "viewer123", "Lê Minh Quan Sát", Role.VIEWER, "viewer@stcs.danang.gov.vn", True),
    ("operator2", "operator123", "Phạm Đức Ca Đêm", Role.OPERATOR, "operator2@stcs.danang.gov.vn", False),
]

INTERSECTIONS = [
    dict(
        code="DN-DBP-NTP", name="Nút giao Điện Biên Phủ – Nguyễn Tri Phương", district="Thanh Khê, Đà Nẵng",
        description="Nút giao 4 nhánh có lưu lượng cao vào giờ cao điểm sáng/chiều, trục Điện Biên Phủ là trục chính.",
        latitude=16.06654, longitude=108.20012, ns_road="Nguyễn Tri Phương", ew_road="Điện Biên Phủ",
        lanes_per_approach=2, fixed_green_ns=30, fixed_green_ew=30, base_demand_ns=1050, base_demand_ew=820,
        controller_endpoint="ntcip://10.20.1.11:161", controller_model="Siemens M60 (SimTSC)",
        density_medium=40, density_high=70, cycle_min_s=50,
    ),
    dict(
        code="DN-CR-BD", name="Nút giao Cầu Rồng – Bạch Đằng", district="Hải Châu, Đà Nẵng",
        description="Nút giao đầu cầu Rồng, lưu lượng du lịch lớn buổi tối và cuối tuần; trục Bạch Đằng ven sông Hàn.",
        latitude=16.06128, longitude=108.22462, ns_road="Bạch Đằng", ew_road="Nguyễn Văn Linh – Cầu Rồng",
        lanes_per_approach=3, fixed_green_ns=35, fixed_green_ew=35, base_demand_ns=980, base_demand_ew=1180,
        controller_endpoint="ntcip://10.20.2.21:161", controller_model="Swarco ITC-3 (SimTSC)",
        density_medium=38, density_high=68, cycle_min_s=50,
    ),
]

PCU = {"car": 1.0, "motorbike": 0.3, "bus": 2.5, "truck": 2.0}


def _tod(local: datetime) -> float:
    h = local.hour + local.minute / 60
    i = int(h) % 24
    f = h - int(h)
    return TOD_PROFILE[i] * (1 - f) + TOD_PROFILE[(i + 1) % 24] * f


def credentials_file() -> str:
    return os.environ.get("STCS_INITIAL_CREDENTIALS_FILE", str(BASE_DIR / "data" / "initial_credentials.txt"))


def _initial_password(demo_pw: str, username: str, generated: list[tuple[str, str]]) -> str:
    """Chế độ demo: mật khẩu mẫu công khai. Ngoài demo: mật khẩu ngẫu nhiên, ghi lại để báo cho quản trị viên."""
    if settings.demo_mode:
        return demo_pw
    pw = secrets.token_urlsafe(12)
    generated.append((username, pw))
    return pw


def _write_credentials(generated: list[tuple[str, str]]) -> None:
    """Ghi mật khẩu khởi tạo vào file quyền 600 (không in mật khẩu ra log)."""
    if not generated:
        return
    path = credentials_file()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(f"# Mật khẩu khởi tạo STCS — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. "
                 "Đăng nhập, đổi mật khẩu, rồi xoá file này.\n")
        for username, pw in generated:
            fh.write(f"{username}\t{pw}\n")
    log.warning("Đã tạo %d tài khoản với mật khẩu ngẫu nhiên — xem %s rồi xoá file sau khi đổi mật khẩu",
                len(generated), path)


def warn_demo_passwords(db: Session) -> list[str]:
    """Ngoài chế độ demo: cảnh báo tài khoản đang hoạt động vẫn dùng mật khẩu mẫu công khai."""
    if settings.demo_mode:
        return []
    weak = []
    for username, pw, *_ in USERS:
        u = db.query(User).filter(User.username == username).first()
        if u and u.is_active and verify_password(pw, u.password_hash):
            weak.append(username)
    if weak:
        log.warning("Tài khoản vẫn dùng mật khẩu mẫu công khai: %s — đổi ngay (STCS_DEMO_MODE=0)", ", ".join(weak))
    return weak


def ensure_default_users(db: Session) -> None:
    """Bổ sung tài khoản mẫu mới (vd. vai trò VIEWER) cho CSDL đã seed từ phiên bản trước."""
    generated: list[tuple[str, str]] = []
    for username, pw, full, role, email, active in USERS:
        if db.query(User).filter(User.username == username).first() is None:
            db.add(User(username=username, full_name=full, role=role.value, email=email,
                        password_hash=hash_password(_initial_password(pw, username, generated)), is_active=active))
    db.commit()
    _write_credentials(generated)


def seed_if_empty(db: Session) -> bool:
    if db.query(User).count() > 0:
        ensure_default_users(db)
        warn_demo_passwords(db)
        return False
    log.info("Khởi tạo dữ liệu mẫu…")
    rng = random.Random(2024)
    now = datetime.now(timezone.utc)

    users = []
    generated: list[tuple[str, str]] = []
    for username, pw, full, role, email, active in USERS:
        u = User(username=username, full_name=full, role=role.value, email=email,
                 password_hash=hash_password(_initial_password(pw, username, generated)),
                 is_active=active, phone=f"09{rng.randint(10000000, 99999999)}",
                 created_at=now - timedelta(days=30), last_login_at=now - timedelta(hours=rng.randint(2, 50)))
        db.add(u)
        users.append(u)

    inters = []
    for spec in INTERSECTIONS:
        it = Intersection(**spec, created_at=now - timedelta(days=30))
        db.add(it)
        db.flush()
        calib = CameraCalibration(lanes=it.lanes_per_approach)
        short = it.code.split("-", 1)[1]
        for d in DIRS:
            db.add(Camera(
                code=f"CAM-{short}-{d[0]}", name=f"Camera hướng {DIR_VI[d]} — {it.ns_road if d in ('NORTH', 'SOUTH') else it.ew_road}",
                intersection_id=it.id, direction=d, source_type="SIMULATED",
                stream_url=f"rtsp://sim.stcs.local/{it.code.lower()}/{d.lower()}", resolution="1280x720",
                target_fps=15, roi=calib.roi_polygon(60.0), counting_line=calib.counting_line(), roi_length_m=60.0,
            ))
        inters.append(it)
    db.flush()

    _seed_history(db, inters, rng, now)
    _seed_events(db, inters, rng, now)
    db.commit()
    _write_credentials(generated)
    log.info("Đã seed dữ liệu mẫu")
    return True


def _seed_history(db: Session, inters: list[Intersection], rng: random.Random, now: datetime) -> None:
    start = align_bucket(now - timedelta(days=7), 5)
    end = align_bucket(now, 5)
    split = now - timedelta(days=3.5)
    stats, cycles = [], []
    for it in inters:
        lanes = it.lanes_per_approach
        cap = 950.0 * lanes  # xe/giờ/hướng có thể thông qua ở chu kỳ cố định
        t = start
        while t < end:
            local = t.astimezone()
            mode = "FIXED_TIME" if t < split else "AUTO"
            tod = _tod(local)
            for d in DIRS:
                base = it.base_demand_ns if d in ("NORTH", "SOUTH") else it.base_demand_ew
                demand = base * ASYM[d] * tod * rng.uniform(0.88, 1.12)
                capacity = cap * (1.14 if mode == "AUTO" else 1.0)
                x = demand / capacity
                # Chu kỳ cố định không khớp nhu cầu → một phần xe phải chờ sang chu kỳ sau / đi đường khác
                spill = (0.03 * x) if mode == "AUTO" else (0.13 * min(x, 1.2) ** 1.5)
                served = min(demand * (1 - spill), capacity * rng.uniform(0.96, 1.02))
                n = max(0, int(round(served * 5 / 60)))
                counts = {"car": 0, "motorbike": 0, "bus": 0, "truck": 0}
                for _ in range(n):
                    counts[rng.choices(list(MIX), weights=list(MIX.values()))[0]] += 1
                density = 8 + 72 * x ** 1.7
                wait = 9 + 38 * x ** 2.1
                queue = 4 + 62 * x ** 2
                if mode == "AUTO":
                    gain = 0.72 if x > 0.75 else 0.86
                    density *= 0.86 if x > 0.75 else 0.93
                    wait *= gain
                    queue *= gain
                density = min(98.0, density * rng.uniform(0.9, 1.1))
                stats.append(dict(
                    intersection_id=it.id, direction=d, bucket_start=t, bucket_minutes=5,
                    car=counts["car"], motorbike=counts["motorbike"], bus=counts["bus"], truck=counts["truck"],
                    total=n, pcu=round(sum(counts[k] * PCU[k] for k in counts), 2),
                    avg_density=round(density, 2), max_density=round(min(100, density * rng.uniform(1.1, 1.35)), 2),
                    avg_queue_m=round(queue * rng.uniform(0.9, 1.1), 2),
                    max_queue_m=round(min(120, queue * rng.uniform(1.3, 1.8)), 2),
                    avg_wait_s=round(wait * rng.uniform(0.9, 1.1), 2), mode=mode,
                ))
            t += timedelta(minutes=5)

        # Lịch sử chu kỳ đèn (7 ngày)
        lost = 2 * (it.yellow_s + it.all_red_s)
        t = start
        while t < now - timedelta(minutes=2):
            local = t.astimezone()
            mode = "FIXED_TIME" if t < split else "AUTO"
            tod = _tod(local)
            dns = it.base_demand_ns * 1.08 * tod * rng.uniform(0.85, 1.15) * 0.69
            dew = it.base_demand_ew * 1.05 * tod * rng.uniform(0.85, 1.15) * 0.69
            if mode == "FIXED_TIME":
                g_ns, g_ew = float(it.fixed_green_ns), float(it.fixed_green_ew)
                reason = "Kế hoạch chu kỳ cố định chuẩn của nút giao"
            else:
                sat = it.saturation_flow * lanes
                y_ns, y_ew = min(dns / sat, 0.45), min(dew / sat, 0.45)
                Y = max(y_ns + y_ew, 0.05)
                C = min(max((1.5 * lost + 5) / (1 - min(Y, 0.9)), it.cycle_min_s), it.cycle_max_s)
                g_ns = round(min(max((C - lost) * y_ns / Y, it.min_green_s), it.max_green_s))
                g_ew = round(min(max((C - lost) * y_ew / Y, it.min_green_s), it.max_green_s))
                hi = "Bắc–Nam" if dns >= dew else "Đông–Tây"
                reason = (f"Nhu cầu Bắc–Nam {dns:,.0f} PCU/h · Đông–Tây {dew:,.0f} PCU/h → ưu tiên {hi}. "
                          f"Chu kỳ Webster {C:.0f}s (Y={Y:.2f}).")
            cycle_len = g_ns + g_ew + lost
            x = max(dns, dew) / (950 * lanes * 0.69)
            wait = (9 + 38 * x ** 2.1) * (0.8 if mode == "AUTO" else 1.0)
            cycles.append(dict(
                intersection_id=it.id, started_at=t, ended_at=t + timedelta(seconds=cycle_len), mode=mode,
                cycle_length_s=cycle_len, green_ns_s=g_ns, green_ew_s=g_ew, yellow_s=it.yellow_s,
                all_red_s=it.all_red_s, demand_ns_pcu=round(dns), demand_ew_pcu=round(dew),
                queue_ns_m=round((4 + 62 * (dns / (950 * lanes * 0.69)) ** 2) * (0.75 if mode == "AUTO" else 1), 1),
                queue_ew_m=round((4 + 62 * (dew / (950 * lanes * 0.69)) ** 2) * (0.75 if mode == "AUTO" else 1), 1),
                avg_wait_s=round(wait * rng.uniform(0.9, 1.1), 1),
                throughput=int((dns + dew) / 0.69 * 2 * cycle_len / 3600 * rng.uniform(0.9, 1.05)),
                plan_reason=reason,
            ))
            t += timedelta(seconds=cycle_len)
    db.execute(insert(TrafficStat), stats)
    db.execute(insert(SignalCycle), cycles)


def _seed_events(db: Session, inters: list[Intersection], rng: random.Random, now: datetime) -> None:
    alerts, incidents, commands, audits = [], [], [], []
    ops = ["operator", "admin"]

    for it in inters:
        # Cảnh báo ùn tắc vào giờ cao điểm
        for day in range(7):
            for hour in (7, 8, 17, 18):
                if rng.random() < 0.55:
                    local = (now - timedelta(days=day)).astimezone().replace(hour=hour, minute=rng.randint(0, 50), second=0, microsecond=0)
                    created = local.astimezone(timezone.utc)
                    if created > now - timedelta(minutes=30):
                        continue
                    d = rng.choice(DIRS)
                    high = rng.random() < 0.45
                    dens = rng.uniform(it.density_high, 92) if high else rng.uniform(it.density_medium, it.density_high - 1)
                    q = rng.uniform(45, 95) if high else rng.uniform(25, 50)
                    acked = rng.random() < 0.85
                    level_vi = "ÙN TẮC" if high else "ĐÔNG ĐÚC"
                    alerts.append(dict(
                        intersection_id=it.id, direction=d, alert_type="CONGESTION",
                        level="CRITICAL" if high else "WARNING",
                        title=f"{level_vi} hướng {DIR_VI[d]} — {it.name}",
                        message=f"Mật độ hướng {DIR_VI[d]} đạt {dens:.0f}% (ngưỡng {it.density_high if high else it.density_medium:.0f}%), hàng đợi ước tính {q:.0f} m.",
                        density=round(dens, 1), queue_m=round(q, 1), peak_density=round(min(99, dens * 1.08), 1),
                        status="RESOLVED", created_at=created,
                        resolved_at=created + timedelta(minutes=rng.randint(6, 40)),
                        acknowledged_by=rng.choice(ops) if acked else None,
                        acknowledged_at=created + timedelta(minutes=rng.randint(1, 5)) if acked else None,
                        ack_note=rng.choice([
                            "Đã theo dõi, AI tăng thời gian xanh hướng ùn tắc",
                            "Phối hợp CSGT phân luồng tại chỗ",
                            "Ùn tắc do giờ tan tầm, đã tự giải toả",
                            "Đã kiểm tra camera, số liệu chính xác",
                        ]) if acked else "Tự giải toả",
                    ))

        # Sự cố thiết bị & lịch sử bảo trì
        short = it.code.split("-", 1)[1]
        templates = [
            ("CAMERA", "CONNECTION_LOST", "CRITICAL", "Camera hướng {d} mất kết nối: RTSP session timeout",
             "Khởi động lại bộ mã hoá camera, thay dây mạng PoE"),
            ("CAMERA", "DEGRADED", "WARNING", "Camera hướng {d} suy giảm chất lượng (FPS 4.2, mất gói tin)",
             "Vệ sinh ống kính, điều chỉnh bitrate về 2 Mbps"),
            ("CONTROLLER", "TIMEOUT", "CRITICAL", "Bộ điều khiển đèn không phản hồi ACK trong 3000 ms",
             "Reset module truyền thông NTCIP, kiểm tra nguồn UPS"),
            ("VISION", "ALGORITHM_ERROR", "CRITICAL", "Mô hình nhận diện trả về kết quả không hợp lệ",
             "Khởi động lại dịch vụ suy luận, cập nhật trọng số mô hình"),
        ]
        for k in range(6):
            dev, typ, sev, msg, fix = rng.choice(templates)
            d = rng.choice(DIRS)
            started = now - timedelta(days=rng.uniform(0.3, 6.8))
            rec = started + timedelta(minutes=rng.randint(2, 45))
            open_one = k == 0 and it.id == inters[0].id
            cam_code = f"CAM-{short}-{d[0]}"
            incidents.append(dict(
                intersection_id=it.id, device_type=dev, device_id=None,
                device_code=cam_code if dev == "CAMERA" else (f"TSC-{it.code}" if dev == "CONTROLLER" else f"AI-{it.code}"),
                incident_type=typ, severity=sev, message=msg.format(d=DIR_VI[d]),
                status="ACKNOWLEDGED" if open_one else "RESOLVED", started_at=started, recovered_at=rec,
                acknowledged_by="operator", acknowledged_at=started + timedelta(minutes=2),
                resolved_by=None if open_one else "admin",
                resolved_at=None if open_one else rec + timedelta(hours=rng.uniform(0.5, 6)),
                resolution_note=None if open_one else fix,
            ))
            if dev in ("CAMERA", "CONTROLLER", "VISION") and sev == "CRITICAL" and rng.random() < 0.6:
                alerts.append(dict(
                    intersection_id=it.id, direction=None, alert_type="FAILSAFE", level="CRITICAL",
                    title=f"FAILSAFE (CHU KỲ CỐ ĐỊNH) — {it.name}",
                    message=f"{msg.format(d=DIR_VI[d])}. Điều khiển tự động đã bị khoá; cần khắc phục sự cố và khôi phục thủ công.",
                    density=None, queue_m=None, peak_density=None, status="RESOLVED", created_at=started,
                    resolved_at=rec + timedelta(minutes=3), acknowledged_by="operator",
                    acknowledged_at=started + timedelta(minutes=1), ack_note="Khôi phục bởi operator",
                ))

        # Lệnh điều khiển thủ công trong quá khứ
        manual = [
            ("SET_MODE", {"mode": "MANUAL"}, "Điều tiết thủ công phục vụ đoàn xe ưu tiên", "EXECUTED"),
            ("HOLD_PHASE", {"phase_id": 1, "duration_s": 60}, "Xe cứu thương hướng Bắc", "ACCEPTED"),
            ("RELEASE_HOLD", {}, "Đoàn xe đã qua", "EXECUTED"),
            ("NEXT_PHASE", {}, "Giải toả hàng đợi hướng Đông", "EXECUTED"),
            ("GOTO_PHASE", {"phase_id": 2}, "Ùn tắc kéo dài trục Đông–Tây", "SCHEDULED"),
            ("EXTEND_GREEN", {"seconds": 10}, "Hàng đợi dài hướng Nam", "EXECUTED"),
            ("SET_MODE", {"mode": "AUTO"}, "Trở lại điều khiển tự động", "EXECUTED"),
            ("FLASHING_YELLOW", {"on": True}, "Bảo trì tủ điều khiển ban đêm", "ACCEPTED"),
            ("FLASHING_YELLOW", {"on": False}, "Hoàn tất bảo trì", "ACCEPTED"),
            ("GOTO_PHASE", {"phase_id": 1}, "Thử nghiệm lệnh trước min green", "SCHEDULED"),
        ]
        for j in range(16):
            cmd, params, reason, status = manual[j % len(manual)]
            ts = now - timedelta(days=rng.uniform(0.1, 6.9))
            by = rng.choice(ops)
            commands.append(dict(
                intersection_id=it.id, created_at=ts, command=cmd, params=params, source="MANUAL", issued_by=by,
                mode="MANUAL" if j % 3 else "AUTO", from_state="P1:GREEN", to_state="P1:YELLOW_CLEARANCE" if status == "EXECUTED" else "P1:GREEN",
                reason=reason, status=status, ack=True, ack_latency_ms=round(rng.uniform(8, 35), 1),
                message=f"{cmd} — {reason}",
            ))
            audits.append(dict(
                created_at=ts, category="SIGNAL_CONTROL", action=cmd, username=by, role="OPERATOR" if by == "operator" else "ADMIN",
                target=it.code, description=f"{it.name}: {cmd} ({reason})", details=params, ip="10.10.0.%d" % rng.randint(10, 60),
                result="SUCCESS", intersection_id=it.id,
            ))
        # Một lệnh bị từ chối bởi khoá an toàn
        ts = now - timedelta(days=1.2)
        commands.append(dict(
            intersection_id=it.id, created_at=ts, command="SET_MODE", params={"mode": "AUTO"}, source="MANUAL",
            issued_by="operator", mode="FAILSAFE", from_state="P1:GREEN", to_state="P1:GREEN",
            reason="Thử bật lại AUTO", status="REJECTED", ack=False, ack_latency_ms=None,
            message="Hệ thống đang FAILSAFE — dùng chức năng Khôi phục sau khi khắc phục sự cố",
        ))
        # Chuyển pha tự động 2 giờ gần nhất
        t = now - timedelta(hours=2)
        phase = 1
        while t < now - timedelta(minutes=1):
            g = rng.randint(18, 42)
            commands.append(dict(
                intersection_id=it.id, created_at=t, command="PHASE_CHANGE", params={"green_s": g}, source="AUTO",
                issued_by="AI_ADAPTIVE", mode="AUTO", from_state=f"P{3 - phase}:ALL_RED_CLEARANCE",
                to_state=f"P{phase}:GREEN", reason="Hết pha toàn đỏ. Kế hoạch Webster thích ứng theo hàng đợi",
                status="EXECUTED", ack=True, ack_latency_ms=round(rng.uniform(6, 30), 1),
                message=f"Bật xanh Pha {phase} trong {g}s",
            ))
            t += timedelta(seconds=g + 5)
            phase = 3 - phase

    # Nhật ký hệ thống
    for day in range(7):
        for u, role in (("operator", "OPERATOR"), ("admin", "ADMIN"), ("manager", "MANAGER")):
            if rng.random() < 0.9:
                ts = now - timedelta(days=day, hours=rng.uniform(0, 10))
                audits.append(dict(created_at=ts, category="AUTH", action="LOGIN", username=u, role=role, target=u,
                                   description=f"Đăng nhập thành công ({u})", details={}, ip="10.10.0.%d" % rng.randint(10, 60),
                                   result="SUCCESS", intersection_id=None))
        if rng.random() < 0.6:
            ts = now - timedelta(days=day, hours=rng.uniform(0, 20))
            audits.append(dict(created_at=ts, category="AUTH", action="LOGIN_FAILED", username="operator", role=None,
                               target="operator", description="Sai mật khẩu (lần 1/5)", details={},
                               ip="10.10.0.%d" % rng.randint(10, 60), result="FAILURE", intersection_id=None))
    config_events = [
        ("UPDATE_INTERSECTION", "Cập nhật ngưỡng cảnh báo: Đông đúc 40%, Ùn tắc 70%", inters[0]),
        ("UPDATE_INTERSECTION", "Cập nhật ràng buộc an toàn: Min Green 10s, Max Green 60s", inters[1]),
        ("UPDATE_CAMERA", "Hiệu chỉnh vùng ROI camera hướng Bắc (60 m)", inters[0]),
        ("CREATE_CAMERA", "Thêm camera hướng Tây", inters[1]),
        ("PING_CAMERA", "Kiểm tra kết nối camera hướng Nam — OK 42 ms", inters[0]),
    ]
    for action, desc, it in config_events:
        ts = now - timedelta(days=rng.uniform(0.5, 6.5))
        audits.append(dict(created_at=ts, category="CONFIG", action=action, username="admin", role="ADMIN", target=it.code,
                           description=f"{it.name}: {desc}", details={}, ip="10.10.0.5", result="SUCCESS",
                           intersection_id=it.id))
    audits.append(dict(created_at=now - timedelta(days=5), category="USER", action="LOCK_USER", username="admin",
                       role="ADMIN", target="operator2", description="Khoá tài khoản operator2 (nghỉ phép dài hạn)",
                       details={}, ip="10.10.0.5", result="SUCCESS", intersection_id=None))
    for a in alerts:
        if a["acknowledged_by"]:
            audits.append(dict(created_at=a["acknowledged_at"], category="ALERT", action="ACK_ALERT",
                               username=a["acknowledged_by"], role="OPERATOR", target=a["title"][:150],
                               description=f"Xác nhận cảnh báo: {a['title']}", details={"note": a["ack_note"]},
                               ip="10.10.0.21", result="SUCCESS", intersection_id=a["intersection_id"]))
    for inc in incidents:
        audits.append(dict(created_at=inc["started_at"], category="DEVICE", action=f"{inc['device_type']}_{inc['incident_type']}",
                           username="system", role=None, target=inc["device_code"], description=f"[{inc['device_code']}] {inc['message']}",
                           details={"severity": inc["severity"]}, ip=None, result="FAILURE",
                           intersection_id=inc["intersection_id"]))

    db.execute(insert(Alert), alerts)
    db.execute(insert(DeviceIncident), incidents)
    db.execute(insert(SignalCommand), commands)
    db.execute(insert(AuditLog), audits)
