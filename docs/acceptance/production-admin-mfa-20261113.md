# Nghiệm thu MFA admin HomeWallet — 13/11/2026

## Xác nhận thực tế

Kiên xác nhận trong phiên làm việc: đã bật MFA, đăng xuất, đăng nhập lại được
hỏi mã TOTP và nhập mã đăng nhập thành công. Đây là xác nhận thao tác của chủ
tài khoản; agent không thu thập mật khẩu, setup key, mã OTP hoặc token.

## Đối chiếu metadata chỉ đọc

- AWS account: `179923444714`, Region: `ap-southeast-1`.
- Cognito pool: `ap-southeast-1_9mOMUx9Ds`.
- Group: `homewallet-dev-admins`.
- Có **1 admin đang enabled** trong group tại thời điểm kiểm tra.
- Admin đó có `SOFTWARE_TOKEN_MFA` trong danh sách MFA và đặt phương thức này
  làm preferred. Không lưu username, email hoặc Cognito subject vào biên bản.

Ghi nhận bước MFA hiện tại đã đạt theo xác nhận của Kiên và metadata trên.
Khi thêm hoặc bật lại admin khác, phải kiểm tra enrollment, preferred TOTP và
đăng nhập có challenge cho người đó trước khi nghiệm thu lại.

## Phạm vi kết luận

Đây là MFA cho tài khoản ứng dụng HomeWallet, không chứng minh IAM/root AWS MFA.
Settings vận hành ngoài Git đã ghi nhận xác nhận challenge; file example giữ
giá trị mặc định `false`. Các gate HTTPS/WAF/profile production, phạm vi hộ và
HA/restore/rollback vẫn phải nghiệm thu riêng.

## Candidate sau merge

PR #104 đã merge vào main `df40bd1a3c838cbf7a6ff1e587c72d84a1a6b60c`.
Các check CI của commit này đã thành công khi kiểm tra. Agent đã dispatch
workflow `Build release candidate` từ main; dispatch không phải bằng chứng
candidate đã build hoặc scan thành công và không thực hiện deploy AWS.
