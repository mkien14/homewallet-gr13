# Tình trạng nghiệm thu phần việc Chi — 09/11/2026

Cập nhật rà soát 10/11: xem [việc nhóm còn lại](team-open-work-20261110.md)
và [khắc phục #34](34-bedrock-remediation-20261110.md).

Kiểm tra từ mã đã merge tới `origin/main` commit `22542ab`, các API đọc AWS
bằng IAM user `kien`, account `179923444714`, và bằng chứng nghiệm thu do Kiên
cung cấp. Region mặc định
`ap-southeast-1`; WAF CloudFront được kiểm tra ở `us-east-1`.

| Việc | Kết luận hiện tại | Bằng chứng và giới hạn |
| --- | --- | --- |
| #29 Cognito admin group / D2 | CLOSED / PASS theo Kiên ngày 10/11 | Group đã triển khai; Kiên xác nhận nghiệm thu runtime hoàn toàn và lưu evidence riêng. Xem [biên bản cuối](29-final-acceptance-20261110.md); không mở lại vì repo không chứa artifact riêng. |
| #31 WAF CloudFront | Đã nghiệm thu hoàn toàn trong phạm vi tuần 10 | CloudFront distribution `E1FBDSJYV9WAKM` gắn Web ACL `homewallet-dev-cloudfront`. ACL mặc định `ALLOW`, `AWSManagedRulesCommonRuleSet` chạy `COUNT` theo cấu hình đã duyệt. GET `/` và `/api/ping` qua CloudFront đều HTTP 200; CloudWatch có AllowedRequests; ảnh UI ngày 09/11 ghi `/api/me`, receipt và ảnh hoạt động. Kiên xác nhận đã cung cấp đầy đủ bằng chứng nghiệm thu #31 trước đó. Tiếp tục giữ `COUNT` theo quyết định tuần 10; không còn việc #31 cho Chi. |
| #32 DB runtime least privilege | Kiên đã nghiệm thu phase 2 | Biên bản chạy trước đó xác nhận API, worker, jobs đọc runtime DB; task jobs probe kết thúc exit 0 với `RUNTIME_DB_READ_OK`, grants đã được DB admin kiểm tra. Rà soát thêm: RDS vẫn single-AZ, một NAT đang available, chỉ có S3 Gateway Endpoint, không có CloudTrail trail mới. RDS và S3 dùng khóa KMS do AWS quản lý; IAM worker giới hạn `kms:ViaService` qua S3. Không đổi mật khẩu, secret hoặc key trong lần rà này. |
| #33 Alarm/SNS/dashboard | Đạt phần giám sát | Xem [33-monitoring-kien-20261109.md](33-monitoring-kien-20261109.md). 8 alarm và 8 widget có mặt; email SNS test đã nhận. DLQ còn một receipt cũ `FAILED`, theo dõi riêng. |
| #42 Cognito locale sync | Đã nghiệm thu cho Hosted UI/PKCE locale sync; email thật chưa nằm trong kết quả | User đã đăng nhập lại qua Hosted UI/PKCE sau khi apply scope. Ảnh DevTools ngày 09/11 cho thấy Cognito `UpdateUserAttributes` trả HTTP 200 khi đổi `en` và `vi`, còn `/api/me` trả đúng `preferred_locale` ở cả hai locale. Giữ bằng chứng dạng tóm tắt; không commit ảnh gốc vì ảnh chứa email/mã mời. SES pool vẫn `DEVELOPER`, SES production access GRANTED on 2026-11-10 under the user-approved decision change. |
| #43 Cognito email and locale | PASS within agreed acceptance scope | CM01-12 and CM14-16 PASS; CM13 user-approved N/A. Controlled mailbox run 2e1a13cdc88d completed 2026-11-10 14:52:45-14:59:53 Asia/Bangkok: localized content operator-confirmed, signup/resend/reset codes succeed, invitation temporary-password challenges and changed-email verification pass in vi/en; 47 API calls HTTP 200, seven temporary users deleted. CM14: 14 Lambda invocations, 42 lifecycle lines, zero application payload lines. SES production access GRANTED, case 179429386000476. Test pool/client and scoped Lambda permission removed and verified. Browser notification 41 read/reload PASS; prior API fixture 20/20 and six jobs/reports checks PASS. Three one-time Scheduler jobs passed in vi/en, six SES simulator sends completed and four pushes provider-accepted; repeats skipped. User confirmed receipt of a new job notification in the 14:08-14:10 window. Test schedules/schemas/grants removed; original recurring schedules DISABLED. Job email evidence is to SES simulator, distinct from actual Cognito mailbox E2E. See [final acceptance](43-final-acceptance-20261110.md). |
| #34 hỗ trợ Bedrock | Nguyên nhân AccessDenied đã xác định; preflight đã sửa, benchmark vẫn PARTIAL | CloudTrail chứng minh guard D1 v3 chặn Sydney; current v4 đã miễn trừ InvokeModel. Mô phỏng IAM Hoàng 7/7 allow, negative controls deny. Một Converse văn bản bằng Kiên trả 200; chưa có runtime bằng Hoàng hoặc paired OCR. Xem [chi tiết và hướng hoàn tất](34-bedrock-remediation-20261110.md). |

## Việc cần đóng tiếp

1. **#31:** Fully accepted per user confirmation; closed.
2. **#42:** Đã nghiệm thu live locale sync cho Hosted UI/PKCE bằng chứng
   `UpdateUserAttributes=200` và `/api/me` `en/vi`. Ghi trạng thái vào PR/artifact;
   không đưa email, token, mã mời hoặc ảnh chưa che dữ liệu vào Git.
3. **#43:** Đã nghiệm thu trong phạm vi đã chốt: CM01–12 và CM14–16 PASS;
   CM13 N/A được duyệt. Email qua hộp thư thật và job-push nhận trên thiết bị
   có bằng chứng. Pool test, client và permission riêng đã dọn.
   Xem [biên bản cuối](43-final-acceptance-20261110.md). Auth cutover là thay đổi riêng.
4. **DLQ:** Kiên chọn giữ receipt `id=1` và phục hồi có kiểm soát. DB/S3 inspection
   xác nhận ảnh gốc còn, không có transaction. Công cụ một receipt/một generation
   attempt đã có 26 tests PASS. Lần thử trả provider `ServerError`; rollback và
   postcheck xác nhận dữ liệu không đổi, transaction vẫn 0, DLQ vẫn 1 visible.
   Phục hồi còn chờ provider; không redrive/xóa message. Xem
   [quy trình và kết quả](33-receipt1-recovery-20261110.md).

Giới hạn về chi phí: AWS Budgets đang có ngưỡng nhóm 50 USD/tháng. Giá trị
`Actual=0` từ API Budgets không chứng minh chi phí WAF/Lambda/SNS bằng 0; cần
đối chiếu Cost Explorer/hóa đơn theo kỳ riêng. Không mở thêm domain, Multi-AZ,
interface endpoint hoặc CloudTrail data events trong đợt này.
