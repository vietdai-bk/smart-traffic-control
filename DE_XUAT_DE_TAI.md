# BÁO CÁO ĐỀ XUẤT ĐỀ TÀI

# PHẦN MỀM ĐIỀU KHIỂN GIAO THÔNG TÍCH HỢP CAMERA KẾT HỢP MÔ HÌNH NGÔN NGỮ LỚN (LLM)

> Ngày lập: 02/11/2026
> Tài liệu tham chiếu: *Tài liệu đặc tả yêu cầu – Phần mềm điều khiển giao thông tích hợp camera* (`yeu_cau_phan_mem_dieu_khien_giao_thong_tich_hop_camera.docx`)

---

## MỤC LỤC

1. [Tổng quan đề tài](#1-tổng-quan-đề-tài)
2. [Mục tiêu và phạm vi](#2-mục-tiêu-và-phạm-vi)
3. [Tóm tắt yêu cầu từ đặc tả](#3-tóm-tắt-yêu-cầu-từ-đặc-tả)
4. [Kiến trúc tổng thể](#4-kiến-trúc-tổng-thể)
5. [Kiến trúc điều khiển 3 tầng có LLM](#5-kiến-trúc-điều-khiển-3-tầng-có-llm)
6. [Các tính năng ứng dụng LLM](#6-các-tính-năng-ứng-dụng-llm)
7. [Các tính năng mở rộng khác](#7-các-tính-năng-mở-rộng-khác)
8. [Thiết kế dữ liệu](#8-thiết-kế-dữ-liệu)
9. [Thiết kế API](#9-thiết-kế-api)
10. [Công nghệ sử dụng](#10-công-nghệ-sử-dụng)
11. [An toàn, bảo mật và quyền riêng tư](#11-an-toàn-bảo-mật-và-quyền-riêng-tư)
12. [Kế hoạch kiểm thử và đánh giá](#12-kế-hoạch-kiểm-thử-và-đánh-giá)
13. [Kế hoạch triển khai (Sprint)](#13-kế-hoạch-triển-khai-sprint)
14. [Rủi ro và phương án xử lý](#14-rủi-ro-và-phương-án-xử-lý)
15. [Ma trận truy vết yêu cầu](#15-ma-trận-truy-vết-yêu-cầu)
16. [Kết luận và hướng phát triển](#16-kết-luận-và-hướng-phát-triển)

---

## 1. Tổng quan đề tài

Ùn tắc giao thông tại các nút giao đô thị phần lớn đến từ việc đèn tín hiệu chạy **chu kỳ cố định**, không thích ứng với lưu lượng thực tế. Đề tài xây dựng một hệ thống:

- **Quan sát** nút giao bằng camera, dùng thị giác máy tính (YOLO + tracking) để nhận diện, phân loại, đếm phương tiện và đo mật độ theo từng hướng.
- **Điều khiển** đèn tín hiệu thích ứng bằng thuật toán tối ưu thời gian xanh.
- **Giám sát thông minh** bằng mô hình ngôn ngữ lớn (LLM): chọn chiến lược điều khiển theo ngữ cảnh, giải thích quyết định, trợ lý vận hành bằng tiếng Việt, tự động lập báo cáo.

**Điểm mới của đề tài:** LLM không thay thế bộ điều khiển thời gian thực. LLM đóng vai trò **giám sát viên (supervisor)** ở tầng chiến lược, và mọi lệnh đều phải qua một **lớp an toàn cứng (Safety Guard)**. Cách làm này vừa tận dụng khả năng suy luận ngữ cảnh của LLM, vừa đáp ứng yêu cầu an toàn giao thông (NFR06, NFR07).

## 2. Mục tiêu và phạm vi

### 2.1. Mục tiêu

| # | Mục tiêu | Chỉ tiêu đo lường |
|---|---|---|
| M1 | Nhận diện và đếm phương tiện từ camera | mAP@0.5 ≥ 0,80; sai số đếm ≤ 10% |
| M2 | Điều khiển đèn thích ứng | Giảm thời gian chờ trung bình ≥ 15% so với chu kỳ cố định (trên mô phỏng SUMO) |
| M3 | Tích hợp LLM giám sát | ≥ 95% phản hồi LLM đúng schema; 100% lệnh vi phạm ràng buộc bị chặn |
| M4 | Giám sát thời gian thực | Độ trễ cập nhật dashboard ≤ 1 giây; video ≤ 2 giây |
| M5 | Báo cáo và truy vết | Lưu đầy đủ lịch sử điều khiển, cảnh báo và cấu hình |

### 2.2. Phạm vi

- **Trong phạm vi:**
  - 1–4 nút giao, mỗi nút 4 hướng.
  - Nguồn video: file mẫu, RTSP hoặc webcam.
  - Bộ điều khiển đèn giả lập (phần mềm), có kết nối với mô phỏng SUMO.
  - Giao diện web.
- **Ngoài phạm vi:**
  - Kết nối tủ điều khiển đèn thương mại thật. Hệ thống chỉ thiết kế sẵn adapter để tích hợp sau.
  - Nhận dạng biển số phục vụ xử phạt.

## 3. Tóm tắt yêu cầu từ đặc tả

### 3.1. Epic

| Mã | Epic | User Story |
|---|---|---|
| E01 | Quản lý người dùng | US01 Đăng nhập, US02 Quản lý tài khoản |
| E02 | Giám sát camera | US03 Xem trực tiếp, US04 Theo dõi nhiều hướng |
| E03 | Nhận diện & phân tích | US05 Nhận diện, US06 Đếm theo hướng, US07 Mật độ |
| E04 | Điều khiển đèn | US08 Thủ công, US09 Tự động, US10 Chuyển chế độ |
| E05 | Giám sát & cảnh báo | US11 Ùn tắc, US12 Sự cố thiết bị |
| E06 | Thống kê & báo cáo | US13 Thống kê, US14 Đánh giá hiệu quả |
| E07 | Quản lý hệ thống | US15 Camera & nút giao, US16 Lịch sử hoạt động |

### 3.2. Yêu cầu chức năng (FR01–FR18)

Đăng nhập; phân quyền 3 vai trò (Quản trị viên, Người vận hành, Người xem); hiển thị camera; quản lý camera; nhận diện, phân loại (ô tô, xe máy, xe buýt, xe tải) và đếm phương tiện; phân tích mật độ; điều khiển đèn thủ công và tự động; chuyển chế độ; quản lý chu kỳ đèn; cảnh báo ùn tắc và thiết bị; thống kê; báo cáo; nhật ký; quản lý cấu hình.

### 3.3. Yêu cầu phi chức năng then chốt

- **NFR06 – An toàn giao thông:** tuân thủ thời gian chuyển pha và thời gian chuyển tiếp (vàng, all-red).
- **NFR07 – An toàn khi lỗi:** khi lỗi phải về trạng thái an toàn và không phát lệnh không hợp lệ.
- **NFR08 – Bảo mật:** xác thực, phân quyền, bảo vệ thông tin đăng nhập.
- **NFR14 – Khả năng kiểm thử:** có mô phỏng trước khi triển khai.
- **NFR15 – Quyền riêng tư:** hạn chế truy cập video, quy định thời gian lưu trữ.

## 4. Kiến trúc tổng thể

```
┌──────────────┐   RTSP/File   ┌──────────────────────────┐
│  Camera(s)   │──────────────▶│  Vision Service          │
└──────────────┘               │  YOLO + ByteTrack        │
                               │  Đếm theo vùng/làn       │
                               │  Mật độ, hàng chờ        │
                               └────────────┬─────────────┘
                                            │ metrics (1 Hz)
                                            ▼
┌───────────────┐  WebSocket   ┌──────────────────────────┐      ┌──────────────┐
│  Web Frontend │◀────────────▶│  Backend API (FastAPI)   │◀────▶│ PostgreSQL   │
│  React        │   REST       │  Auth/RBAC, CRUD,        │      │ + Redis      │
│  Dashboard    │              │  Alerts, Reports, Logs   │      └──────────────┘
└───────────────┘              └────────────┬─────────────┘
                                            │
                     ┌──────────────────────┼───────────────────────┐
                     ▼                      ▼                       ▼
            ┌────────────────┐   ┌────────────────────┐   ┌──────────────────┐
            │ LLM Supervisor │──▶│ Signal Controller  │──▶│  Safety Guard    │
            │ (Claude API)   │   │ Webster/MaxPressure│   │  (rule cứng)     │
            └────────────────┘   └────────────────────┘   └────────┬─────────┘
                                                                   ▼
                                                     ┌───────────────────────────┐
                                                     │ Controller Adapter        │
                                                     │ Giả lập │ SUMO/TraCI │ HW │
                                                     └───────────────────────────┘
```

**Nguyên tắc thiết kế:**

- **Module hóa (NFR11):** Vision, Controller, LLM và Adapter giao tiếp qua interface. Mỗi thành phần có thể thay thuật toán mà không ảnh hưởng phần còn lại.
- **Mở rộng (NFR10):** nút giao, camera và hướng đều được cấu hình trong DB, không hard-code.
- **Adapter pattern (NFR13):** cùng một interface `SignalControllerAdapter` cho cả bộ giả lập, SUMO và phần cứng thật.

## 5. Kiến trúc điều khiển 3 tầng có LLM

### 5.1. Lý do LLM không điều khiển trực tiếp

| Đặc điểm của LLM | Hệ quả nếu cho LLM điều khiển trực tiếp |
|---|---|
| Độ trễ 1–5 giây, có lúc timeout | Không đáp ứng vòng điều khiển theo giây |
| Đầu ra không tất định, có thể "ảo giác" | Có thể sinh lệnh mâu thuẫn hoặc nguy hiểm |
| Phụ thuộc mạng và dịch vụ bên ngoài | Vi phạm NFR07 khi mất kết nối |

→ Giải pháp là **phân tầng theo tần suất và mức độ tin cậy**.

### 5.2. Mô tả các tầng

```
Tầng 3 — LLM Supervisor     | chu kỳ 30–60 giây hoặc khi có sự kiện | chiến lược và tham số
Tầng 2 — Signal Controller  | mỗi chu kỳ đèn                        | tính thời gian xanh cụ thể
Tầng 1 — Safety Guard       | mọi lệnh                              | kiểm tra, phủ quyết, fail-safe
```

**Tầng 3 – LLM Supervisor**

- **Đầu vào (context):**
  - Số xe, mật độ và độ dài hàng chờ theo hướng.
  - Xu hướng 15 phút gần nhất.
  - Thời điểm (giờ cao điểm hay không).
  - Các cảnh báo đang mở.
  - Chiến lược hiện tại và hiệu quả của chu kỳ trước.
- **Đầu ra:** JSON theo schema cố định, được ép bằng tool use / structured output:

```json
{
  "strategy": "PRIORITIZE_DIRECTION",
  "cycle_length_s": 110,
  "direction_weights": { "N": 1.0, "S": 1.0, "E": 1.6, "W": 1.2 },
  "duration_min": 10,
  "reason": "Hàng chờ hướng Đông dài gấp 2,3 lần trung bình và đang tăng trong 10 phút gần nhất."
}
```

- **Các chiến lược cho phép (enum):** `BALANCED`, `PRIORITIZE_DIRECTION`, `PEAK_HOUR`, `OFF_PEAK`, `INCIDENT_MODE`, `EMERGENCY_PREEMPT`.
- **Chế độ vận hành:**
  - *Advisory:* LLM chỉ đề xuất, người vận hành duyệt.
  - *Autonomous:* tự áp dụng sau khi qua Safety Guard.

**Tầng 2 – Signal Controller.** Thời gian xanh của từng pha được tính theo công thức Webster có trọng số:

```
C₀ = (1,5·L + 5) / (1 − Y)          (chu kỳ tối ưu; L = tổng thời gian mất, Y = Σ yᵢ)
gᵢ = (C − L) · (wᵢ · yᵢ) / Σ(wⱼ · yⱼ)   (wᵢ = trọng số từ LLM, yᵢ = tỉ số lưu lượng/bão hòa)
```

Phương án thay thế là thuật toán **Max-Pressure**. Bộ điều khiển có thể đổi qua cấu hình, phục vụ so sánh trong thực nghiệm.

**Tầng 1 – Safety Guard** (code tất định, có unit test 100%):

| Ràng buộc | Giá trị mặc định (cấu hình được, cần phê duyệt) |
|---|---|
| Xanh tối thiểu / tối đa | 10 s / 90 s |
| Vàng | ≥ 3 s |
| All-red | ≥ 2 s |
| Chu kỳ | 40–180 s |
| Ma trận xung đột | Không cho 2 pha xung đột cùng xanh |
| Tốc độ thay đổi | Chu kỳ mới không lệch quá ±20% so với chu kỳ trước |
| Tần suất đổi chiến lược | Không quá 1 lần mỗi 60 s |

**Cơ chế fail-safe (NFR07):**

| Sự cố | Hành vi |
|---|---|
| LLM timeout / sai schema | Bỏ qua đề xuất, giữ chiến lược hiện tại, ghi log |
| Mất camera một hướng | Hướng đó dùng giá trị lịch sử cùng khung giờ |
| Mất ≥ 50% camera | Chuyển về **chu kỳ cố định** đã phê duyệt |
| Mất bộ điều khiển / lỗi nghiêm trọng | **Nháy vàng** và báo động mức Critical |
| Người vận hành chuyển sang thủ công | Tầng 2 và 3 tạm dừng; chỉ hoàn tất pha hiện tại qua vàng → all-red |

### 5.3. Sơ đồ trình tự một vòng điều khiển

```
Vision ──metrics──▶ Backend ──context──▶ LLM ──JSON──▶ Validator(schema)
                                                        │ hợp lệ
                                                        ▼
                     Signal Controller ◀── tham số ─────┘
                            │ timing plan
                            ▼
                     Safety Guard ──(vi phạm)──▶ clamp / reject + log + alert
                            │ OK
                            ▼
                     Adapter ──▶ Đèn ──ACK──▶ Backend ──WS──▶ Dashboard
```

## 6. Các tính năng ứng dụng LLM

| # | Tính năng | Mô tả | Liên kết yêu cầu |
|---|---|---|---|
| L1 | **Auto-tuning chiến lược** | LLM chọn chiến lược và trọng số theo ngữ cảnh (mục 5) | FR10, US09 |
| L2 | **Giải thích quyết định (XAI)** | Mỗi thay đổi đèn kèm một câu lý do tiếng Việt, hiện trên dashboard và lưu log | NFR12, US16 |
| L3 | **Trợ lý vận hành (chat)** | Hỏi đáp dữ liệu và ra lệnh bằng ngôn ngữ tự nhiên qua tool use | FR09, FR16 |
| L4 | **Báo cáo tự động** | Sinh báo cáo ngày/tuần từ số liệu thống kê, xuất PDF | FR16, US13, US14 |
| L5 | **Phân tích sự cố** | Khi có cảnh báo, tóm tắt nguyên nhân có thể và gợi ý xử lý | FR13, FR14 |
| L6 | **VLM đọc ảnh (tùy chọn)** | Gửi snapshot cho model có vision để phát hiện tai nạn, xe chết máy, ngập nước | FR08 |

### 6.1. Trợ lý vận hành – thiết kế tool

| Tool | Quyền tối thiểu | Cần xác nhận? |
|---|---|---|
| `get_intersection_status(id)` | Người xem | Không |
| `query_traffic_stats(id, from, to, group_by)` | Người xem | Không |
| `list_alerts(status, from, to)` | Người xem | Không |
| `set_priority(id, direction, minutes)` | Người vận hành | **Có** |
| `switch_mode(id, mode)` | Người vận hành | **Có** |
| `generate_report(id, from, to)` | Người quản lý | Không |

Ví dụ hội thoại:

> **Người dùng:** Ưu tiên hướng Bắc ở nút giao Láng Hạ trong 10 phút.
> **Trợ lý:** Đề xuất: tăng trọng số hướng Bắc lên 1,5 trong 10 phút. Hiện hướng Bắc có 42 xe chờ, cao hơn 60% so với các hướng khác. **[Xác nhận] [Hủy]**

**Nguyên tắc:**

- Lệnh làm thay đổi trạng thái luôn cần người bấm xác nhận.
- Quyền của tool được kiểm tra theo **người dùng đang đăng nhập**, không theo LLM.
- Mọi lệnh đều đi qua Safety Guard.

### 6.2. Prompt hệ thống (rút gọn)

```
Bạn là giám sát viên điều khiển giao thông tại nút giao {name}.
Nhiệm vụ: chọn chiến lược và tham số cho chu kỳ đèn tiếp theo.
Chỉ trả lời bằng tool `propose_strategy`. Không đặt thời gian pha cụ thể.
Ràng buộc: chu kỳ {min}–{max}s; trọng số 0.5–2.0; giải thích ngắn gọn bằng tiếng Việt,
dựa trên số liệu được cung cấp, không suy đoán số liệu không có.
```

### 6.3. Lựa chọn model và chi phí

- **Tác vụ thường xuyên (L1, L2, L5):** `claude-haiku-5-5`, nhanh và rẻ.
- **Tác vụ phức tạp (L3, L4, L6):** `claude-sonnet-5-5`, cho chat, báo cáo và phân tích ảnh.
- **Tiết kiệm chi phí:** dùng prompt caching cho system prompt và cấu hình nút giao. Chỉ gọi L1 khi chỉ số thay đổi vượt ngưỡng (event-driven).
- **Chạy offline:** dùng interface `LLMProvider` để có thể thay bằng model chạy cục bộ (Ollama).

## 7. Các tính năng mở rộng khác

| # | Tính năng | Mô tả | Giá trị |
|---|---|---|---|
| X1 | **Ưu tiên xe khẩn cấp** | Nhận diện xe cứu thương/cứu hỏa, hoặc nhận tín hiệu ưu tiên, rồi chuyển xanh cho hướng đó (vẫn qua vàng → all-red) | Demo ấn tượng, ý nghĩa thực tế |
| X2 | **Phát hiện vi phạm** | Vượt đèn đỏ, đi sai làn, dừng quá vạch (vạch ảo + tracking) | Mở rộng E03 |
| X3 | **Hàng chờ và thời gian chờ** | Ước lượng độ dài hàng chờ (m) và thời gian chờ trung bình mỗi xe | Chỉ số đánh giá US14 |
| X4 | **Mô phỏng SUMO** | Tái hiện nút giao, so sánh các chiến lược | NFR14, số liệu cho báo cáo |
| X5 | **Dự báo lưu lượng** | LSTM / Prophet dự báo 15–30 phút tới, làm đầu vào cho LLM | Điều khiển chủ động |
| X6 | **Làn sóng xanh** | Phối hợp offset giữa các nút giao liên tiếp | Hướng nâng cao |
| X7 | **Bản đồ tổng quan** | Leaflet hiển thị các nút giao, tô màu theo mức mật độ | UX dashboard |
| X8 | **Ẩn danh hóa video** | Làm mờ biển số và khuôn mặt trong video lưu trữ | NFR15 |
| X9 | **Thông báo đa kênh** | Đẩy cảnh báo qua Telegram/Email theo mức độ | FR13, FR14 |
| X10 | **Replay sự kiện** | Phát lại video và trạng thái đèn quanh thời điểm sự cố | Điều tra sự cố |

## 8. Thiết kế dữ liệu

### 8.1. Các bảng chính

| Bảng | Trường chính |
|---|---|
| `users` | id, username, password_hash (bcrypt), full_name, role, is_locked, created_at |
| `intersections` | id, name, lat, lng, status, control_mode (AUTO/MANUAL/FIXED/FLASH) |
| `approaches` | id, intersection_id, direction (N/S/E/W), lanes, saturation_flow |
| `cameras` | id, intersection_id, approach_id, stream_url, status, last_seen_at |
| `zones` | id, camera_id, type (COUNT_LINE/QUEUE_AREA/STOP_LINE), polygon (JSON) |
| `phases` | id, intersection_id, order, green_approaches, min_green, max_green, yellow, all_red |
| `traffic_metrics` | ts, approach_id, count_car, count_moto, count_bus, count_truck, density, queue_len |
| `signal_plans` | id, intersection_id, cycle_length, splits (JSON), source (FIXED/ALGO/LLM/MANUAL), applied_at |
| `llm_decisions` | id, intersection_id, input_context (JSON), output (JSON), accepted, reject_reason, latency_ms, created_at |
| `alerts` | id, type (CONGESTION/DEVICE/SAFETY/EMERGENCY), severity, intersection_id, message, status, created_at, resolved_at |
| `audit_logs` | id, user_id, action, target, detail (JSON), ip, created_at |
| `settings` | key, value (JSON), updated_by, updated_at |

### 8.2. Lưu trữ và thời hạn (NFR09, NFR15)

- `traffic_metrics`: lưu chi tiết 30 ngày, sau đó gộp theo 15 phút và giữ 1 năm.
- Video: không lưu mặc định. Chỉ lưu clip ±30 s quanh sự cố, đã làm mờ, giữ 7 ngày.
- `audit_logs`, `signal_plans`, `llm_decisions`: chỉ ghi thêm (append-only), lưu tối thiểu 1 năm.

## 9. Thiết kế API

| Method | Endpoint | Mô tả | Quyền |
|---|---|---|---|
| POST | `/api/auth/login` | Đăng nhập, trả JWT | Public |
| GET/POST/PUT | `/api/users` | Quản lý tài khoản | Admin |
| GET/POST/PUT/DELETE | `/api/intersections` | Quản lý nút giao | Admin (ghi), All (đọc) |
| GET/POST/PUT/DELETE | `/api/cameras` | Quản lý camera | Admin |
| GET | `/api/cameras/{id}/stream` | Luồng MJPEG/HLS có overlay | Operator+ |
| GET | `/api/intersections/{id}/metrics` | Số liệu hiện tại | All |
| POST | `/api/intersections/{id}/mode` | Chuyển chế độ | Operator+ |
| POST | `/api/intersections/{id}/manual-phase` | Đổi pha thủ công | Operator+ |
| PUT | `/api/intersections/{id}/phases` | Cấu hình pha đèn | Admin |
| GET | `/api/llm/decisions` | Lịch sử quyết định LLM | Manager+ |
| POST | `/api/llm/decisions/{id}/approve` | Duyệt đề xuất (chế độ Advisory) | Operator+ |
| POST | `/api/assistant/chat` | Trợ lý vận hành (streaming) | All (tool theo quyền) |
| GET | `/api/alerts` | Danh sách cảnh báo | All |
| GET | `/api/stats` | Thống kê theo bộ lọc | Manager+ |
| GET | `/api/reports/export` | Xuất CSV/PDF | Manager+ |
| GET | `/api/audit-logs` | Nhật ký hoạt động | Admin, Manager |
| WS | `/ws/live` | Đẩy metrics, trạng thái đèn, cảnh báo | Theo token |

## 10. Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Backend | Python 3.10+, FastAPI, SQLAlchemy, Pydantic, WebSocket |
| CSDL / Cache | PostgreSQL (SQLite khi dev), Redis |
| Thị giác máy tính | Ultralytics YOLOv8/YOLO11, ByteTrack, OpenCV, Supervision |
| LLM | Claude API (Anthropic SDK): Haiku 5.5 / Sonnet 5.5; tool use, structured output, prompt caching |
| Dự báo | Prophet hoặc PyTorch LSTM |
| Mô phỏng | SUMO + TraCI |
| Frontend | React, Vite, TailwindCSS, Recharts, Leaflet |
| Xác thực | JWT (access/refresh), bcrypt |
| Triển khai | Docker Compose |
| Kiểm thử | pytest, Playwright |

## 11. An toàn, bảo mật và quyền riêng tư

### 11.1. Phân quyền (FR02)

| Chức năng | Admin | Manager | Operator | Viewer |
|---|:-:|:-:|:-:|:-:|
| Quản lý tài khoản | ✔ | | | |
| Cấu hình nút giao, camera, pha | ✔ | | | |
| Xem video trực tiếp | ✔ | ✔ | ✔ | |
| Điều khiển đèn / chuyển chế độ | ✔ | | ✔ | |
| Duyệt đề xuất LLM | ✔ | | ✔ | |
| Xem thống kê, báo cáo, nhật ký | ✔ | ✔ | Một phần | Một phần |

> Ghi chú: đặc tả nêu 3 vai trò (Quản trị viên, Người vận hành, Người xem dữ liệu); vai trò "Người quản lý" xuất hiện trong US13, US14, US16 nên được bổ sung thành vai trò riêng.

### 11.2. Bảo mật (NFR08)

- Mật khẩu băm bằng bcrypt. Khóa tài khoản sau 5 lần đăng nhập sai.
- JWT có hạn ngắn (15 phút) kèm refresh token. HTTPS khi triển khai.
- API key của LLM chỉ lưu ở backend (biến môi trường), không bao giờ gửi xuống frontend.
- **Chống prompt injection:**
  - Dữ liệu đưa vào LLM chỉ là số liệu có cấu trúc.
  - Đầu ra luôn được validate theo schema.
  - LLM không có quyền gọi trực tiếp adapter đèn.

### 11.3. An toàn điều khiển (NFR06, NFR07, NFR12)

- Safety Guard là chốt chặn cuối cùng và không thể bị tắt qua giao diện.
- Giao diện điều khiển thủ công có hộp thoại xác nhận, hiển thị pha hiện tại và pha kế tiếp, và chặn bấm liên tục.
- Mọi lệnh đều ghi `audit_logs` kèm người thực hiện và nguồn lệnh (MANUAL/ALGO/LLM).

## 12. Kế hoạch kiểm thử và đánh giá

### 12.1. Kiểm thử chức năng

| Loại | Nội dung |
|---|---|
| Unit test | Safety Guard (mọi ràng buộc, ma trận xung đột), Webster, đếm qua vạch, validator JSON |
| Integration | Vision → Backend → Controller → Adapter giả lập |
| Fault injection | Ngắt camera, LLM timeout, LLM trả JSON sai hoặc giá trị ngoài miền, mất adapter |
| E2E | Playwright: đăng nhập, xem camera, chuyển chế độ, xuất báo cáo |

### 12.2. Đánh giá nhận diện (NFR03)

- Bộ dữ liệu: video giao thông Việt Nam, gán nhãn khoảng 500–1000 khung hình.
- Chỉ số: Precision, Recall, mAP@0.5 theo lớp; sai số đếm |đếm tay − đếm máy| / đếm tay.
- Hiệu năng (NFR02): FPS trên CPU và GPU ở các độ phân giải 640/960.

### 12.3. Đánh giá điều khiển (US14)

Thực nghiệm trên SUMO với 3 kịch bản lưu lượng: thấp, cao điểm, bất đối xứng (một hướng tăng đột biến).

| Phương án | Mô tả |
|---|---|
| B0 | Chu kỳ cố định |
| B1 | Webster thích ứng |
| B2 | Max-Pressure |
| **P1** | **Webster + LLM Supervisor** |

**Chỉ số so sánh:** thời gian chờ trung bình, độ dài hàng chờ tối đa, thông lượng (xe/giờ), số lần dừng, số lần Safety Guard can thiệp.

**Đánh giá riêng LLM:**

- Tỉ lệ đúng schema.
- Độ trễ p50 và p95.
- Tỉ lệ đề xuất bị Safety Guard chặn.
- Chi phí mỗi giờ.
- Chất lượng giải thích (người đánh giá chấm thang 1–5).

## 13. Kế hoạch triển khai (Sprint)

| Sprint | Thời gian | Nội dung | Kết quả |
|---|---|---|---|
| S1 | Tuần 1–2 | Khung dự án, Auth/RBAC, CRUD nút giao/camera, audit log | E01, E07 (một phần) |
| S2 | Tuần 3–4 | Stream video, YOLO + tracking, đếm theo vùng, overlay | E02, E03 (US05, US06) |
| S3 | Tuần 5–6 | Mật độ/hàng chờ, cảnh báo ùn tắc và thiết bị, WebSocket dashboard | E03 (US07), E05 |
| S4 | Tuần 7–8 | Adapter giả lập, Safety Guard, Webster, thủ công/tự động, chuyển chế độ | E04 |
| S5 | Tuần 9–10 | LLM Supervisor (L1, L2), chế độ Advisory/Autonomous | Điểm nhấn LLM |
| S6 | Tuần 11–12 | Trợ lý chat (L3), báo cáo tự động (L4), xe ưu tiên (X1) | Mở rộng |
| S7 | Tuần 13–14 | SUMO, thực nghiệm so sánh, thống kê/báo cáo, hoàn thiện tài liệu | E06, báo cáo cuối |

## 14. Rủi ro và phương án xử lý

| Rủi ro | Mức | Phương án |
|---|---|---|
| Thiếu camera và đèn thật | Cao | Dùng video mẫu, RTSP giả lập và SUMO; thiết kế adapter |
| YOLO nhận diện kém với xe máy dày đặc | Trung bình | Fine-tune trên dữ liệu Việt Nam; dùng mật độ theo diện tích chiếm dụng thay vì chỉ đếm |
| LLM chậm, tốn phí hoặc mất mạng | Trung bình | Gọi theo sự kiện, prompt caching, fallback về tầng 2, hỗ trợ model cục bộ |
| LLM đề xuất sai | Trung bình | Schema cứng, giới hạn miền giá trị, Safety Guard, chế độ Advisory |
| Thiếu GPU | Trung bình | YOLO bản nano, giảm FPS xử lý (5–10 FPS là đủ cho việc đếm) |
| Trễ tiến độ | Trung bình | Ưu tiên MVP (S1–S5); X2, X5, X6 là phần tùy chọn |

## 15. Ma trận truy vết yêu cầu

| Yêu cầu | Module / Tính năng | Sprint |
|---|---|---|
| FR01, FR02, NFR08 | Auth, RBAC | S1 |
| FR03, US03, US04 | Video stream, multi-view | S2 |
| FR04, FR18, US15 | CRUD camera/nút giao, cấu hình zone | S1–S2 |
| FR05, FR06, FR07 | Vision Service (YOLO + ByteTrack) | S2 |
| FR08, US07 | Mật độ, hàng chờ, L6 | S3 |
| FR09, FR11, US08, US10 | Điều khiển thủ công, chuyển chế độ | S4 |
| FR10, US09 | Webster + LLM Supervisor (L1) | S4–S5 |
| FR12 | Cấu hình pha | S4 |
| FR13, FR14, US11, US12 | Alert engine, L5, X9 | S3 |
| FR15, FR16, US13, US14 | Thống kê, báo cáo, L4, SUMO | S6–S7 |
| FR17, US16 | Audit log, `llm_decisions` | S1–S5 |
| NFR06, NFR07 | Safety Guard, fail-safe | S4 |
| NFR12 | XAI (L2), UI xác nhận | S5 |
| NFR14 | SUMO, fault injection | S7 |
| NFR15 | Ẩn danh hóa (X8), chính sách lưu trữ | S6 |

## 16. Kết luận và hướng phát triển

Đề tài đáp ứng đầy đủ 7 Epic, 18 yêu cầu chức năng và 15 yêu cầu phi chức năng trong đặc tả. Đóng góp chính là **kiến trúc điều khiển 3 tầng**: LLM đảm nhận vai trò giám sát chiến lược và giải thích, thuật toán cổ điển đảm bảo phản hồi thời gian thực, và lớp an toàn tất định đảm bảo không phát lệnh nguy hiểm. Hệ thống có thể kiểm chứng định lượng trên mô phỏng SUMO trước khi triển khai thực tế.

**Hướng phát triển:**

- Học tăng cường (RL) cho tầng 2, với LLM làm reward shaping hoặc giám sát.
- Phối hợp đa nút giao (làn sóng xanh) ở quy mô tuyến đường.
- Kết nối tủ điều khiển thực theo chuẩn NTCIP.
- Triển khai suy luận tại biên (edge AI) trên Jetson.
- Kết hợp dữ liệu GPS và bản đồ số để ước lượng lưu lượng ngoài vùng camera.
