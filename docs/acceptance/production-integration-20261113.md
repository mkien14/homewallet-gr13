# Ghép PR #102/#103 và application hardening — 13/11/2026

**Trạng thái: code để review, chưa commit/push hay triển khai production.**
Nhánh `fix/production-integration`, nền main `63fd2b9` (PR #103), sau `d10e7b9`
(PR #102). Không tạo clone/worktree mới. Kiên tự commit/push.

## Phần đã có trước đợt ghép

Kiên đã chạy migration 006 và grant SELECT/INSERT cho hw_runtime bằng task riêng;
exit code 0. API Hoàng lên `hw-api:22`, running=desired=1, pending=0, stable=true.
Kết quả được Kiên cung cấp và metadata ECS đã được đọc lại; không chạy migration
lần nữa. Đây chưa phải deployment của các thay đổi hardening dưới đây.

50 file công việc trước đó được khôi phục từ stash
`75f31e72fe05d14218f5a5805fe83ae0a014470a`; stash vẫn giữ để đối chiếu.
Sáu xung đột đã được ghép: API main, compute outputs, ECR, edge main/variables,
network variables. Không bỏ readiness hoặc sửa logic membership của Hoàng.

## Các sửa lỗi của Chi

1. SNS bổ sung quyền publish cho CloudWatch, giới hạn account, region và ARN
   alarm `homewallet-prod-*`; giữ quyền sự kiện RDS.
   [AWS CloudWatch/SNS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Notify_Users_Alarm_Changes.html).
2. EventBridge lọc ECS deployment failure theo ARN service API/worker trong
   `resources`, cùng account/region. Bỏ bộ lọc `detail.clusterArn` vì event
   deployment không có trường này.
   [AWS ECS deployment events](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_service_deployment_events.html).
3. Pipeline chặn thay đổi ngoài image và APP_RELEASE; chặn cấu hình unknown,
   task mới hoặc thay đổi migration/bootstrap chưa được apply riêng. Artifact
   chỉ ghi metadata và revision ARN đã review, không ghi cấu hình/secret.
   Deploy lấy đúng revision đã review, giữ cấu hình còn lại, đổi image+APP_RELEASE;
   không clone tùy ý revision service đang chạy hoặc family jobs mới nhất.
4. Migration image có input riêng để một application release không tự đổi
   revision migration/bootstrap. Cấu hình app production được ghép vào root
   tùy chọn prod, tắt AI/OCR và bỏ nạp Gemini key trong release core.

## Tương thích khi ghép

- Giữ liveness/readiness của Chi. Origin guard miễn `/health`, `/ready` cho ALB;
  các route `/api/*` vẫn yêu cầu origin header.
- Edge giữ cả HTTPS origin bằng chứng chỉ của Chi và HTTPS API Gateway cho
  phương án không domain. ECR giữ release tag ở cả hai profile.
- Giữ task revisions cũ qua skip_destroy để phục hồi có kiểm soát.
- Helper HTTPS giữ đầy đủ image URI/tag/digest của các task hiện có, bao gồm
  image digest API vừa triển khai; không quay về default image cũ.
- Chỉ cập nhật đầu vào các fixture test đã có cho contract mới; không thêm test.

## Phương án vận hành đang chọn

Giữ account, dữ liệu và CloudFront hiện tại; không mua domain hoặc apply stack
`infra/envs/prod` mới. Xem [quyết định](../production-readiness.md) và
[runbook](../production-rollout.md). Workflow Reviewed production release chỉ
dành cho stack riêng; không dùng nó để deploy cluster `homewallet`.

Code HA của Chi chưa chuyển thành HA trên stack đang chạy. Việc áp dụng phải
review state/service address, ngân sách và tài nguyên trước, rồi có bằng chứng
restore/rollback. Các acceptance cũ không được đổi thành nghiệm thu HA mới.

## Kiểm tra và giới hạn

- Frontend lint/build: PASS, còn cảnh báo bundle lớn; npm audit 0 lỗ hổng.
- Python syntax và workflow YAML: PASS; Terraform fmt/validate dev và prod: PASS.
- Docker build: PASS, chỉ image local APP_RELEASE=working-tree, chưa publish.
- Image scan ban đầu: NO-GO, 47 phát hiện HIGH thuộc Debian, 0 CRITICAL, 0 có FixedVersion
  tại thời điểm scan. Không có HIGH/CRITICAL Python package hoặc secret finding
  trong phạm vi image scan. Báo cáo đầy đủ để ngoài Git trong thư mục tạm.
- Có saved plan HTTPS chỉ đọc; không apply. Plan thêm API Gateway/VPC Link/SG,
  WAF rate COUNT và task metadata/revision cần review. Không suy diễn no-op hay
  nghiệm thu traffic từ validate/plan.
  Lần plan cuối: 8 resource create, 4 update, 1 task-definition replacement,
  1 data read; không đổi RDS, VPC hoặc ECS service. Replacement API giữ revision
  trước bằng skip_destroy, không phải thay service. Plan thuộc working tree,
  phải tạo lại từ commit được review trước khi có quyết định apply.
- Không chạy bộ test, regression, load test, gửi email/push, ghi secret hay bật
  Scheduler. Khi đọc lại metadata, ba lịch gốc đều DISABLED, API vẫn `hw-api:22`.
- Chưa revoke Gemini key tại Google, chưa có lựa chọn ngân sách tháng, chưa có
  sign-off HA/restore hoặc artifact release đã ký duyệt. Chưa kết luận production.

## Bổ sung: gỡ chặn container và củng cố gate phát hành

Dockerfile cuối Python 3.12/Alpine 3.24 pin digest, nhiều stage và khóa hash
dependency đã build/quét lại: 0 HIGH, 0 CRITICAL, 0 secret finding; pip-audit
56 dependency đạt, SBOM 95 component. Không ignore hoặc hạ ngưỡng. Chỉ image
local APP_RELEASE=working-tree, chưa deploy/nghiệm thu tương thích chức năng.
Candidate workflow, verifier và preflight được bổ sung evidence/digest/runtime
gates. Plan HTTPS đã tạo lại, số lượng/phạm vi thay đổi giữ như trên; không apply.
Xem [biên bản riêng](container-security-20261113.md).
