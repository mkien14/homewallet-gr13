# Tình trạng nghiệm thu phần việc Chi — 09/11/2026

Kiểm tra từ mã đã merge tới `origin/main` commit `22542ab` và các API đọc AWS
bằng IAM user `kien`, account `179923444714`. Region mặc định
`ap-southeast-1`; WAF CloudFront được kiểm tra ở `us-east-1`.

| Việc | Kết luận hiện tại | Bằng chứng và giới hạn |
| --- | --- | --- |
| #29 Cognito admin group | Đã triển khai | Pool có group `homewallet-dev-admins` và một user enabled. Kiểm thử quyền API D2 thuộc phần Hoàng/Kiên. |
| #31 WAF CloudFront | Đã triển khai ở `COUNT`; nghiệm thu luồng còn thiếu | CloudFront distribution `E1FBDSJYV9WAKM` gắn Web ACL `homewallet-dev-cloudfront`. ACL mặc định `ALLOW`, chỉ có `AWSManagedRulesCommonRuleSet` với override `COUNT`. GET `/` và `/api/ping` trực tiếp qua CloudFront đều HTTP 200; CloudWatch có AllowedRequests; ảnh UI ngày 09/11 ghi `/api/me`, receipt và ảnh hoạt động. Chưa có biên bản riêng cho upload mới và callback Cognito hợp lệ sau khi gắn WAF. Logging và sampled requests chưa bật, nên chưa có bằng chứng theo request để đánh giá false positive. Giữ `COUNT` trong tuần 10. |
| #32 DB runtime least privilege | Kiên đã nghiệm thu phase 2 | Biên bản chạy trước đó xác nhận API, worker, jobs đọc runtime DB; task jobs probe kết thúc exit 0 với `RUNTIME_DB_READ_OK`, grants đã được DB admin kiểm tra. Rà soát thêm: RDS vẫn single-AZ, một NAT đang available, chỉ có S3 Gateway Endpoint, không có CloudTrail trail mới. RDS và S3 dùng khóa KMS do AWS quản lý; IAM worker giới hạn `kms:ViaService` qua S3. Không đổi mật khẩu, secret hoặc key trong lần rà này. |
| #33 Alarm/SNS/dashboard | Đạt phần giám sát | Xem [33-monitoring-kien-20261109.md](33-monitoring-kien-20261109.md). 8 alarm và 8 widget có mặt; email SNS test đã nhận. DLQ còn một receipt cũ `FAILED`, theo dõi riêng. |
| #42 Cognito SRP/Custom Message | Cấu hình dev đã apply; SRP, quyền locale và Lambda smoke đạt; chưa nghiệm thu email thật | Pool dùng SES `DEVELOPER`, có `custom:preferred_locale`, Custom Message Lambda `Active`; invoke permission giới hạn đúng pool. SPA client còn `ALLOW_USER_SRP_AUTH`, refresh và OAuth code/PKCE cùng callback localhost/CloudFront. SES sender đã verified nhưng account vẫn sandbox. Gọi trực tiếp Lambda với placeholder giả lúc khoảng 10:45 +07 đạt 4/4 ca signup/forgot vi/en, HTTP 200, đúng subject và giữ placeholder. Một user giả tạo bằng `AdminCreateUser` với `MessageAction=SUPPRESS` đăng nhập SPA client bằng SRP, ghi rồi đọc lại `custom:preferred_locale=en` thành công; user đã được xóa ngay sau ca. Chưa có bằng chứng Cognito trigger hoặc email thật tới recipient đã verified. |
| #43 Email Cognito theo locale | Chưa đạt end-to-end | Ma trận trong [43-cognito-email.md](43-cognito-email.md) còn `NOT_RUN`. Nhánh `feat/42-43-cognito-locale-sync` chuẩn bị gửi `custom:preferred_locale` lúc signup, đồng bộ Cognito với hồ sơ backend và thêm OAuth scope cho PKCE; chưa merge/deploy hoặc nghiệm thu email thật. Glossary vi/en đã được Kiên duyệt; xem [43-cognito-email.md](43-cognito-email.md). |
| #34 hỗ trợ Bedrock | Profile đọc được; kết quả gọi model chưa được chứng minh | Inference profile Nova Lite APAC đang `ACTIVE` và liệt kê 6 model đích. Bằng chứng này không thay thế một lần `InvokeModel` thành công sau sửa policy; Hoàng phụ trách benchmark và báo cáo D3. |

## Việc cần đóng tiếp

1. **#31:** Dùng tài khoản dev hiện có kiểm tra một upload hợp lệ và một vòng
   Hosted UI/PKCE callback sau WAF. Ghi thời gian, HTTP status, request ID đã
   che dữ liệu. Không chuyển rule sang `BLOCK` trong tuần 10.
2. **#42:** Review/merge thay đổi frontend gửi/đọc/ghi `custom:preferred_locale`
   trên `feat/42-43-cognito-locale-sync`, apply OAuth scope đã review rồi deploy.
   Sau khi có recipient SES-verified, Kiên/Chi chạy signup, resend, forgot/reset
   cho cả `vi` và `en`, xác minh code thật ngoài repo và rà log Lambda. Ghi
   kết quả từng ca vào ma trận #43; không coi cấu hình AWS là bằng chứng email.
3. **#43:** Dùng glossary vi/en đã duyệt và hoàn tất các ca email cùng phần
   jobs/reports/push/API/UI còn thiếu. Kiên chỉ cân nhắc đổi entrypoint auth sau khi các ca bắt buộc về
   SRP, refresh, TOTP, email và PKCE đều có kết quả.
4. **DLQ:** Receipt `id=1` đã `FAILED/WORKER_MAX_ATTEMPTS`. Đây là sự cố dữ
   liệu cũ, không phải lỗi cấu hình #33. Giữ bằng chứng; không redrive trực
   tiếp hoặc xóa message để làm alarm xanh. Chủ receipt/backend quyết định
   phục hồi hoặc đóng sự cố sau khi điều tra.

Giới hạn về chi phí: AWS Budgets đang có ngưỡng nhóm 50 USD/tháng. Giá trị
`Actual=0` từ API Budgets không chứng minh chi phí WAF/Lambda/SNS bằng 0; cần
đối chiếu Cost Explorer/hóa đơn theo kỳ riêng. Không mở thêm domain, Multi-AZ,
interface endpoint hoặc CloudTrail data events trong đợt này.
