# HomeWallet: kế hoạch vận hành production

Cập nhật 13/11/2026. Người phụ trách: Kiên. Nhánh: `fix/production-integration`.

**Đã chuẩn bị code và cấu hình; chưa triển khai production.** Lần này chưa apply
Terraform, đổi traffic, ghi secret, gửi thư hay bật Scheduler. Kiên commit/push.
PR #102 và #103 đã có trên main. Migration 006 và API `hw-api:22` của Hoàng đã
được Kiên triển khai; đó chưa phải bản application hardening trong nhánh này.
Xem [biên bản ghép thay đổi](acceptance/production-integration-20261113.md).

`docs/runbooks/production-readiness.md` và `infra/envs/prod` mô tả phương án stack
riêng do PR #103 bổ sung, cần domain/ACM và ngân sách riêng. Đó không phải hướng
đang được chọn. Không chạy workflow **Reviewed production release** cho stack
hiện tại: workflow đó chỉ chấp nhận tài nguyên `homewallet-prod`.

## Phương án đã chọn

- Giữ account `179923444714`, Singapore và URL
  `https://daoedidcrnf1f.cloudfront.net`. Không mua domain hay thêm account.
- Chuyển có kiểm soát stack hiện tại sang profile ứng dụng production. Tên/state
  vẫn chứa `dev`; không rename tài nguyên hay tạo VPC/RDS thứ hai. Sau chuyển,
  phát triển ở mock/local: dùng chung stack không có cách ly dev/production.
- Browser → CloudFront → API Gateway HTTP API dùng HTTPS. API Gateway → VPC Link
  → ALB → API dùng HTTP **bên trong VPC**, không phải TLS trên mọi hop. Tái sử dụng
  ALB; API Gateway cần ngân sách theo lưu lượng.
  [AWS: private integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html).
- Phát hành chức năng cốt lõi trước: `GEMINI_ENABLED=false`, `OCR_ENABLED=false`.
  Giữ nhập chi tiêu thủ công, ngân sách, hộ và cộng đồng; gợi ý ngân sách dùng
  quy tắc hiện có. AI/OCR là release sau, có đổi khóa và nghiệm thu #34.
- Scheduler giữ DISABLED. Bật lại sau nghiệm thu người nhận, opt-out,
  bounce/complaint, chống gửi trùng và delivery; không tự bật khi deploy.
- Giữ dữ liệu/hình/DLQ #36/#39 theo quyết định quản lý; không xóa, phát lại, gửi
  thư hay dùng dữ liệu hộ ngoài nhóm làm fixture. Cần review ranh giới dữ liệu
  và người nhận trước khi đưa stack hiện tại vào vận hành.
- Multi-AZ, backup/restore, bảo vệ xóa DB, scaling/health checks, retention log và
  runbook rollback đã có code của Chi cho stack riêng; chưa áp dụng cho stack
  đang chạy. Cần chuyển cấu hình phù hợp sang stack hiện tại theo change riêng,
  review state/service addresses và chi phí, rồi có bằng chứng restore/rollback.
  Không dùng việc merge PR #103 để xác nhận HA của stack hiện tại đã đạt.

## Code đã bổ sung

| Phần | Cách xử lý |
| --- | --- |
| Đăng nhập | React/SRP chính, Hosted UI dự phòng. Mật khẩu mới 10 ký tự/chữ hoa/chữ thường/số. Profile production bỏ callback localhost và client CLI password flow, không xóa User Pool. |
| MFA | Menu → Bảo mật tài khoản cho người dùng tự bật và ưu tiên TOTP. Chủ tài khoản nhập mã bằng thiết bị của mình; chưa bật thay ai. Phải kiểm tra challenge khi đăng nhập lại. |
| Giới hạn | Redis dùng chung task, admission atomic. 120 request/phút, 30 write/phút/user; Redis lỗi chặn write/costly bằng 503, read vẫn có thể dùng MySQL. |
| Hạn mức | Upload 10/user, 30/hộ, 200/toàn hệ thống/ngày; AI suggestion 10/20/100. Ngày UTC+7. Đây là số thao tác, không phải trần hóa đơn AWS: retry có thể phát sinh nhiều provider call. |
| Dữ liệu | Trang /privacy song ngữ, checkbox đồng ý xử lý hóa đơn, audit action RECEIPT_PROCESSING_CONSENT_V1 trong bảng hiện có; không thêm migration. |
| Worker | OCR production tắt thì pause trước ReceiveMessage, không đẩy dữ liệu đang giữ vào DLQ. Log production không in nội dung hóa đơn/S3 key; lỗi provider không giữ raw message. |
| API | Origin header bắt buộc production, constant-time comparison; no-store JSON; request ID do server tạo; body API tối đa 1 MiB; quota có Retry-After. Upload S3 trực tiếp vẫn tối đa 5 MiB/tệp. |
| HTTPS | Module api-https thêm HTTP API + VPC Link và SG riêng tới ALB. Tạo origin, chuyển traffic và đóng ingress HTTP cũ là ba phase riêng. |
| WAF/CSP | COUNT → BLOCK sau canary. Profile production tạo CSP theo đúng S3/Cognito/Google Fonts, hạn chế script/frame/object và quyền thiết bị không dùng. |
| Artifact | API/worker/jobs cùng image digest và APP_RELEASE Git SHA; ECR khóa tag immutable, giữ tagged release image để task restart không mất image do dev cleanup. Deploy Dev chặn profile production trước push/deploy. |
| Candidate CI | Workflow Build release candidate chạy từ main, audit dependency/secret/history/container, build cùng commit, checksum artifact; action/scanner pin commit/digest. Không có quyền AWS và không tự deploy. |
| Container | Python 3.12/Alpine 3.24 pin digest, nhiều stage, 56 dependency runtime khóa hash; bỏ SQLite không dùng bằng apk và bỏ binding Python, không che inventory. UID/GID 10001. ECS production drop ALL capabilities và bật init process cho API/worker/jobs. |
| Gate | production-preflight.py chỉ đọc metadata, không GetSecretValue hay gửi email. Kiểm tra HTTPS, WAF, cache, profile, image, bucket, client/admin TOTP, SES, budget, Scheduler và bàn giao resilience. GO không thay nghiệm thu UI/tenant isolation. |

## Đầu vào chưa có

1. Kiên đã chốt **100 USD/tháng**. Chuẩn bị thêm budget HomeWallet riêng, giữ
   nguyên Group-Monthly-Cost-Budget 50 USD và Zero-Spend Budget đang có.
   Budget alert không tự khóa chi tiêu; cần cấu hình subscriber thật khi apply.
2. Xác nhận khóa Gemini lộ trước đây đã **thu hồi tại Google project HWAPI**.
   Đổi version AWS không thu hồi Google key. Phiên AWS không có quyền Google để
   làm thay bước này. Không gửi key mới trong chat. Profile tắt Gemini và không
   nạp key cũ cho API/worker trong lúc chờ.
3. Chủ tài khoản admin tự đăng ký TOTP và kiểm tra đăng nhập lại.
4. Kiên chốt giữ/exclude household 1; cố định danh sách hộ hiện có khác 1 vào
   allowlist khi triển khai, không tự cho hộ tương lai vào. Cognito khóa tự đăng
   ký trong profile production. Tài khoản chưa có hộ/hộ không được duyệt bị
   chặn trước bước tạo user. Không thay dữ liệu hộ 1.
5. Bàn giao hạ tầng của Chi vẫn **chưa nghiệm thu** theo xác nhận của Kiên; cần
   bằng chứng trên đúng stack đang chạy và biên bản nghiệm thu release commit.

## Kiểm tra đã thực hiện

- Frontend lint/build sau ghép PR #103: PASS; còn cảnh báo bundle lớn. npm audit:
  0 lỗ hổng tại thời điểm kiểm tra 13/11/2026.
- Python compile các module/script thay đổi: PASS; workflow YAML parse thành công.
- Terraform fmt/validate cho cả dev/prod: PASS. Có plan HTTPS chỉ đọc trên dev;
  không apply, không thay DB, VPC hoặc service. Có thay revision task definition
  API trong plan để khớp image đang chạy; phải review, không gọi đây là no-op.
- Build container local: PASS. Image dùng APP_RELEASE=working-tree để review,
  không phải artifact release từ commit đã duyệt.
- Container scan cũ: 47 HIGH Debian. Bản Dockerfile cuối chuyển sang Alpine 3.24
  và khóa dependency đã build/quét lại: **0 HIGH, 0 CRITICAL, 0 secret finding**;
  pip-audit 56 dependency: 0 lỗ hổng đã biết. Không ignore/hạ ngưỡng. Đây là
  image local, chưa deploy và chưa nghiệm thu tương thích chức năng với musl.
  Xem [biên bản và checksum](acceptance/container-security-20261113.md).
- Candidate lưu scan/SBOM có checksum; verifier đối chiếu đúng image config,
  release và tuổi scan tối đa 72 giờ. Publish đối chiếu image ECR đang chạy với
  candidate. Preflight kiểm tra cả API/worker/jobs, cấu hình container và MFA
  challenge, không chỉ API. Kết quả chỉ đọc trên AWS vẫn NO_GO, không phải lỗi
  container local còn 47 HIGH.
- Sau yêu cầu nghiệm thu candidate của Kiên: 25 backend targeted tests và 9
  release-script tests PASS; frontend 96 tests/lint/production build PASS;
  Terraform mock tests dev 1, prod riêng 3 PASS. Không chạy trên DB thật.
  Xem [quyết định/bàn giao mới](acceptance/production-owner-decisions-20261113.md).
  Chưa nghiệm thu candidate từ commit main hoặc chạy load test.
- Chưa chạy workflow GitHub, chưa có artifact release được nghiệm thu, chưa
  smoke test endpoint production. Không suy diễn các bước trên đã PASS.

## Chuyển phiên bản

Xem [runbook triển khai](production-rollout.md). Flag mặc định giữ hành vi dev.
Không apply file ví dụ khi chưa điền ngân sách/digest và review saved plan.
