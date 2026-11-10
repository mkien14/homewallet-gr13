# Tình trạng nghiệm thu phần việc Chi — 09/11/2026

Kiểm tra từ mã đã merge tới `origin/main` commit `22542ab`, các API đọc AWS
bằng IAM user `kien`, account `179923444714`, và bằng chứng nghiệm thu do Kiên
cung cấp. Region mặc định
`ap-southeast-1`; WAF CloudFront được kiểm tra ở `us-east-1`.

| Việc | Kết luận hiện tại | Bằng chứng và giới hạn |
| --- | --- | --- |
| #29 Cognito admin group | Đã triển khai | Pool có group `homewallet-dev-admins` và một user enabled. Kiểm thử quyền API D2 thuộc phần Hoàng/Kiên. |
| #31 WAF CloudFront | Đã nghiệm thu hoàn toàn trong phạm vi tuần 10 | CloudFront distribution `E1FBDSJYV9WAKM` gắn Web ACL `homewallet-dev-cloudfront`. ACL mặc định `ALLOW`, `AWSManagedRulesCommonRuleSet` chạy `COUNT` theo cấu hình đã duyệt. GET `/` và `/api/ping` qua CloudFront đều HTTP 200; CloudWatch có AllowedRequests; ảnh UI ngày 09/11 ghi `/api/me`, receipt và ảnh hoạt động. Kiên xác nhận đã cung cấp đầy đủ bằng chứng nghiệm thu #31 trước đó. Tiếp tục giữ `COUNT` theo quyết định tuần 10; không còn việc #31 cho Chi. |
| #32 DB runtime least privilege | Kiên đã nghiệm thu phase 2 | Biên bản chạy trước đó xác nhận API, worker, jobs đọc runtime DB; task jobs probe kết thúc exit 0 với `RUNTIME_DB_READ_OK`, grants đã được DB admin kiểm tra. Rà soát thêm: RDS vẫn single-AZ, một NAT đang available, chỉ có S3 Gateway Endpoint, không có CloudTrail trail mới. RDS và S3 dùng khóa KMS do AWS quản lý; IAM worker giới hạn `kms:ViaService` qua S3. Không đổi mật khẩu, secret hoặc key trong lần rà này. |
| #33 Alarm/SNS/dashboard | Đạt phần giám sát | Xem [33-monitoring-kien-20261109.md](33-monitoring-kien-20261109.md). 8 alarm và 8 widget có mặt; email SNS test đã nhận. DLQ còn một receipt cũ `FAILED`, theo dõi riêng. |
| #42 Cognito locale sync | Đã nghiệm thu cho Hosted UI/PKCE locale sync; email thật chưa nằm trong kết quả | User đã đăng nhập lại qua Hosted UI/PKCE sau khi apply scope. Ảnh DevTools ngày 09/11 cho thấy Cognito `UpdateUserAttributes` trả HTTP 200 khi đổi `en` và `vi`, còn `/api/me` trả đúng `preferred_locale` ở cả hai locale. Giữ bằng chứng dạng tóm tắt; không commit ảnh gốc vì ảnh chứa email/mã mời. SES pool vẫn `DEVELOPER`, SES production access GRANTED on 2026-11-10 under the user-approved decision change. |
| #43 Cognito email and locale | PARTIAL; SES sandbox block removed, controlled inbox/code evidence pending | CM10/11/12 PASS; CM13 N/A approved; CM14 PASS for the controlled email-trigger window (11 invocations, 33 lifecycle-only log lines). User approved SES production access; AWS GRANTED, case 179429386000476. Isolated pool prepared; signup/resend/forgot/fallback/locale-change/invitation requests accepted with labeled SES simulator addresses; six temporary users deleted. Received content/codes remain PARTIAL; CM16 needs a second controlled address. Browser notification 41 read/click and reload persistence PASS, PATCH 200/read=true, request ID 9389bdb0-83bc-40ee-b129-1e3bbf92de34. Existing API fixture 20/20 and six jobs/reports checks PASS. Three one-time Scheduler schedules ran unmodified hw-jobs:3 CLIs on two isolated schemas: all three jobs succeeded in vi/en, six SES simulator sends completed, four pushes provider-accepted; repeated claims skipped. Temporary schedules, schemas and schema grants removed; original schedules DISABLED. Job-push send/receive smoke PASS from user confirmation for the 14:08-14:10 Asia/Bangkok window on 2026-11-10; not every individual push was separately observed. See [delivery and remaining manual steps](43-delivery-20261110.md), [matrix](43-cognito-email.md). |
| #34 hỗ trợ Bedrock | Profile đọc được; kết quả gọi model chưa được chứng minh | Inference profile Nova Lite APAC đang `ACTIVE` và liệt kê 6 model đích. Bằng chứng này không thay thế một lần `InvokeModel` thành công sau sửa policy; Hoàng phụ trách benchmark và báo cáo D3. |

## Việc cần đóng tiếp

1. **#31:** Fully accepted per user confirmation; closed.
2. **#42:** Đã nghiệm thu live locale sync cho Hosted UI/PKCE bằng chứng
   `UpdateUserAttributes=200` và `/api/me` `en/vi`. Ghi trạng thái vào PR/artifact;
   không đưa email, token, mã mời hoặc ảnh chưa che dữ liệu vào Git.
3. **#43:** SES production access đã được người dùng duyệt và AWS GRANTED.
   Ca Scheduler/CLI/provider đã PASS và được dọn. Dùng pool test riêng để hoàn
   tất nhận email/nội dung/mã. Nhận push từ job đã được người dùng xác nhận
   trong khoảng 14:08–14:10 ngày 10/11/2026, PASS trong phạm vi smoke.
   Xem [hướng dẫn phần còn lại](43-delivery-20261110.md). Auth cutover cần review riêng.
4. **DLQ:** Receipt `id=1` đã `FAILED/WORKER_MAX_ATTEMPTS`. Đây là sự cố dữ
   liệu cũ, không phải lỗi cấu hình #33. Giữ bằng chứng; không redrive trực
   tiếp hoặc xóa message để làm alarm xanh. Chủ receipt/backend quyết định
   phục hồi hoặc đóng sự cố sau khi điều tra.

Giới hạn về chi phí: AWS Budgets đang có ngưỡng nhóm 50 USD/tháng. Giá trị
`Actual=0` từ API Budgets không chứng minh chi phí WAF/Lambda/SNS bằng 0; cần
đối chiếu Cost Explorer/hóa đơn theo kỳ riêng. Không mở thêm domain, Multi-AZ,
interface endpoint hoặc CloudTrail data events trong đợt này.
