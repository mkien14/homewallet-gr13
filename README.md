# homewallet-gr13

## Nạp/cập nhật schema database local

Schema được quản lý bằng các migration trong `backend/db/migrations/`. Không
nạp file SQL bằng tay: runner tự áp dụng migration chưa chạy theo thứ tự tên
file và ghi nhận trong bảng `schema_migrations`.

1. Khởi động MySQL local. Nếu container phát triển `hw-mysql` đã được tạo:

   ```powershell
   docker start hw-mysql
   ```

2. Mở PowerShell ở thư mục gốc repo, đặt thông tin kết nối mặc định của nhóm:

   ```powershell
   $env:DB_HOST = "localhost"
   $env:DB_PORT = "3307"
   $env:DB_USER = "root"
   $env:DB_PASSWORD = "devpass"
   ```

   Nếu máy bạn dùng MySQL hoặc credentials khác, thay các giá trị cho phù hợp.
3. Chạy runner từ thư mục `backend`:

   ```powershell
   cd backend
   python -m pip install -r requirements.txt
   python jobs/migrate.py
   ```

Runner tạo database `homewallet` nếu chưa tồn tại. Chạy lại các lệnh trên sau
khi kéo migration mới; những file đã áp dụng sẽ được bỏ qua. Với database cũ
đã có bảng `users` nhưng chưa có bảng theo dõi migration, runner tự đánh dấu
`001_init.sql` là đã chạy rồi tiếp tục áp dụng migration mới.

Các migration hiện có:

- `001_init.sql`: tạo schema ban đầu.
- `002_add_receipt_warnings.sql`: thêm cột JSON `warnings` vào `receipts`.

Khi thay đổi schema, hãy thêm file migration mới với số thứ tự tiếp theo. Không
sửa các migration đã được chia sẻ hoặc đã áp dụng.
