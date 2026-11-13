# OCR production: bản sửa chuẩn bị candidate — 13/11/2026

**Chưa bật trên AWS.** Nhánh `fix/production-reconcile-gemini`; Kiên giữ quyền
commit/push/merge. Candidate phải build từ main sau khi merge, chọn input
`enable_ocr=true` của workflow Build release candidate.

## Thay đổi đã chuẩn bị

- Worker kiểm tra allowlist hộ (loại hộ 1), membership uploader, bucket/key và
  consent audit đúng receipt/uploader trước đổi trạng thái hoặc đọc ảnh.
- Chỉ nhận prefix `receipts/production/` qua queue `production-ocr-queue` mới;
  notification/queue/DLQ cũ được giữ. Production consumer từ chối URL queue cũ.
- Khóa DB theo receipt chống xử lý song song. Named lock toàn provider và audit
  bền vững giới hạn 10 lần gọi/ngày UTC, cách nhau ít nhất 30 giây, tối đa hai
  lần/receipt, tính cả retry. Giới hạn output 4096 token. DB/quota lỗi thì dừng
  trước gọi provider; đây là giới hạn app, không phải xác nhận quota Google.
- Nhánh local CLI production bị chặn; nhánh đánh FAILED cũng kiểm tra policy.
- Terraform có cờ OCR mặc định false, yêu cầu rotation đã xác nhận. Chỉ worker
  nhận Gemini key; API không mở AI gợi ý ngân sách. Textract fallback tắt.
  Queue riêng được giữ cả khi tắt feature để rollback không xóa thông điệp.
- Candidate có input OCR tường minh; checksum/manifest và image security gate
  được giữ. Publisher đối chiếu feature profile với API đang chạy.

## Kiểm tra đã chạy

- Worker/policy/recovery unit tests: **37 PASS** sau sửa một test dùng timestamp
  tạo quá sớm khi collect; không bỏ assertion.
- Script tests: **27 PASS**. Frontend lint PASS. Terraform fmt/validate PASS.
- `gemini-3.6-flash`: hai lần gọi ảnh tổng hợp đều trả 503 high demand. Không bật
  model này dựa vào metadata GET thành công.
- `gemini-3.5-flash-lite`: một lần đọc cùng ảnh tổng hợp **PASS**, đúng cửa hàng,
  ngày, tổng 78000 VND và hai dòng 33000/45000. Không gửi ảnh của hộ thật.
  [Bằng chứng](gemini-flash-lite-smoke-20261113.json).

## Cổng còn phải đạt

CI/candidate scan; saved plan không thay DB/network/service; nghiệm thu trên
candidate mới upload-consent → S3 → queue riêng → worker → DRAFT, từ chối hộ/
consent sai, quota/retry/idempotency và stop/rollback. Preflight production vẫn
đòi bằng chứng resilience đúng release/image. Không đổi flag attestation để
vượt cổng. Chỉ sau đủ bằng chứng mới đặt `ocr_benchmark_accepted=true` và publish.

Chọn `gemini-3.5-flash-lite` cho canary tiếp theo vì smoke ảnh đã đạt trong khi
3.6 đang quá tải; chưa coi một ảnh là benchmark chất lượng rộng hoặc SLA.
