# Phát hành production core 26a0645 — 13/11/2026

**PASS — gate cuối GO, 90/90 kiểm tra đạt.** Phạm vi phục vụ là 16 hộ đã được
Kiên duyệt; chưa mở đăng ký công khai. Frontend/backend đã triển khai trên AWS.

## 1. Nguồn và phiên bản đang chạy

| Mục | Giá trị |
| --- | --- |
| Main commit | `26a0645709af3acb123768bb21a6a788d4252373` |
| Build release candidate | [43408857810 — SUCCESS](https://github.com/mkien14/homewallet-gr13/actions/runs/43408857810) |
| Artifact ID | `14028223709` |
| ZIP SHA-256 | `3551435f94a24d1208a305c06cef61b6aa7b4e49fd3f4b885a7ad62c8d54e91c` |
| ECR image digest | `sha256:dfef1a60b3fee7e1733563a3aa040ebfc1cb0d92021b154b16f00eb788d74348` |
| API | `hw-api:29`, running/desired 2/2, healthy tại `ap-southeast-1a` và `ap-southeast-1b` |
| Worker / jobs | `hw-worker:6` chạy 1/1; `hw-jobs:6` là target của ba lịch DISABLED |
| Website | https://daoedidcrnf1f.cloudfront.net |
| Account / Region | `179923444714` / `ap-southeast-1` |

Sáu check CI của main và workflow candidate thành công. Source/history secret
scan, npm/pip audit và kiểm tra SBOM đạt. Container scan có **0 HIGH, 0 CRITICAL,
0 secret finding**, bao gồm phát hiện chưa có bản vá. Checksum từng file và
image config digest trong artifact đã được đối chiếu với image ECR đang chạy.
Kết quả phản ánh phiên bản và feed tại lúc quét, không phải bảo đảm không có CVE mới.

## 2. Triển khai và nghiệm thu ứng dụng

- API, worker và jobs dùng cùng image digest và `APP_RELEASE`. Giữ production
  profile, các secret/role/network/log, UID/GID 10001, drop ALL capabilities và
  init process; tag revision được giữ theo baseline.
- Frontend gồm 29 file từ chính artifact trên: upload asset trước, index sau,
  giữ asset cũ. Invalidation `I9G1LFWAENJBLBCZVBMVJBEHPM` đã COMPLETED.
  Hash index công khai khớp candidate; `/release.json` và `/api/release` cùng
  SHA `26a0645…`, `/api/ready` trả 200 ready. VersionId entry point được lưu
  ngoài Git để phục hồi có kiểm soát.
- Có **42 kiểm tra API trong đợt exercise**, thêm hai request kiểm tra/xóa hộ thử
  khi cleanup (44 event trong JSON). Bao phủ profile, categories, giao dịch
  CRUD/idempotency, dashboard/CSV, ngân sách/gợi ý rule, hóa đơn định kỳ CRUD,
  cộng đồng và từ chối non-admin, JSON lỗi 400, truy cập chéo hộ 1 trả 404,
  danh tính ngoài allowlist trả 403 và OCR đang tắt trả 503.
- Lượt ghi thứ 31 bị giới hạn với **429 và Retry-After**; response API được kiểm
  tra không phải cache hit. Đây là phép thử quota, chưa phải benchmark tải.
- Microsoft Edge headless, phiên mới: đăng nhập **React/SRP và challenge TOTP
  thực tế** thành công; 12 kiểm tra trang/mobile đạt, không có page error hoặc
  API 5xx. Viewport 390×844 không tràn ngang. Không hiện nút tự đăng ký và input
  OCR upload. Tài khoản tổng hợp được dùng cho phép thử, không dùng bí mật của Kiên.
- Jobs chạy `python -m jobs.recurring_alerts --help`, exit 0. Không gửi email/push
  hoặc gọi Gemini/OCR trong đợt nghiệm thu này.

## 3. Restore, HA và rollback cùng candidate

- PITR và snapshot được phục hồi sang hai DB riêng. Kiểm tra MySQL TLS,
  migration 006, quyền runtime, giao dịch commit/rollback tổng hợp và startup,
  auth gate/readiness ứng dụng bằng image candidate đạt. Thời gian đến kiểm tra
  ứng dụng đạt: **858,1 giây (~14,3 phút)** cho PITR và **618,5 giây (~10,3 phút)**
  cho snapshot; độ trễ restore point **66,1 giây**.
- Dừng một API task: ECS thay task, trở về hai task/hai AZ, quan sát 110,8 giây.
  Redis đổi primary và ứng dụng phục hồi, quan sát 91,5 giây. RDS có sự kiện AWS
  bắt đầu/kết thúc forced failover cách nhau 55,0 giây; toàn phép thử quan sát
  126,7 giây. Metadata AZ của RDS không đổi nên không tuyên bố đã quan sát đổi AZ.
  Các thời gian gồm nhịp polling, không đại diện downtime hoặc SLA.
- Probe sau failover xác nhận MySQL TLS, Redis TLS/AUTH/RESP2, Lua với Redis client
  8.1; test key đã dọn.
- Rollback API thực tế: `:30` (candidate) → `:28` (production cũ `1bba075…`) →
  `:30` (candidate) đạt. Sau cleanup chuyển sang **`:29`** với allowlist cuối,
  chờ stable và gate 90/90; revision thử `:30` đã deregister.
- DB clone, SG, role và task definition validator/probe tạm đã dọn. Snapshot
  `hw-prod-before-core-20261113-d8aca388` giữ đến **27/11/2026** theo tag quản lý;
  tag không tự xóa snapshot khi đến hạn. Snapshot checkpoint cũ vẫn giữ.

Restore dùng startup probe với profile dev cô lập; production profile được kiểm
tra riêng trên hộ tổng hợp ở ứng dụng đang chạy. Chưa đổi endpoint primary sang
DB phục hồi, chưa diễn tập mất toàn bộ AZ, chưa chạy tải kéo dài hoặc hạ frontend
về release khác. Không diễn giải các phép thử trên thành những kết quả này.

## 4. Ranh giới và cleanup dữ liệu

Allowlist cuối: `2,3,4,5,6,7,8,9,11,12,13,22,23,24,25,26`.
Hộ thử 28 được cho phép tạm thời ở revision `:30`, đã xóa qua API; hai Cognito
identity tổng hợp đã xóa và xác nhận không tồn tại. Hộ 28 không còn trong
allowlist của API `:29`/worker `:6`; password/TOTP seed của fixture đã bỏ khỏi
file vận hành. Một số hàng user/history tổng hợp còn được giữ làm audit.

Hộ 1 cùng ảnh/dữ liệu/DLQ được giữ nguyên; không purge, redrive, replay hay OCR.
AI/Gemini/OCR, tự đăng ký và ba lịch Scheduler vẫn tắt. Thu hồi khóa cũ ở Google
project HWAPI, nghiệm thu gửi email/push theo lịch và inbox alarm SNS là các việc
riêng trước khi mở những khả năng tương ứng; không coi đã đạt trong biên bản này.

## 5. Phương thức triển khai và lưu ý Terraform

Terraform plan local bị timeout khi đọc metadata secret VAPID qua endpoint
Secrets Manager Singapore. Kết nối trong VPC vẫn cấp secret cho task được.
Plan đã dừng, lock của chính tiến trình đó đã giải phóng sau khi kiểm tra;
**không có Terraform apply, import hoặc state push** trong đợt này.

Image và `APP_RELEASE` được đổi bằng đăng ký revision ECS từ baseline production,
đối chiếu cấu hình container chỉ thay hai trường này; giữ tag và chính sách
rollout. Cập nhật API/worker và ba target Scheduler bằng API AWS, lịch vẫn
DISABLED. Các file production tfvars/settings vận hành ngoài Git đã cập nhật
sang release mới.

**State/output Terraform có thể còn tham chiếu revision cũ.** Không tuyên bố
Terraform “No changes”. Trước lần apply hạ tầng tiếp theo cần xử lý kết nối
metadata, tạo saved plan với input production mới và review chênh lệch. Chênh
lệch phát hành dự kiến là đăng ký task definition; dừng nếu plan đề xuất hạ
profile, thay/xóa DB, network, service hoặc tài nguyên ngoài phạm vi được duyệt.
Không chạy lại Deploy Dev hoặc apply default dev để đồng bộ phiên bản.

## 6. Hồ sơ và bàn giao

- [Kết quả release và API](production-release-26a0645-20261113.json).
- [Gate cuối 90/90](production-preflight-26a0645-20261113.json).
- [Browser/SRP/TOTP](production-browser-26a0645-20261113.json).
- [Restore/HA/rollback](production-resilience-26a0645-20261113.json).
- [Runbook và lệnh commit/push](../runbooks/current-stack-production.md).

File vận hành bền vững ở `%LOCALAPPDATA%\HomeWallet\production\20261113`, bộ hồ
sơ release ở `releases\26a0645`, có ACL hạn chế và không nằm trong Git. Không
upload artifact, state, tfvars, token, password, TOTP seed hoặc email subscriber.
Tám file bằng chứng/tài liệu của đợt này ở nhánh `release/production-26a0645`;
Kiên review, commit và push. Agent chưa stage, commit hoặc push.
