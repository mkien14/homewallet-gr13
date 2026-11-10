# #43 — đề xuất gỡ chặn email Cognito (bản trước khi duyệt)

## Quyết định cần chốt

Biên bản `43-cognito-email.md` yêu cầu giữ SES sandbox của tài khoản dùng chung.
Ngày 10/11/2026, AWS vẫn báo `ProductionAccessEnabled=false` tại Singapore;
user pool hiện dùng `EmailSendingAccount=DEVELOPER`. Tạo thêm pool trong cùng
tài khoản/Region không thay đổi trạng thái SES của tài khoản/Region đó.

Đề xuất: duyệt gửi yêu cầu SES production access tại `ap-southeast-1`, account
`179923444714`, rồi kiểm tra Cognito trong một pool test riêng. Đây là thay đổi
quyết định sandbox trước đó và chỉ thực hiện sau khi người dùng chốt cụ thể.
AWS phải xét duyệt; gửi yêu cầu không đồng nghĩa được duyệt hoặc hoàn tất E2E.

Nội dung đề xuất gửi (cần người sở hữu xác nhận đúng trước khi nộp):

- Loại thư: TRANSACTIONAL.
- Website: https://daoedidcrnf1f.cloudfront.net.
- Mục đích: email xác minh đăng ký, gửi lại mã và đặt lại mật khẩu cho ứng dụng
  HomeWallet trong bài tập; kiểm tra tiếng Việt/Anh bằng tài khoản test riêng.
- Chỉ gửi tới các hộp thư test do nhóm kiểm soát trong đợt nghiệm thu.
- Không gửi marketing hoặc tới danh sách mua/thu thập từ bên ngoài.
- Không thay đổi pool/app client đang phục vụ frontend để chạy ca thử.
- Chỉ bắt đầu gửi khi AWS đã duyệt, hộp thư test được xác nhận, và kiểm tra
  xử lý bounce/complaint hiện có đã đủ cho phạm vi được duyệt.

## Phạm vi nghiệm thu sau duyệt

Tạo pool/client test riêng và bản Lambda Custom Message cùng mã nguồn hiện có;
chỉ cấp invoke permission cho pool test. Chạy signup/resend/confirm và forgot/
confirm reset cho `vi`, `en`; mã người dùng nhập được giữ trong bộ nhớ, không
đưa vào log hoặc bằng chứng. Rà log Lambda tương ứng cho CM14. CM15/16 chỉ dùng
tài khoản và địa chỉ test đã chọn. Dọn pool/client/permission test sau nghiệm thu.

Không dùng `COGNITO_DEFAULT` để đánh dấu PASS nội dung Custom Message hiện tại:
AWS yêu cầu `DEVELOPER` khi Lambda trả `emailSubject`/`emailMessage` tùy biến.

## Tài liệu AWS

- [Cognito email settings](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-email.html)
- [Custom Message trigger](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-custom-message.html)
- [SES production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html)

Cập nhật 10/11/2026: người dùng đã duyệt gửi request; AWS đã GRANTED, case
`179429386000476`. Bản đề xuất trên được giữ làm lịch sử quyết định. Trạng thái
hiện tại và bằng chứng nằm tại [43-delivery-20261110.md](43-delivery-20261110.md).
