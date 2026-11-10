# Bước cuối #37 — nhận một email budget alert thật

Phần API, LLM/fallback, ngưỡng và chống trùng đã đạt; xem
[biên bản](25-37-budget-20261110.md). Bước này chỉ cần người có thể đọc hộp thư.

## Chuẩn bị

Mở PowerShell tại `homewallet-gr13`. Dùng phiên AWS của Kiên ở account dev
`179923444714`. Backend virtualenv phải có các dependency hiện dùng. Nếu chạy
trên máy khác, tạo môi trường và cài `backend/requirements-dev.txt` trước.

```powershell
aws sts get-caller-identity --query Arn --output text
```

Không gửi access key, secret, mật khẩu hoặc token vào chat. Dùng hộp thư nhóm
nếu bạn đọc được, hoặc hộp thư test của chính bạn.

## Chạy một lần

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\run-budget-mailbox-acceptance.py `
  --output .\docs\acceptance\37-mailbox-20261110.json
```

1. Tại `Email you can read (hidden):`, nhập địa chỉ bạn đọc được rồi Enter.
   Ký tự không hiện trên terminal là bình thường.
2. Công cụ tạo **schema test riêng**, một người nhận, một ngân sách và chi tiêu
   tổng hợp đúng 80%. Nó dùng `hw-jobs:3` và CLI ngân sách hiện có. Không chạy
   job trên các hộ đang dùng ứng dụng và không bật lịch định kỳ.
3. Chờ ba giai đoạn dựng/gửi/dọn; mỗi task Fargate có thể mất khoảng một phút.
   CLI gửi được chạy lần đầu rồi lặp cùng command/period_key; lần hai phải
   SKIPPED. Không đăng ký subscription push trong schema này.
4. Khi terminal in `D1 Acceptance <6 ký tự>`, mở Inbox/Spam của hộp thư vừa nhập.
   Chỉ kiểm tra thư **mới** có đúng chuỗi đó trong tiêu đề.
5. Kiểm tra tiêu đề **Cảnh báo ngân sách 80%**, category mang chuỗi nhận diện
   trên, nội dung tiếng Việt và hướng dẫn mở HomeWallet. Đây là dữ liệu giả.
6. Chỉ nhập **`y`** khi đã nhận và đọc đúng thư. Nếu chưa thấy hoặc nội dung sai,
   nhập `n`; không ghi nhận PASS thay cho việc đọc thư thật.
7. Chờ cleanup kết thúc rồi kiểm tra:

```powershell
$ketQua37 = Get-Content .\docs\acceptance\37-mailbox-20261110.json -Raw | ConvertFrom-Json
$ketQua37 | Select-Object status, mailbox_confirmed, cleanup
$ketQua37.delivery | Select-Object real_email_sends_accepted, duplicate_cli_skipped, period_key
```

Kỳ vọng: `status=PASS`, `mailbox_confirmed=True`, `cleanup=PASS`,
`real_email_sends_accepted=1`, `duplicate_cli_skipped=True`.

Artifact chỉ lưu metadata và fingerprint địa chỉ; không lưu email thật, body,
credentials hoặc token. Chia sẻ status/các trường trên; không cần chụp hộp thư.

## Nếu có lỗi

- File output đã tồn tại: đọc kết quả cũ, không xóa để chạy lại. Cần xem lần
  gửi trước đã diễn ra chưa trước khi chuẩn bị một lần khác.
- `SENT_AWAITING_MAILBOX_CONFIRMATION`: CLI/SES đã chấp nhận gửi và cleanup
  đạt, nhưng chưa có xác nhận nội dung. Mở thư đúng marker và báo lại; không
  chạy lại chỉ để đánh dấu `y`.
- Nếu `cleanup=FAILED`, chỉ chạy chế độ cleanup, không gửi lại:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\run-budget-mailbox-acceptance.py `
  --cleanup-from .\docs\acceptance\37-mailbox-20261110.json `
  --output .\docs\acceptance\37-mailbox-cleanup-20261110.json
```

- SES/CLI lỗi hoặc kết quả gửi không rõ: giữ artifact và báo `status`,
  `reason`, task ID. Không dùng script cũ chạy job trên toàn bộ household và
  không retry liên tục.

Sau khi mailbox PASS, gắn artifact này cùng biên bản ngân sách để chốt #37.
