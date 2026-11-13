# PR #123 — sửa quyền truy cập Redis fixture trên Linux

Nhánh: `fix/dependency-release-118-119`; commit gặp lỗi: `b842112`.
Run GitHub đã kiểm tra:
<https://github.com/mkien14/homewallet-gr13/actions/runs/43372771072>.

## Nguyên nhân thực tế

Backend job đã chạy qua **217 test, 59 skip**. Bước kế tiếp
`python ../scripts/run-redis-acceptance.py` thất bại vì Redis TLS không khởi động.
`TemporaryDirectory` trên Linux có mode `0700`, thuộc runner; Redis fixture lại
chạy UID/GID cố định `999:999`, không thể đi vào thư mục để đọc config/cert/key.
Kiểm tra trước đó dùng Docker Desktop Windows và `--image`, đã không tái hiện
được quyền bind mount POSIX của CI. Năm check khác của PR vẫn xanh.

## Bản sửa

- Trên POSIX, Redis fixture dùng UID/GID hiện tại của người chạy helper.
  Thư mục vẫn `0700`; cert/key/config là `0600`, không mở quyền cho user khác.
- Trên Windows Docker Desktop giữ UID/GID fixture `999:999`.
- Nếu container dừng lúc khởi động, helper báo exit code và log giới hạn, che
  mật khẩu test, thay vì chỉ đợi hết thời gian và trả lỗi chung.
- Thêm 5 test regression cho UID/GID Linux, nhánh Windows và quyền/chứng chỉ
  localhost. Giữ nguyên các test TLS, xác thực và cache/rate limit.

## Tái hiện và kiểm tra

Đã chạy Linux Python **3.12.16**, pytest **9.2.0**, UID/GID **10001:10001**,
cài bằng `requirements-dev.txt` và gọi helper theo đúng đường mặc định của CI
(không dùng `--image`). Docker daemon kiểm thử nằm trong container Linux riêng;
không mount Docker socket host hay AWS credentials vào môi trường đó.

| Kiểm tra | Kết quả |
| --- | --- |
| Helper cũ từ commit b842112 trên Linux | Tái hiện cùng lỗi `Disposable TLS Redis did not become ready`, exit 1 |
| Helper đã sửa, cùng môi trường và user | 9 test Redis/client PASS, exit 0 |
| Toàn bộ Backend trên Linux Python 3.12 | 222 PASS, 59 SKIP, exit 0 |
| Release safety tests trên Linux | 9 PASS, exit 0 |
| Test regression helper trên Windows | 5 PASS |
| Helper mới trên Windows Docker Desktop, đường --image | 9 PASS, exit 0 |

Các ca DB/môi trường chuyên biệt vẫn skip theo điều kiện sẵn có; đây không phải
nghiệm thu AWS/HA. Tài nguyên Linux/Docker được tạo riêng cho lượt kiểm tra và
dọn sau khi hoàn tất. Log đầy đủ giữ ngoài Git trong thư mục tạm.

Bản sửa local chưa được commit/push bởi agent. PR #123 chỉ có kết quả GitHub
mới sau khi Kiên commit và push lên cùng nhánh. Chờ mọi check trên head mới xanh
trước Squash and merge; không lấy lần chạy lỗi cũ làm kết quả cho bản sửa này.
