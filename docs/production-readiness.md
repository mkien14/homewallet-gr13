# HomeWallet: production trên stack hiện tại

Cập nhật **14/11/2026**. Chủ vận hành: **Kiên**.
**Đã phát hành bản công khai** tại https://daoedidcrnf1f.cloudfront.net; người dùng mới có thể đăng ký, xác minh email, tạo hộ hoặc tham gia bằng mã mời. Đây là cùng AWS account/stack hiện hữu, không yêu cầu domain hay account AWS khác.

## Điểm chuẩn đang chạy

| Phần | Trạng thái |
| --- | --- |
| Source / candidate | Main `16f87ea10d4fc6c47afd198e3ee77274fa6c3013`; [candidate run 43567562979](https://github.com/mkien14/homewallet-gr13/actions/runs/43567562979) |
| Candidate/image | Artifact `14102797171`; immutable backend image và scan được ghi trong [biên bản phát hành](acceptance/production-public-16f87ea-20261114.md) |
| Runtime | API `hw-api:38` (2/2, hai AZ), worker `hw-worker:14` (1/1), jobs `hw-jobs:12` |
| Public registration | Cognito self-signup và xác minh email bật; React/SRP là chính, Hosted UI/PKCE dự phòng trên HTTPS |
| Người dùng mới | Admin xác nhận trực tiếp: signup, email verification, login, tạo hộ và tham gia hộ đã thành công |
| Phạm vi dữ liệu | Quyền theo membership; household 1 và dữ liệu/ảnh/queue/DLQ cũ vẫn giữ riêng |
| Lịch định kỳ | `hw-recurring-reminders`, `hw-budget-alerts`, `hw-weekly-report` ENABLED, target jobs :12, `Asia/Ho_Chi_Minh` |
| HTTPS/WAF/HA | CloudFront HTTPS, WAF; API hai AZ, autoscaling/health checks; RDS Multi-AZ, Redis failover và NAT mỗi AZ |
| Bảo mật dữ liệu | RDS private/encrypted/TLS, backup 14 ngày và deletion protection; Redis TLS/AUTH; logs 30 ngày |
| OCR | Gemini 3.5 Flash Lite tại worker, consent/quota/household checks; live OCR của tài khoản công khai mới chưa được thử trong nghiệm thu này |
| Chi phí | AWS Budget cảnh báo 100 USD/tháng; đây không phải số thực chi hay hard cap. Gemini được tính riêng, ngoài AWS Budget |
| Gate / Terraform | Production preflight **99/99 GO**; saved plan đối chiếu AWS cuối **No changes** |

Tên/tag `dev` và state key `dev/terraform.tfstate` vẫn là tên cũ của stack production đang chạy. Không chạy Deploy Dev hoặc apply `infra/envs/prod` vào stack này. TLS được tuyên bố theo từng hop đã kiểm tra, không mặc định mọi kết nối nội bộ đều dùng TLS.

## Nghiệm thu hiện hành

- [Bản phát hành công khai 16f87ea](acceptance/production-public-16f87ea-20261114.md): candidate, runtime, 99 gate, publish frontend, ba lịch và giới hạn nghiệm thu. Admin trực tiếp xác nhận signup, xác minh email, đăng nhập, tạo hộ và tham gia hộ.
- [Bằng chứng máy đọc được](acceptance/production-public-16f87ea-20261114.json) và [preflight 99/99](acceptance/production-preflight-20261114.json).
- [OCR canary lịch sử](acceptance/production-ocr-a5097aa-20261114.json): ảnh tổng hợp và release được nêu trong bản ghi; không dùng nó để tuyên bố live OCR của người dùng công khai mới đã được thử.
- [Các diễn tập phục hồi lịch sử](acceptance/production-resilience-a5097aa-20261114.json) và biên bản hiện hành: restore, task replacement, RDS/Redis failover và rollback có ghi rõ release/thời điểm.

## Phạm vi và giới hạn

Đăng ký công khai đã bật; hộ mới không cần allowlist. Mọi nghiệp vụ vẫn kiểm tra membership. Household 1 cùng dữ liệu, ảnh và queue/DLQ cũ không được đưa vào phạm vi công khai; không receive/purge/replay queue cũ. Việc kiểm tra truy cập hộ 1 dùng danh tính không thuộc hộ và trả 404.

Các lịch đang ENABLED chỉ chứng minh cấu hình đã bật; biên nhận email/push phải được xác minh riêng theo từng kỳ. Báo cáo này không đưa ra số “chi phí thực tế”: chưa có kỳ Cost Explorer/hóa đơn phân bổ riêng cho project được chốt. Google Gemini nằm ngoài AWS Budget. Live OCR trên ảnh hóa đơn mới của người dùng công khai, benchmark OCR rộng và SLA dài hạn chưa được xác nhận bởi acceptance này.

Xem [bàn giao vận hành](runbooks/current-stack-production.md), [runbook đăng ký công khai](runbooks/public-registration.md), [lịch định kỳ](runbooks/scheduled-notifications.md) và [quy trình release](production-rollout.md). Không đưa state/tfvars, artifact riêng, token/key, email subscriber riêng hoặc DOCX hướng dẫn tuần vào Git.
