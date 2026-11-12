# Lịch sử hộ: triển khai và giới hạn

Chức năng trả hộ đang tham gia từ `household_members`; mỗi lần rời hộ, bị chủ hộ xóa hoặc hộ giải tán sẽ lưu ảnh chụp tên hộ, vai trò, thời gian và lý do vào `household_membership_history` trong cùng transaction với việc xóa membership. Bảng lịch sử không có khóa ngoại tới `households`, để bản ghi vẫn tồn tại khi hộ bị xóa. Không lưu mã mời, giao dịch hay ảnh trong lịch sử. API chỉ lọc theo user đã xác thực.

Không thể phục hồi đầy đủ những lần tham gia đã kết thúc trước khi tính năng được đưa vào sử dụng. Các membership còn tồn tại đã có thời điểm tham gia và sẽ được hiển thị, không cần backfill. Thời gian là `DATETIME` do database cung cấp, không có thông tin múi giờ.

Đây là kế hoạch cho admin review; không tự chạy trên môi trường chia sẻ:

1. Kiểm tra CI, sao lưu theo quy trình nhóm và chốt cửa sổ triển khai. Ngăn thao tác tạo, tham gia, rời, xóa thành viên hoặc giải tán trong suốt thời gian chuyển đổi; backend bản cũ vẫn có thể xóa membership mà không ghi lịch sử.
2. Chạy migration `006_household_membership_history.sql` bằng quy trình migration được cấp quyền. Xác minh bảng mới; cấp `hw_runtime` đúng quyền `SELECT, INSERT` trên bảng theo `backend/db/bootstrap/runtime-grants.sql` nếu môi trường dùng tài khoản runtime. Việc cập nhật grant cần admin thực hiện và kiểm tra, không chạy bootstrap lại một cách mù quáng.
3. Triển khai backend mới, bảo đảm tất cả instance phục vụ yêu cầu đã chuyển sang bản mới và có quyền cần thiết. Chỉ sau đó mở lại thao tác membership; triển khai frontend theo quy trình riêng.
4. Với fixture thử nghiệm được nhóm duyệt, kiểm tra hộ hiện tại, rời và tham gia lại, chủ hộ xóa thành viên, giải tán, và lịch sử chỉ có dữ liệu của tài khoản đang đăng nhập. Không kiểm tra bằng cách giải tán hộ thật.

Giải tán vẫn sử dụng luồng xóa S3 hiện có: lịch sử được ghi trong transaction trước khi bắt đầu xóa S3 nhưng chỉ commit cùng các thay đổi database. Nếu xóa S3 thành công một phần hoặc DB lỗi sau đó, ảnh có thể đã bị xóa dù hộ chưa giải tán hoàn toàn; cần kiểm tra và xử lý theo quy trình vận hành, không tự động chạy lại.
