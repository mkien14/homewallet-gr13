# #43 — nghiệm thu cuối ngày 10/11/2026

## Kết luận

**PASS trong phạm vi nghiệm thu #43 đã chốt.** CM01–12 và CM14–16 PASS;
CM13 N/A theo cấu hình MFA và quyết định của người dùng trước đó.
Người dùng hoàn tất kiểm tra hộp thư thật, nội dung vi/en và nhập mã tại terminal.
Không còn blocker SES sandbox hoặc ca email chờ mã trong ma trận này.

## Email E2E qua hộp thư kiểm soát được

- Run `2e1a13cdc88d`, từ `2026-11-10T07:52:45Z` đến `07:59:53Z`, tương ứng
  **14:52:45–14:59:53 Asia/Bangkok**.
- Kết quả `COMPLETED_INTERACTIVE_CORE_CASES`; 47 API calls đều HTTP 200 và có
  AWS request ID. Bảy tài khoản test tạo riêng đã được xóa; `cleanup=PASS`.
- Người dùng kiểm tra nội dung thư ở các prompt tương tác trước khi xác nhận.
  Signup/resend được xác nhận bằng mã trong thư; reset kiểm tra đăng nhập bằng
  mật khẩu mới; lời mời hoàn thành challenge đổi mật khẩu; email đổi được xác
  minh và đọc lại `email_verified=true`.
- Log CM14 trong cửa sổ này: 14 invocation, 42 dòng vòng đời Lambda,
  `application_lines=0`. Không ghi mã, mật khẩu, token hoặc nội dung email vào
  artifact. Lambda dùng chung nên không suy diễn từng dòng log là một loại
  trigger cụ thể.

| Ca | Bằng chứng cuối | Kết luận |
| --- | --- | --- |
| CM01/02 signup vi/en | ConfirmSignUp + đăng nhập HTTP 200 | PASS |
| CM03/04 resend vi/en | Mã mới ConfirmSignUp + đăng nhập HTTP 200 | PASS |
| CM05/06 reset vi/en | ConfirmForgotPassword + đăng nhập bằng mật khẩu mới HTTP 200 | PASS |
| CM07 thiếu locale | Người dùng xác nhận nội dung tiếng Việt, xác minh và đăng nhập | PASS |
| CM08/09 đổi locale | Nội dung thư theo locale mới, mã reset và đăng nhập; phần đồng bộ hai store đã có bằng chứng live trước đó | PASS |
| CM10 lỗi đồng bộ/retry | Bằng chứng browser 09/11 trong ma trận | PASS |
| CM11 refresh/session | Refresh sau 60 phút và GET /api/me 200 đã ghi nhận trước đó | PASS |
| CM12 PKCE | Fresh login/callback đã nghiệm thu | PASS |
| CM13 TOTP | N/A được người dùng duyệt, pool OPTIONAL chưa cấu hình software token | N/A |
| CM14 log | 14 invocation, 42 lifecycle lines, không có application payload | PASS |
| CM15 lời mời | Cả vi/en: mật khẩu tạm, NEW_PASSWORD_REQUIRED và đăng nhập | PASS |
| CM16 đổi email | Cả vi/en: VerifyUserAttribute, GetUser xác nhận email mới | PASS |

Artifact đầy đủ: [43-cognito-mailbox-20261110.json](43-cognito-mailbox-20261110.json).

## API/UI/jobs/reports/push

- API thông báo và các ca profile/locale/household đã ghi nhận: 20/20; UI đánh
  dấu đã đọc thông báo `41` và tải lại giữ trạng thái PASS.
- Logic jobs/reports trên fixture tổng hợp: sáu kiểm tra PASS.
- Ba lịch Scheduler một lần chạy CLI `hw-jobs:3`: cả vi/en SUCCEEDED, sáu
  email gửi qua SES tới success simulator, bốn push được provider chấp nhận.
  Chạy lại cùng job key bỏ qua, không gửi trùng.
- Người dùng xác nhận nhận thông báo mới từ job trong khoảng 14:08–14:10
  Asia/Bangkok ngày 10/11: send/receive smoke PASS; không khẳng định cả bốn
  lần gửi đã được quan sát riêng.

Phạm vi: email nhận và xác nhận mã thật trong báo cáo này thuộc các luồng
Cognito. Email jobs/reports được nghiệm thu tới SES simulator cùng kết quả
render/logic riêng, không tuyên bố đã đọc báo cáo job trong hộp thư thật.
Ba lịch định kỳ gốc vẫn DISABLED theo cấu hình đã chốt; ca một lần đã dọn.
Auth cutover hoặc bật lịch định kỳ là thay đổi triển khai riêng.

## Dọn tài nguyên

Sau khi script dọn đủ bảy user, kiểm tra AWS xác nhận pool test trống. Đã xóa
pool/client test `ap-southeast-1_Hm6fFrq0M` và permission Lambda có SID
`chi43-email-e2e-5fc232b06155`, chỉ áp dụng cho ARN pool test đó. Đã xác nhận
pool test không còn và permission đã được gỡ. Pool ứng dụng hiện hành được giữ.

Chi tiết: [43-email-e2e-cleanup-20261110.json](43-email-e2e-cleanup-20261110.json).
SES production access vẫn GRANTED theo phê duyệt của người dùng.

Các file `.docx` hướng dẫn công việc tuần chỉ lưu trên máy, đã được Git ignore
và không nằm trong lịch sử commit chuẩn bị push.
