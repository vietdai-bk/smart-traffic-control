# Chuẩn bị fine-tune Supervisor

Đây là bước chuẩn bị dữ liệu, chưa phải model đã fine-tune.
Không thay đổi backend đang chạy; công cụ chỉ dùng thư viện chuẩn Python.

Chạy từ thư mục gốc dự án:

```bash
python3 backend/finetuning/export_candidates.py \
  --database backend/data/stcs.db \
  --output /tmp/stcs-supervisor-candidates.jsonl
```

Công cụ chỉ đọc database, chọn quyết định APPROVED/APPLIED có context và nhãn đầy đủ, luôn đánh dấu `reviewed: false`. Không ghi đè file đã có. Nếu không có mẫu, công cụ không tạo dữ liệu giả.

Duyệt từng mẫu: đối chiếu context, sửa target, ghi người duyệt và căn cứ vào review_note rồi mới đặt reviewed=true. Duyệt trong ứng dụng không đồng nghĩa nhãn đã đủ chất lượng cho huấn luyện. Không đưa thông tin nhạy cảm hoặc dữ liệu chưa được phép chia sẻ lên nền tảng huấn luyện.

Định dạng SFT sau khi duyệt: messages gồm system=SYSTEM_PROMPT trong app/llm/supervisor.py, user=JSON context, assistant=JSON target. Lưu phiên bản prompt cùng dataset. Không tự đưa các mẫu chưa duyệt vào train.

Tiếp theo cần chọn model nền và máy huấn luyện. Tạo môi trường riêng cho thư viện huấn luyện; giữ requirements backend nguyên trạng. Tách tập dữ liệu theo thời gian/nhóm tình huống, loại trùng trước khi huấn luyện LoRA/SFT. Giữ tập test riêng. Đánh giá tính hợp lệ JSON, validator, bịa số liệu và hiệu quả điều khiển so với model nền trước khi tích hợp.

Không đổi STCS_LLM_MODEL sang tên adapter cục bộ tại endpoint Groq: cần nơi phục vụ model tương thích API và hỗ trợ model đó. Việc dùng model Supervisor mới cũng cần tách khỏi model trợ lý nếu chỉ huấn luyện nhiệm vụ Supervisor.
