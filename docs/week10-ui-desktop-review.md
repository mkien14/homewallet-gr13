# Tuần 10 — bằng chứng UI desktop (bản mock)

Ngày rà soát: 2026-11-03
Nhánh: `feat/ui-responsive-auth-community`
Môi trường: Vite mock trên laptop, Chrome, viewport desktop hiển thị khoảng 1700 × 950 px. Dữ liệu trong bản preview chỉ nằm trên trình duyệt.

## #26 — Web Push và thông báo trong app

- Đã có trang `/notifications`, trạng thái hỗ trợ/quyền trình duyệt, bật/tắt đăng ký theo thao tác chủ động, lưu/đối chiếu browser subscription qua API và trạng thái cấu hình VAPID còn thiếu.
- Danh sách thông báo gọi `GET /api/notifications`; mở thông báo gọi `PATCH /api/notifications/{id}` rồi điều hướng theo `deep_link` nội bộ.
- Service worker xử lý push chỉ với `event_type` và `deep_link`, hiển thị nội dung chung theo locale đã lưu, không đưa dữ liệu giao dịch lên lock screen.
- Đã mở thử một thông báo ngân sách trong mock; trang đích là `/budgets`.
- Đã bật/tắt đăng ký giả trong mock và tải lại; trạng thái mô phỏng được giữ lại. Ca này không gọi quyền trình duyệt hay tạo subscription thật.
- Chưa nghiệm thu giao nhận push thật: môi trường chưa có `VITE_VAPID_PUBLIC_KEY`/khóa private tương ứng và chưa chạy qua HTTPS dev. Không bật quyền thông báo trong lần rà soát này.

## #29 — Community/admin

- Thành viên thấy danh sách bài `APPROVED` và có thể gửi mẹo tiết kiệm hoặc mẫu ngân sách mới ở trạng thái `PENDING`.
- Admin nhìn thấy hàng chờ, trạng thái, và thao tác sửa/duyệt/ẩn. Quyền trên bản thật được đọc từ Cognito group `homewallet-dev-admins`; API vẫn phải kiểm tra quyền.
- Đã xem giao diện member và chuyển sang chế độ admin trong mock; demo role chỉ sửa dữ liệu giả ở trình duyệt.
- Repo tại thời điểm rà soát chưa có community/admin API hoặc contract Hoàng trong `docs/`. UI đang gọi các route `/api/community/posts` và `/api/admin/community/posts`; cần đối chiếu contract và nối API thật trước khi đánh dấu nghiệm thu tích hợp.

## Kiểm tra giao diện

- Đã xem `VI + Sáng`, `EN + Tối` trên laptop; chuyển locale/theme không làm mất trang hiện tại.
- Mở thông báo điều hướng đúng trang; hiển thị menu có liên kết Thông báo và Cộng đồng.
- Build frontend: PASS (`npm.cmd run build`).
- Frontend tests: PASS, 72/72 (`npm.cmd test`).
- Lint: PASS (`npm.cmd run lint`).
- Đã nhận ảnh kiểm tra thực tế trên điện thoại; thấy bảng hóa đơn và bộ lọc bị tràn/ép chữ. Đã thêm layout thẻ và quy tắc responsive; cần tải lại tunnel để nghiệm thu bản sửa.

## Còn lại trước nghiệm thu cuối

1. Chốt community API contract và chạy member/admin trên API thật; xác nhận member nhận `403` khi gọi admin action và bài `PENDING` không xuất hiện với member.
2. Cấu hình public VAPID key với private key đã cấp ở jobs task, dùng HTTPS dev, rồi kiểm tra bật/tắt, reload và push click-through.
3. Làm lượt kiểm tra mobile sau, theo cả VI/EN và Sáng/Tối; lưu ảnh trước/sau và viewport thực tế.
