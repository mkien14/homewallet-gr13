# Terraform production: kết nối và đối chiếu AWS — 13/11/2026

**PASS cho kết nối, chạy plan và đối chiếu cấu hình. Chưa apply hoặc đổi state.**
Source `0cc9821` đã gồm PR #130; ứng dụng đang chạy release `26a0645`.
Nhánh tài liệu: `fix/production-reconcile-gemini`; Kiên tự commit/push.

## 1. Secrets Manager đã kết nối lại được

- Đúng account `179923444714`, Region `ap-southeast-1`, profile mặc định.
- DNS/TCP 443 và TLS xác thực chứng chỉ đạt với endpoint chính thức
  `secretsmanager.ap-southeast-1.amazonaws.com` (TLS 1.3).
- `DescribeSecret` của VAPID và Gemini thành công; không đọc giá trị secret.
- Terraform đọc `data.aws_secretsmanager_secret.vapid_private_key` thành công
  và hoàn tất refresh/plan. Lỗi timeout trước không tái hiện; chưa có bằng chứng
  xác định nguyên nhân mạng gốc. Không đổi IAM, VPC, DNS, proxy hay tắt TLS.

Endpoint Singapore được đối chiếu với
[tài liệu AWS](https://docs.aws.amazon.com/general/latest/gr/asm.html).
Kết quả này không phải bảo đảm mạng local không bao giờ gián đoạn lại.

## 2. Plan bằng input production đã lưu

Input: `%LOCALAPPDATA%\HomeWallet\production\20261113\production.tfvars.json`.
Saved plan, JSON đầy đủ, log và bản sao state serial 143 lưu trong thư mục ACL
hạn chế `…\reconcile-20261113`, ngoài Git. Không đưa các file này vào PR.

Lệnh dùng `plan -input=false -no-color -lock-timeout=60s -detailed-exitcode`.
Exit **2** là plan thành công và có chênh lệch. Tổng hợp:

| Đối tượng | Plan | Đối chiếu AWS |
| --- | --- | --- |
| Task API | Đăng ký revision thay revision `:28` state đang giữ | Container, image/release, role, CPU/RAM, runtime platform và tag khớp API `:29` đang chạy |
| Task worker | Đăng ký revision thay revision `:5` state đang giữ | Khớp worker `:6` đang chạy |
| Task jobs | Đăng ký revision thay revision `:5` state đang giữ | Khớp jobs `:6`, target ba lịch DISABLED |
| IAM policy Scheduler | Data policy đọc lúc apply nên policy tạm là unknown | Statement dự kiến khớp ngữ nghĩa với policy live: chỉ họ `hw-jobs:*`, đúng cluster và hai role ECS |
| DB/network/service/bucket | Không có thay đổi apply | Không đề xuất thay/xóa các tài nguyên này |

Terraform ghi **3 add / 1 change / 3 destroy**: ba replacement là task
definition, không phải ECS service hoặc database. `skip_destroy=true` của ba
task definition được kiểm tra; không diễn giải số destroy thành xóa dữ liệu.
Policy update là hệ quả dependency/read hoãn; không phát hiện thiếu quyền jobs
`:6` trên AWS. Không mở rộng IAM hoặc bật lịch để thử.

AWS vẫn chạy API `:29` 2/2, worker `:6` 1/1 và jobs `:6`. Ba task dùng đúng
candidate/image đã nghiệm thu; API/worker không được nạp Gemini key, OCR/Gemini
đều false. Preflight đọc lại đạt **GO, 90/90**.

## 3. Kết luận và ranh giới thay đổi

Yêu cầu chạy plan/đối chiếu đã hoàn tất. Không có `apply`, import, state rm hoặc
state push. Không đổi release, không chạy lại migration/restore/deploy; dữ liệu
hộ 1 và DLQ được giữ nguyên. Không tuyên bố Terraform “No changes”.

State/output còn giữ revision Terraform cũ, trong khi dịch vụ đã chạy revision
mới. Lần đồng bộ state tiếp theo phải có backup và đối chiếu ARN/config vừa đọc
lại, rồi dùng quy trình rebind/import được review hoặc apply saved plan đã review
để đăng ký revision tương đương. Không tự `state push`, không copy output cũ để
deploy lại dịch vụ. Saved plan của đợt này chỉ là hồ sơ review; tạo plan mới trước
một apply trong tương lai, sau khi kiểm tra mọi thay đổi phát sinh.

## 4. Quyết định Gemini đọc ảnh

**NO_GO — giữ tắt.** Kiên xác nhận khóa từng gửi trong chat chưa được thu hồi và
chưa thay bằng khóa mới. Không sửa `gemini_provider_revocation_confirmed` hoặc
`ocr_benchmark_accepted` thành true. Không gọi generate, không gửi ảnh lên Google,
không đổi giá trị/stage secret trong đợt này.

Ngoài rotation/quota/nghiệm thu, pipeline worker hiện kiểm tra status receipt
nhưng chưa kiểm tra allowlist hộ và bản ghi consent trước `_mark_processing`,
S3 read và provider call. Chỉ bật biến môi trường sẽ cho worker đọc queue chung;
API guard không thay thế worker guard cho thông điệp cũ. Không consume/redrive
queue hoặc DLQ để kiểm tra. Frontend candidate và profile Terraform hiện cũng
cố ý khóa OCR ở false.

Gemini `gemini-3.6-flash` có hỗ trợ ảnh/PDF đầu vào và output text theo
[tài liệu model](https://aistudio.google.com/docs/models/gemini-3.6-flash).
Khả năng model không thay thế quyền truy cập/quota và chất lượng trích xuất
thực tế của project HWAPI. Đổi API key không tự cấp thêm quota vì quota theo
project, theo [tài liệu rate limits](https://aistudio.google.com/docs/rate-limits).

Xem [hướng dẫn thay khóa và điều kiện mở OCR](../gemini-ocr-production-enablement.md).
Bằng chứng máy đọc được: [kết quả đối chiếu](production-terraform-reconcile-20261113.json).

### Cập nhật rotation sau biên bản plan

Kiên đã lưu version mới `134ab65d-79de-48d9-b27c-73300828943c` và xác nhận thu
hồi khóa cũ trong Google HWAPI. Metadata model `gemini-3.6-flash` truy cập thành
công bằng khóa mới; không gọi generate, gửi ảnh hoặc đổi feature flag. Settings
vận hành đã ghi nhận attestation thu hồi; benchmark vẫn false. Xem
[kết quả rotation](gemini-rotation-20261113.json). Các giá trị false trong JSON
biên bản plan ở trên phản ánh thời điểm trước xác nhận; không sửa lịch sử để coi
OCR đã nghiệm thu. Các chặn worker/phạm vi dữ liệu/quota/candidate vẫn còn.
