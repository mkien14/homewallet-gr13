# Mở production cho người dùng mới

Quyết định của admin: cho phép mọi người tự đăng ký, xác minh email, rồi tạo hoặc tham gia hộ. Hộ 1 và ảnh/queue/DLQ cũ tiếp tục giữ riêng. Quyền admin không được cấp qua đăng ký. Membership vẫn là ranh giới dữ liệu.

## Trạng thái

Bản sửa trên `fix/auth-registration-and-challenges` đã kiểm tra cục bộ. Chưa commit, merge, build candidate hoặc triển khai AWS; không dùng biên bản của release cũ để kết luận public onboarding đã PASS.

- Frontend: lint, build và 102 ca test đạt.
- Backend: 63 ca phạm vi sửa đạt; 98 ca của nhóm kiểm tra MySQL/auth/community/history đạt trên MySQL 8.4 cục bộ riêng, gồm public onboarding; không ghi vào RDS.
- Công cụ triển khai: 27 ca hiện có đạt. Terraform dev/prod validate đạt.
- Browser cục bộ, Cognito SDK giả lập: đăng ký → xác minh/gửi lại mã; TOTP trong phiên đăng nhập; MFA chỉ hiện lựa chọn server trả về; reset; quay lại; tiếng Anh. Không phải bằng chứng email/TOTP thật trên AWS.

## Phát hành sau merge

1. Build release candidate từ main đã merge, chọn `public_registration=true`, `enable_ocr=true`. Chờ CI và security scan đạt; lấy đúng artifact của SHA đó.
2. Sao lưu operator settings và tfvars đang dùng. Trong bản chuẩn bị của **stack hiện hữu `infra/envs/dev`**, đặt `production_public_registration=true`; cập nhật `release_commit` và `release_image_digest` từ candidate mới. Giữ nguyên các thông số hạ tầng, secret, consent, quota và lịch hiện hành. Danh sách hộ cũ có thể giữ làm tham chiếu nhưng không giới hạn chế độ công khai.
3. Trong operator settings của bản phát hành đặt `public_registration_enabled=true`, `household_scope_rule=public_except_retained_1` và SHA/digest tương ứng. Không dùng nguyên file example làm cấu hình live.
4. Terraform plan phải chỉ có thay đổi đã review: Cognito cho self-signup và task definitions cho cùng image/release/cờ public. Dừng nếu định thay thế DB, bucket hoặc User Pool. Không apply stack prod thứ hai.
5. Apply saved plan; chuyển API, worker và ba target Scheduler sang revision mới. Đợi service ổn định. Hộ mới được API admit khi chưa có membership; join hộ 1 bị chặn trước INSERT. Worker kiểm hộ/membership/key/consent. Cả ba job lọc SQL `household_id > 1`.
6. Chạy `production-preflight.py` với settings mới. Gate đối chiếu API/worker/jobs và Cognito email verification/self-signup. Publisher kiểm cờ đăng ký của artifact khớp API trước upload. Publish frontend từ cùng candidate, chờ invalidation, kiểm SHA ở `/release.json` và `/api/release`.
7. Dùng hộp thư được phép đọc để tự đăng ký, nhập mã email thật, đăng nhập SRP, tạo hộ, mời tài khoản thứ hai, kiểm tra member/owner và từ chối truy cập chéo hộ. Kiểm reset thật, admin TOTP và fallback PKCE. Kiểm receipt mới theo consent/quota và phạm vi job; không replay dữ liệu giữ riêng.
8. Ghi bằng chứng runtime đúng SHA, kết quả/thời điểm và cleanup; khi đủ mới đổi trạng thái trong báo cáo thành đã triển khai/đã nghiệm thu. Không gửi mật khẩu, token, OTP hoặc setup key lên Git.

## Quay lại chế độ đóng

Tắt self-signup và frontend đăng ký; runtime public=false với allowlist được review. **Không rollback mù về danh sách 16 hộ cũ sau khi đã có người dùng mới**: phải quyết định rõ các hộ mới cần tiếp tục phục vụ và đưa vào danh sách trước khi chuyển. Không xóa tài khoản/hộ/dữ liệu khi rollback. Artifact của frontend và runtime phải khớp chính sách.

Các bản sửa xác thực kèm theo: TOTP sign-in dùng `nextStep.totpSetupDetails` và `confirmSignIn`, không gọi API MFA đòi phiên đã đăng nhập; challenge không hỗ trợ có thông báo và fallback; khóa email trong challenge; xóa password/code khi đổi bước; chặn submit trùng và xử lý lỗi fallback; loại token lưu trình duyệt sai cấu trúc/hết hạn.

Tham chiếu SDK: https://docs.amplify.aws/react/frontend/auth/multi-step-sign-in/
