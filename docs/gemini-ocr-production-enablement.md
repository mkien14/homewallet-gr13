# Gemini đọc hóa đơn: thay khóa và mở production có kiểm soát

Cập nhật **14/11/2026: đã bật OCR tại worker** bằng `gemini-3.5-flash-lite`,
candidate `a5097aa`. Đã đạt upload-consent → S3 → queue riêng → worker → Gemini
→ draft → xác nhận, policy/quota/replay và rollback. Chỉ dùng ảnh tổng hợp;
không gửi ảnh hộ thật trong nghiệm thu. [Biên bản](acceptance/production-release-a5097aa-20261114.md).

Version khóa AWSCURRENT: `134ab65d-79de-48d9-b27c-73300828943c`. Kiên xác nhận
thu hồi khóa cũ ở HWAPI; đây là attestation của chủ project, không phải audit
Google độc lập. [Bằng chứng rotation](acceptance/gemini-rotation-20261113.json).
Model 3.6 đã trả 503 trong hai smoke ảnh; chọn 3.5 Flash Lite sau smoke và E2E
đạt. Metadata GET không thay nghiệm thu generate.

Phạm vi: 16 hộ đã duyệt, loại hộ 1; ảnh mới có consent ở prefix
`receipts/production/`, queue/DLQ mới. Cap app 10 attempts/ngày UTC, cách nhau
30 giây, tối đa hai attempts/receipt và 4096 output token. Một lần generate đạt
không xác nhận quota Google còn lại hoặc benchmark chất lượng rộng #34.
Chỉ worker nhận key; API Gemini ngân sách, Textract fallback và Scheduler tắt.
Các mục dưới đây là runbook rotation và tiêu chí cho lần thay đổi tiếp theo.

## 1. Kiên thu hồi khóa cũ ở Google

**Đã nhận xác nhận hoàn tất ngày 13/11/2026.** Các bước dưới đây là runbook cho
lần rotation sau; không yêu cầu tạo lại key hiện tại.

1. Mở [Google AI Studio → API keys](https://aistudio.google.com/apikey), đăng
   nhập Google account quản lý project **HWAPI**.
2. Chọn đúng project HWAPI, đối chiếu tên/project ID trong bảng quản lý. Không
   tạo project khác chỉ để lấy quota mới.
3. Tìm khóa đã từng gửi trong chat bằng bản ghi quản lý của bạn, chọn thao tác
   **Delete/Revoke** của khóa đó và xác nhận. Nếu AI Studio không hiện khóa,
   mở Google Cloud Console → APIs & Services → Credentials của đúng project để
   quản lý. Không xóa cả project hoặc service account dùng chung.
4. Xác nhận khóa cũ đã bị xóa/thu hồi trong trang quản lý. Ghi ngày và tên khóa
   làm bằng chứng, không chụp/copy chuỗi key. Thay secret AWS không thu hồi key
   Google, nên bước này phải thực hiện ở Google.

## 2. Tạo khóa mới và ghi vào secret AWS hiện có

1. Ở API keys, chọn **Create API key** trong project HWAPI; đặt tên dễ quản lý,
   chẳng hạn `homewallet-production-ocr-20261113`.
2. Dùng cơ chế key hiện hành của Google AI Studio, kiểm tra quyền của identity
   gắn với key và giới hạn API vào **Generative Language API**. Key dùng trên
   backend ECS, không đưa vào frontend hoặc biến `VITE_*`.
3. Copy key mới. Không dán vào chat, lệnh shell, `.env` trong repo hoặc tài liệu.
4. Tại PowerShell trong repo, chạy helper hiện có:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\put-gemini-secret-version.py `
  --secret-id 'hw/dev/gemini-api-key' `
  --expected-account '179923444714' `
  --region 'ap-southeast-1'

if ($LASTEXITCODE -ne 0) {
    throw 'Chưa lưu được khóa mới. Giữ Gemini/OCR tắt.'
}

Set-Clipboard -Value 'HomeWallet: key stored in Secrets Manager'
```

Helper yêu cầu nhập key **hai lần, không hiện ký tự**. Nhập riêng phần key,
không có tiền tố `GEMINI_API_KEY=` hoặc dấu nháy. Thông báo thành công gồm ARN
và Version ID, không in giá trị key. Không chạy `GetSecretValue` ra terminal
để xem lại. Nếu đổi AWS profile, thêm `--profile '<profile-admin-đã-xác-thực>'`;
helper luôn đối chiếu account trước khi ghi.

Lệnh clipboard ghi đè nội dung bằng dòng chữ không bí mật. Tránh dùng chuỗi rỗng
vì Windows PowerShell trên máy Kiên báo `Value cannot be null`. Nếu đã thấy
`Secret version stored successfully` rồi mới gặp lỗi clipboard, khóa đã lưu;
chỉ chạy riêng lệnh ghi đè clipboard, không chạy lại helper để sửa lỗi này.

Lệnh này chỉ thêm version vào secret **đã có**, không tạo secret mới, không tự
restart task hoặc bật Gemini. Production chỉ inject secret này vào worker OCR,
không vào API. Sau lần rotation tiếp theo, ghi nhận: “Đã thu hồi khóa cũ ở HWAPI và lưu
khóa mới vào Secrets Manager”, kèm Version ID nếu cần; không gửi key.

Tài liệu tham chiếu: [quản lý Gemini API key](https://aistudio.google.com/docs/api-key).

## 3. Các điều kiện kỹ thuật trước khi bật

### Worker và dữ liệu

- Kiểm tra production allowlist và bản ghi audit
  `RECEIPT_PROCESSING_CONSENT_V1` đúng receipt/uploader trước cập nhật trạng thái,
  đọc ảnh S3 và gọi provider. Kiểm tra cả nhánh CLI/local và nhánh đánh FAILED;
  không cho đường phụ vượt phạm vi.
- Có mốc bắt đầu/cutoff và phạm vi xử lý mới rõ ràng. Không bật consumer queue
  chung nếu nó có thể consume, xóa, tăng receive count hoặc redrive thông điệp
  của hộ đang giữ. Tách đường nhận thông điệp mới được duyệt nếu cần; không
  purge hoặc replay queue/DLQ cũ, không xử lý ảnh hộ 1.
- Worker cần tự thực thi admission/quota và xử lý message trùng; API quota ở
  thời điểm presign không đủ để giới hạn retry/replay ở worker.
- Không bật Textract fallback tự động như tác dụng phụ. Chọn rõ provider,
  chi phí, hành vi lỗi và quyền dùng dữ liệu cho từng provider.

### Quota, chất lượng và chi phí

- Khi thay key/model, kiểm tra generate bằng quyền project HWAPI. Model đang
  chạy là `gemini-3.5-flash-lite`; không quay lại 3.6 chỉ vì metadata GET đạt.
  Xem [tài liệu model](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite).
  Canary release đã thử PNG; không suy ra đã nghiệm thu mọi định dạng/loại ảnh.
- Xem quota hiện tại ở [AI Studio](https://aistudio.google.com/rate-limit), gồm
  RPM/TPM/RPD. Không dựa vào ảnh quota cũ hoặc coi đổi key là được quota mới.
  Quota áp dụng theo project theo
  [tài liệu Google](https://aistudio.google.com/docs/rate-limits).
- Giới hạn ban đầu phải chừa chỗ cho số lần retry và các consumer khác. Ví dụ,
  quota 20 request/ngày không đủ cho 20 hóa đơn nếu mỗi hóa đơn retry hai lượt.
  Một worker và khoảng nghỉ theo process không phải giới hạn toàn project.
- Chạy ảnh tổng hợp hoặc bộ ảnh nhóm cho phép dùng, có dữ liệu kỳ vọng. Kiểm
  tra cửa hàng/ngày/tổng tiền/dòng hàng/danh mục, tổng lệch và JSON lỗi; không
  coi một lần gọi thành công là benchmark hoàn tất. Không tự reset guard của
  benchmark #34 để lấy nhãn PASS.
- AWS budget 100 USD/tháng không giới hạn hóa đơn Google; cần kiểm soát quota/
  chi phí của project Google riêng, không tự nâng billing để vượt giới hạn.

### Candidate và rollout

- Sửa production profile có cờ mở OCR rõ ràng và điều kiện kiểm chứng rotation/
  benchmark, secret worker đúng phạm vi, giữ mặc định tắt.
- Workflow candidate có input `enable_ocr`, mặc định false; bản đang chạy build
  với input true. Giữ lựa chọn này tường minh và khớp manifest/profile API khi
  release tiếp theo; frontend/backend cùng artifact. Không sửa tay JS trên S3.
- Giữ AI gợi ý ngân sách bằng rule nếu chỉ mở Gemini cho đọc ảnh; không tự cấp
  key cho API để mở thêm tính năng khác. Consent UI phải nêu rõ xử lý ngoài AWS,
  kết quả là draft và người dùng kiểm tra trước khi xác nhận.
- Canary bằng dữ liệu tổng hợp: upload có consent → S3 → thông điệp mới →
  worker → Gemini → DRAFT; kiểm tra retry/quota/idempotency, thiếu consent,
  truy cập chéo hộ, hộ đang giữ và stop/rollback. Chỉ mở sau bằng chứng đạt.
- Khi dừng: tắt nhận upload mới và pause consumer trước ReceiveMessage, không
  làm mất thông điệp hoặc quay về task có profile dev. Scheduler vẫn DISABLED.

Chưa đủ các điều kiện trên thì giữ `OCR_ENABLED=false`, `GEMINI_ENABLED=false`
và không sửa attestation để vượt preflight.
