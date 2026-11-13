# Chốt phạm vi phát hành và bàn giao — 13/11/2026

Người chốt: Kiên, admin dự án. Nhánh: `fix/production-integration`.

## Quyết định đã nhận

- Cảnh báo AWS **100 USD/tháng**, không phải hard cap. Giữ budget nhóm 50 USD
  và zero-spend budget hiện có; thêm `HomeWallet-Production-Monthly`, cảnh báo
  actual 50/80/100% và forecast 100%. Chưa apply hoặc gửi notification.
- Phạm vi hộ: theo trả lời cuối của Kiên, các hộ hiện có **trừ household 1**.
  Trước apply phải chụp danh sách ID chỉ đọc, cố định vào allowlist và settings.
  Không tự cho hộ tương lai vào. Danh tính chưa thuộc hộ được duyệt bị chặn;
  Cognito/React không mở tự đăng ký ở profile production. Onboarding admin là
  thao tác riêng có review. Không đổi dữ liệu, ảnh hoặc DLQ của household 1.
- TOTP của từng tài khoản admin do chủ tài khoản nhập trên thiết bị của mình.
  Không thu thập mật khẩu, shared secret hoặc OTP trong chat. Enrollment và
  preferred TOTP được đọc lại bằng metadata; challenge đăng nhập lại cần chủ
  tài khoản xác nhận thực tế.
- Kiên xác nhận Chi **chưa có** biên bản áp dụng lên stack đang chạy và kết quả
  restore/rollback. `resilience_signoff=false`, không đổi để chạy qua gate.
- Kiên tự commit/push/merge. Triển khai dùng candidate từ đúng commit main được
  review; không dùng image working-tree hoặc workflow stack prod riêng.

## Đã chuẩn bị và kiểm tra trước commit

- 5 GitHub Repository Variables công khai đã được cấu hình và đọc lại bằng API.
  Không lưu private key/token vào variables. Public VAPID khớp bản frontend
  đang chạy; sao lưu cấu hình trước chỉnh sửa nằm ngoài Git trong thư mục tạm.
- Backend targeted tests: **25 pass**, gồm auth, health và 8 ca policy hộ; không
  kết nối/truncate DB thật. Production release script tests: **9 pass**.
- Frontend: **96 pass**, lint PASS; build bằng profile production (real API,
  SRP, OCR off, self-signup off): PASS. Chưa thay website đang chạy.
- Terraform mock tests dev: **1 pass**, prod riêng: **3 pass**; validate cả hai
  root PASS. Mock không nghiệm thu hạ tầng AWS thật. Không apply.
- Đây là kiểm tra working tree trên máy hiện tại; CI/candidate Linux Python 3.12
  từ commit main vẫn phải chạy sau merge. Bằng chứng container trước đó nằm
  trong `container-security-20261113.*`; source policy hộ mới phải build/quét
  lại trong candidate, không suy diễn report cũ là report của commit chưa có.

## Bàn giao triển khai cho Kiên

| Phần | Người thực hiện | Bằng chứng phải có |
| --- | --- | --- |
| Source | Kiên | PR đã review/merge, SHA main, CI xanh |
| Candidate | Agent theo ủy quyền của Kiên | Workflow run, artifact cùng SHA, integrity/security/compatibility acceptance |
| MFA | Từng admin; agent đọc lại metadata | Preferred TOTP và challenge khi đăng nhập lại |
| Budget/scope | Agent sau candidate | Saved plan, recipient vận hành đã duyệt, snapshot household ID trừ 1 |
| HTTPS | Agent sau candidate | Tạo gateway/VPC Link; canary hợp lệ và chặn bypass; cutover riêng |
| WAF/profile | Agent sau review traffic | False-positive review, BLOCK đúng phạm vi, API/worker/jobs cùng release |
| HA/restore/rollback | Chi, Kiên nhận bàn giao | Biên bản đúng stack hiện có; không chỉ code `infra/envs/prod` |
| Mở production | Kiên | Gate cuối GO và nghiệm thu UI/data/tenant; không còn sign-off bỏ trống |

## Phần cần Chi hoàn tất trước mở production

Đối chiếu stack `homewallet`/RDS `homewallet-dev-mysql`/CloudFront hiện tại:
Multi-AZ và ngân sách thực tế; backup, deletion protection, retention log;
health/scaling; diễn tập restore DB riêng tư được cô lập với RPO/RTO đo được;
rollback revision tương thích migration 006 và kiểm tra ứng dụng sau phục hồi.
Không bật autoscaling bằng cách làm Terraform replace ECS service do thay
address `api[0]`/`api_scaled[0]` hoặc `worker[0]`/`worker_release[0]`; cần review
state move riêng. Không xóa bản giữ phục hồi hay replay DLQ trong bàn giao này.

Có thể chuẩn bị HTTPS origin và budget trong lúc chờ bàn giao. Chưa được kết
luận sản phẩm production hoàn thiện hoặc mở traffic production khi gate này
vẫn chưa đạt. Tài liệu này ghi trách nhiệm và bằng chứng còn thiếu, không phải
biên bản nghiệm thu thay cho Chi.
