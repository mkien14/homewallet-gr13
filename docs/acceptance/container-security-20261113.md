# Container và phần chuẩn bị production — 13/11/2026

**Container local đạt gate; production chưa triển khai.** Nhánh hiện tại
`fix/production-integration`; Kiên giữ phần commit/push. Không tạo worktree/clone.

## Xử lý 47 HIGH

47 phát hiện cũ thuộc 11 CVE trên 18 package Debian 13.7. Upgrade package đã
không giải quyết hết vì các bản vá chưa được cung cấp cho nhánh đó. Không thêm
ignore, không dùng `--ignore-unfixed`, không xóa database package để che scanner.

Chọn official `python:3.12-alpine3.24`, pin manifest SHA256 trong Dockerfile.
Giữ Python 3.12; thay hệ điều hành bằng Alpine 3.24 đang được hỗ trợ. Không chọn
Bookworm vì SQLite vẫn bị ảnh hưởng; không trộn package Debian unstable vào stable.

- [Docker Official Image Python: các biến thể được hỗ trợ](https://hub.docker.com/_/python).
- [Alpine: nhánh 3.24 hỗ trợ main đến 01/06/2028](https://alpinelinux.org/releases/).
- [Debian: SQLite CVE-2026-119374 còn ảnh hưởng Bookworm/Trixie](https://security-tracker.debian.org/tracker/CVE-2026-119374).

Dockerfile build nhiều stage: dependency native dùng wheel musllinux; chỉ
`http-ece` là source distribution Python thuần được build wheel ở stage riêng.
Runtime không nhận build tools/wheel cache. Khóa đủ 56 dependency runtime cùng
hash PyPI trong `backend/requirements.lock`; Docker kiểm hash và `pip check`.
Các requirement gốc cũng được nạp khi resolve để tránh bỏ sót dependency mới.
Giữ CA RDS và các entry point API/worker/jobs. Runtime dùng UID/GID 10001.

Đối chiếu SBOM phát hiện base Alpine vẫn có SQLite 3.53.4, nằm trong khoảng
ảnh hưởng của các CVE SQLite nêu trên dù feed Trivy Alpine chưa báo HIGH. Vì
HomeWallet dùng MySQL, source app/jobs và các dependency runtime không tham
chiếu SQLite, bản cuối bỏ binding `_sqlite3`, thư viện chuẩn `sqlite3`, rồi
tính lại dependency ELF và gỡ `sqlite-libs` qua apk. Không force broken world
hay xóa package metadata. Runtime **không còn hỗ trợ SQLite**; dependency mới
đòi SQLite phải được thiết kế/review lại. Verifier từ chối SBOM có SQLite, để
không tái đưa package này vào dựa trên kết quả scanner bằng 0.

## Kết quả thực tế

| Kiểm tra | Kết quả |
| --- | --- |
| Build Linux amd64 từ Dockerfile cuối | PASS |
| Trivy 0.76.2, OS và Python HIGH/CRITICAL, kể cả chưa có bản vá | 0 HIGH, 0 CRITICAL |
| Trivy secret trong image | 0 finding |
| pip-audit với lock và require-hashes/strict | 56 dependency, 0 lỗ hổng đã biết |
| CycloneDX SBOM | 95 component |
| Python syntax, workflow YAML | PASS |
| Terraform fmt/validate dev và prod | PASS |

Image ID: `sha256:b7db14c31a952f5a2522176d2f7c5758c4ad2c886644d462a79d684847e9f443`.
Image chỉ local, `APP_RELEASE=working-tree`; không gắn nhãn một commit sạch giả.
Scanner host ghi thời gian UTC trong JSON; ngày biên bản theo Asia/Bangkok.
Số liệu, source checksum và evidence checksum nằm trong
[JSON bằng chứng](container-security-20261113.json). Báo cáo gốc, SBOM và image
tar nằm ngoài Git tại `%TEMP%\homewallet-hardening-scan`; chuyển sang nơi lưu trữ
nội bộ nếu cần giữ lâu. Không đưa image tar vào Git.

Không chạy bộ test ứng dụng, regression, load test hoặc kiểm thử tương thích
chức năng sau đổi libc sang musl. Build/hash/scan không thay thế nghiệm thu đó.
Kết quả chỉ đúng với image và cơ sở dữ liệu lỗ hổng tại thời điểm quét; không
khẳng định image sẽ luôn không có lỗ hổng.

## Công việc production tiếp theo đã chuẩn bị

1. Candidate workflow giữ báo cáo Trivy và SBOM trong artifact có checksum.
   Chặn HIGH/CRITICAL, secret, OS hết hỗ trợ; scanner pin digest, không bỏ lỗi
   chưa có bản vá. Chỉ đóng gói sau khi mọi bước đạt.
2. Verifier đối chiếu scan/SBOM với image config trong tar, SHA release và user
   không đặc quyền. Báo cáo phải trong 72 giờ; quá hạn build/quét lại. Khi
   publish frontend, đối chiếu config digest từ ECR của API đang chạy với đúng
   candidate, ngoài kiểm tra APP_RELEASE. Checksum không thay xác minh nguồn:
   chỉ dùng artifact từ workflow main đã review của nhóm.
   Cũng chặn SQLite ở SBOM độc lập với mức severity do scanner cung cấp.
3. Profile production API/worker/jobs dùng user 10001:10001, drop ALL Linux
   capabilities, init process. Flag mặc định không đổi task đang chạy.
4. Preflight kiểm tra cả API/worker/jobs cùng image/SHA/profile, private network,
   ECR immutable, cấu hình container và lịch trỏ đúng revision jobs. Có gate
   riêng cho chủ admin xác nhận challenge MFA khi đăng nhập lại.
5. Đã tạo lại plan HTTPS chỉ đọc: 8 create, 4 update, 1 task-definition
   replacement có giữ revision cũ, 1 data read. Không thay RDS/VPC/ECS service.
   Không apply; phải tạo lại từ commit đã review trước triển khai.

## Trạng thái AWS và việc còn cần thực hiện

Preflight chỉ đọc vẫn **NO_GO**: origin chưa HTTPS, WAF chưa enforce, runtime
chưa chuyển profile/digest đồng nhất, ECR chưa immutable, client CLI/callback
localhost chưa bỏ, MFA admin/challenge chưa đạt. Chưa có lựa chọn budget,
review ranh giới dữ liệu hay sign-off resilience. Không đổi các attestation
thành true để vượt gate. Không đọc secret value, gửi thư/push hoặc bật Scheduler.

Thứ tự tiếp tục: Kiên review/commit/push/merge → CI/candidate từ main → nghiệm
thu tương thích API/worker/jobs với Alpine → chốt budget, MFA và bàn giao hạ
tầng/dữ liệu → tạo HTTPS origin, canary rồi đổi traffic → apply profile → gate
và publish frontend cùng release. Xem [runbook](../production-rollout.md).

## Bổ sung sau khi Kiên yêu cầu nghiệm thu candidate

Kiên đã chốt 100 USD/tháng và giữ/exclude household 1. Đã bổ sung policy hộ và
test, cấu hình budget optional và khóa self-signup. 25 backend targeted tests,
9 script tests, 96 frontend tests, production FE build/lint và 4 Terraform mock
tests đạt. Đây là source mới **sau** image scan ghi ở trên; candidate từ main
phải build/quét source này lại. Bằng chứng image cũ không thay thế candidate.
Xem [quyết định và bàn giao](production-owner-decisions-20261113.md) và
[hướng dẫn commit/candidate](../production-commit-and-candidate.md).
