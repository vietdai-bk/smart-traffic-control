# Báo cáo thay đổi giao diện STCS

## Kế hoạch trước khi chỉnh sửa

Mục tiêu: giảm cảm giác bóng, nhiều hiệu ứng và màu trang trí; tạo giao diện điều hành giản dị, rõ thứ bậc, dễ đọc.

Qua kiểm tra mã, các yếu tố cần cải thiện gồm nền kính mờ, bóng màu, chữ gradient trên trang đăng nhập, viền/ring lặp lại trên panel và hiệu ứng co nút. Thay đổi giới hạn ở CSS, cấu hình giao diện Tailwind và class/style của các thành phần có sẵn.

Phạm vi dự kiến:
- `frontend/src/index.css`: nền trung tính sáng/tối, độ tương phản chữ phụ, bóng nhẹ và panel đặc.
- `frontend/tailwind.config.js`: thống nhất bo góc nhỏ hơn.
- `frontend/src/components/ui/primitives.tsx`: panel, nút, badge, tabs tiết chế hơn; giữ màu trạng thái.
- `frontend/src/components/layout/AppShell.tsx`: giảm nền trong suốt và bóng trang trí.
- `frontend/src/pages/LoginPage.tsx`: bỏ chữ gradient và kính mờ, giảm độ đậm và bóng.

Giới hạn: không đổi API, phân quyền, state, callback, định tuyến, cấu trúc điều khiển đèn, camera, thuật toán hoặc phụ thuộc. Giữ bố cục responsive, chế độ sáng/tối, cảnh báo, focus bàn phím và reduced motion.

Rủi ro: component dùng chung ảnh hưởng nhiều trang; màu chữ và trạng thái cần giữ dễ phân biệt. Typecheck/build không thay thế kiểm tra trực quan trên trình duyệt.

Kiểm tra sau thay đổi: `npx --no-install tsc -b --noEmit`, `npm run build`, đối chiếu diff để chắc chắn chỉ thay đổi trình bày. Nếu có công cụ trình duyệt cục bộ, kiểm tra màn hình desktop/mobile. Không dùng dịch vụ ngoài để xuất bản dự án.

Hoàn tác: khôi phục các file giao diện từ bản sao trước chỉnh sửa; không reset các thay đổi đã tồn tại của người dùng.

## Kết quả thực hiện

Đã hoàn tất đúng năm file dự kiến:
- Nền sáng xám trung tính, nền tối bớt xanh; chữ phụ chế độ tối sáng hơn.
- Panel dùng nền đặc, viền đơn, khoảng đệm rõ hơn; bo góc panel/card 8px, nút 6px.
- Nút dùng màu phẳng, bỏ bóng màu và hiệu ứng co ở component dùng chung; badge giảm độ đậm nền, dot bỏ quầng sáng; giữ màu và animation cảnh báo.
- Thanh điều hướng, header, menu chọn nút giao dùng nền đặc; mục đang chọn có nền trung tính và chữ nhấn.
- Trang đăng nhập bỏ nền lưới, chữ gradient và kính mờ; giảm chữ quá đậm, giảm padding form trên mobile.

Kết quả kiểm tra:
- `npx --no-install tsc -b --noEmit`: đạt, exit 0.
- `npm run build`: đạt, Vite build production thành công.
- Đã đọc diff: thay đổi ở class/style và token trình bày, không thay đổi logic nghiệp vụ.
- Không chạy lại backend test vì không sửa backend hoặc giao thức API.
- Chưa kiểm tra trực quan bằng trình duyệt; chưa xác nhận hiển thị thực tế trên mọi kích thước màn hình.

Bản sao nguyên trạng trước chỉnh sửa: `/tmp/stcs-ui-before-refresh/`, giữ cấu trúc đường dẫn frontend. Đây là bản sao tạm; có thể bị dọn khi hệ thống làm sạch `/tmp`. Muốn hoàn tác, chép lại đúng năm file tương ứng từ bản sao, không dùng `git reset --hard` vì dự án đã có thay đổi trước đó.

Xem thay đổi: khi Vite đang chạy, tải lại trang; nếu chạy production, khởi động lại backend sau bản build mới. Nên xem trang đăng nhập và giám sát ở cả sáng/tối, desktop/mobile; kiểm tra menu, hộp thoại xác nhận và màu cảnh báo.

## Bổ sung: rút gọn thanh điều hướng

Yêu cầu: chỉ hiển thị tên mục chính, bỏ dòng mô tả nhỏ bên dưới. Kế hoạch trước sửa: bỏ phần hiển thị `n.hint` trong sidebar desktop và menu “Thêm” mobile; căn giữa icon với tên mục. Giữ tuyến đường, phân quyền và số cảnh báo.

Kết quả: đã bỏ mô tả phụ ở cả hai vị trí và căn lại icon; TypeScript kiểm tra đạt. Không đổi hành vi điều hướng.

## Fine-tune LLM Supervisor — kế hoạch trước triển khai

Mục tiêu: huấn luyện có giám sát (SFT) để model trả JSON chiến lược/trọng số và lý do tiếng Việt theo đúng hợp đồng của Supervisor. Fine-tune cập nhật trọng số (hoặc adapter LoRA), khác với sửa prompt. Không huấn luyện phần trợ lý chat/tool calling trong bước này.

Các bước:
1. Xuất nhật ký `llm_decisions` thành dữ liệu ứng viên, chỉ đọc SQLite, không thay đổi database hoặc backend.
2. Người duyệt sửa và xác nhận từng nhãn. Trạng thái APPROVED/APPLIED trong nhật ký không chứng minh nhãn tối ưu; không tự coi đầu ra model là đáp án chuẩn.
3. Chọn model nền phù hợp tài nguyên và giấy phép. Model Groq đang dùng là endpoint suy luận; không thể tải adapter tùy ý lên endpoint bằng cách đổi tên model.
4. Tách train/validation/test theo thời gian hoặc nhóm tình huống để tránh rò rỉ mẫu gần trùng. Dùng đúng SYSTEM_PROMPT và context của Supervisor.
5. Huấn luyện SFT/LoRA trong môi trường riêng; đánh giá JSON hợp lệ, validator, sai lệch số liệu và hiệu quả hàng đợi/chờ so với model nền trên mô phỏng.
6. Chỉ tích hợp checkpoint đã đánh giá qua server suy luận tương thích API; giữ nguyên validator, Webster và FSM. Trước hết chạy chế độ tư vấn.

Phạm vi bước chuẩn bị: thêm công cụ xuất dữ liệu và hướng dẫn trong `backend/finetuning/`. Không sửa `.env`, requirements backend, API, FSM, prompt đang chạy hoặc tải model/dữ liệu lên dịch vụ ngoài.

Điều kiện chưa có: lựa chọn model, nơi huấn luyện và bộ nhãn được kiểm duyệt. `nvidia-smi` hiện không giao tiếp được driver trong môi trường công cụ. Vì vậy chưa thể tuyên bố đã fine-tune hoặc chuyển hệ thống sang model mới.

### Kết quả bước chuẩn bị fine-tune

- Đã thêm `backend/finetuning/export_candidates.py` và `backend/finetuning/README.md`.
- Truy vấn chỉ đọc database hiện tại: bảng `llm_decisions` có 0 bản ghi. Chạy exporter: không có mẫu, không tạo dataset giả.
- Kiểm tra bằng SQLite tạm: chỉ lấy APPROVED/APPLIED; mọi mẫu đều chưa duyệt; không ghi đè output; số bản ghi nguồn giữ nguyên. Các kiểm tra đạt.
- Không thay đổi mã backend/frontend đang chạy hoặc cấu hình model.
- Chưa huấn luyện: thiếu dataset được duyệt, model nền và nơi huấn luyện. Đã hỏi người dùng về nguồn dữ liệu và Colab/máy huấn luyện. Chưa có checkpoint, adapter LoRA hay kết quả chất lượng để triển khai.

## 2026-11-12 — Giảm thông tin và thao tác khẩn cấp nhanh

Kế hoạch trước sửa: tập trung màn hình giám sát, bảng điều khiển và thẻ Webster. Giảm KPI trùng lặp (chế độ/chu kỳ đã có trong bảng riêng), bỏ màu trang trí; đưa thông số thuật toán vào mục mở rộng. Thay dropdown chọn hướng giữ xanh bằng hai nút Bắc–Nam/Đông–Tây, đưa nhóm ưu tiên lên trước lệnh thường; giữ chọn thời gian và nút bỏ giữ. Thao tác vẫn mở modal yêu cầu lý do và xác nhận, gửi đúng HOLD_PHASE với phase_id/duration_s như cũ. Không thay đổi API, quyền, backend, thời gian chuyển pha hoặc khoá an toàn. Chớp vàng và khôi phục vẫn giữ xác nhận mã nút giao.

Kiểm chứng: typecheck, build và kiểm tra mapping hai nút hướng, trạng thái disabled, payload và luồng xác nhận. Chưa coi build là kiểm chứng trực quan.

Kết quả thực hiện 2026-11-12:
- `CommandCenterPage.tsx`: còn bốn KPI chính; chế độ và chu kỳ vẫn có ở bảng điều khiển/thẻ đề xuất. Bỏ dải màu và màu chữ trang trí; chuyển chú thích KPI sang tooltip.
- `SignalControlPanel.tsx`: chế độ chỉ còn nhãn tiếng Việt, màu trung tính; bỏ quầng sáng đếm ngược và badge “đủ xanh tối thiểu” dư thừa. Trạng thái đang khoá, giữ pha, xếp lịch, lỗi và màu đèn vẫn hiển thị.
- Đưa nhóm ưu tiên khẩn cấp lên trước lệnh thường. Hai nút trực tiếp chọn phase_id=1 (Bắc–Nam), phase_id=2 (Đông–Tây), giữ lựa chọn 30/60/120 giây hoặc đến khi bỏ. Có nút bỏ giữ khi đang giữ pha. Nhanh hơn ở thao tác chọn hướng, không rút ngắn thời gian chuyển pha an toàn.
- `AdaptivePlanCard.tsx`: nền trung tính; thu gọn nhu cầu, tỷ số Y và giải thích vào details/summary. Thời gian xanh đề xuất, thời gian đang thực thi và cảnh báo gần bão hoà vẫn hiện.
- `npm run build` (bao gồm `tsc -b`) đạt, Vite build thành công. Đọc kiểm tra mapping phase_id, duration_s, requireReason, disabled và xác nhận dùng lại luồng cũ. Chưa chạy kiểm thử tương tác/hiển thị trong trình duyệt; chưa khẳng định mọi kích thước màn hình đều đã kiểm chứng.
- Chỉ sửa ba file frontend kể trên trong đợt này; không sửa backend hoặc dependencies. Bản sao trước đợt này tại `/tmp/stcs-ui-nov12/` (tạm thời, có thể bị hệ thống dọn).

## 2026-11-12 — Rút gọn tiêu đề, bỏ Viewer và giữ xanh một chạm

Kế hoạch trước sửa: giữ bố cục/chức năng Tài khoản & Nhật ký; xoá mô tả phụ ngay dưới tiêu đề các trang. Bỏ tài khoản demo Viewer và lựa chọn tạo mới Viewer trên frontend, giữ tương thích tài khoản Viewer đã có, không xoá dữ liệu tài khoản trong database. Hai nút giữ xanh khẩn cấp và bỏ giữ gửi lệnh ngay khi bấm, không mở modal. Gửi confirm=true theo hợp đồng API, dùng lý do thao tác nhanh để lưu audit; khoá khi đang gửi để chống lặp. Giữ kiểm tra quyền, kết nối và FSM backend. Các lệnh khác vẫn dùng xác nhận hiện có.

Kết quả: đã bỏ mô tả dưới tiêu đề Tài khoản, Cảnh báo, Cấu hình và Phân tích; giữ bảng tài khoản, tab nhật ký và các thao tác quản trị. Bỏ Viewer khỏi đăng nhập demo và danh sách vai trò tạo mới; tài khoản Viewer cũ vẫn chỉnh sửa được, chưa xoá/khóa trong database. Giữ xanh hai hướng và bỏ giữ thực thi một chạm, có trạng thái đang gửi và khoá đồng bộ chống nhấn lặp. Giữ backend confirm=true, phân quyền và giới hạn FSM; các lệnh khác vẫn xác nhận như cũ.

Kiểm tra: build production (gồm TypeScript) đạt. Harness chạy handler thực tế với API giả lập đạt các trường hợp payload đúng hướng/thời gian/nút giao, chặn nhấn lặp, bỏ giữ, thiếu quyền/trạng thái disabled và mở khoá khi lỗi. Không gửi lệnh tới hệ thống đang chạy. Chưa kiểm tra trực quan trong trình duyệt.

## 2026-11-12 — Xác nhận khẩn cấp tại chỗ và ẩn Viewer trong RBAC

Kế hoạch: lần bấm đầu chỉ chọn lệnh giữ xanh/bỏ giữ; hiện nút Xác nhận và Huỷ ngay trong khối khẩn cấp. Chỉ gửi API khi xác nhận; huỷ lựa chọn khi đổi nút giao, thời gian, trạng thái giữ hoặc kết nối. Giữ khoá chống gửi lặp. Loại Viewer khỏi cột ma trận quyền, không xoá tài khoản/database.

Kết quả: đã thêm Xác nhận/Huỷ tại khối khẩn cấp cho giữ xanh và bỏ giữ. Nút chọn lệnh chỉ cập nhật lựa chọn, duy nhất nút Xác nhận gọi handler gửi lệnh. Lựa chọn được xoá khi đổi ngữ cảnh; giữ chống gửi lặp và khoá theo quyền/kết nối. Viewer không còn cột trong ma trận RBAC. TypeScript và build production đạt; đã kiểm tra luồng gọi trong mã, chưa kiểm thử tương tác trên trình duyệt. Không sửa backend.

## Điều chỉnh xác nhận khẩn cấp dạng pop-up

Theo yêu cầu mới: thay xác nhận tại chỗ bằng Modal nổi, chỉ gồm tên nút giao/lệnh và hai nút Huỷ, Xác nhận; không nhập lý do hoặc tick checkbox. Tái sử dụng Modal hiện có, giữ khoá đang gửi và logic backend. Bảng quyền không thay đổi thêm.

Đã triển khai pop-up Modal thay khối xác nhận inline. Chỉ nút Xác nhận gửi API; Huỷ/đóng không gửi. Pop-up hiển thị tên nút giao, hướng và thời gian giữ; khoá thao tác trong lúc gửi. TypeScript và build production đạt. Chưa kiểm tra trực quan trong trình duyệt.

## Cố định danh sách nút giao khi cuộn cấu hình

Kế hoạch: chỉ chỉnh CSS của panel danh sách trong ConfigPage. Ở bố cục hai cột (xl), danh sách dùng sticky dưới header với chiều cao giới hạn theo viewport; nội dung danh sách cuộn riêng khi dài. Giữ bố cục cuộn tự nhiên trên mobile và không sửa logic chọn/lưu nút giao.

Đã áp dụng sticky và cuộn độc lập cho danh sách; header danh sách không co lại. TypeScript và build production đạt. Chưa kiểm tra cuộn trực quan trong trình duyệt.
