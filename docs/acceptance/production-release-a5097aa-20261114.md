# Nghiệm thu và bàn giao production — 14/11/2026

**Đạt trong phạm vi 16 hộ đã duyệt.** Chủ vận hành: **Kiên**.
Website: https://daoedidcrnf1f.cloudfront.net.

## Phiên bản đã phát hành

| Thành phần | Giá trị |
| --- | --- |
| Source main | `a5097aa3fd941c53a9cc9a3961f205d9e55d1553` |
| Candidate | [43471247102](https://github.com/mkien14/homewallet-gr13/actions/runs/43471247102) |
| Artifact | `14061021492`; frontend/backend lấy từ cùng artifact |
| SHA256 ZIP | `73a285c6c1168cf353a6d658ca16eafe45e77358655326d3c5d67c4c0065a83e` |
| ECR digest | `sha256:4e6af786b86b595f9526010848e52d023bc027030260910edfcd91f02d41ca4a` |
| API / worker / jobs | `hw-api:34` / `hw-worker:10` / `hw-jobs:9` |
| Cổng cuối | **93/93 GO**, sau khi dọn hộ thử và trả lại allowlist cuối |
| Terraform | Saved plan đã review/apply; plan cuối **No changes**, exit code 0 |

## Kết quả thực tế

- Sáu kiểm tra CI đạt; scan container **0 HIGH, 0 CRITICAL, 0 secret finding**.
  Artifact được kiểm checksum; image config đã quét khớp image ECR đang chạy.
- Frontend đã publish; invalidation hoàn tất. Hash index khớp artifact;
  `/release.json` và `/api/release` cùng SHA. Không build lại frontend riêng.
- Edge thực tế: React/SRP và TOTP đăng nhập thành công; 12 kiểm tra trang/mobile
  đạt, không có page error/API 5xx; upload OCR và checkbox consent hiện đúng.
- Local backend: **234 PASS, 60 SKIP** theo cấu hình; bộ kiểm tra policy và
  MySQL 8.4 riêng **15 PASS**. CI chạy kiểm tra MySQL thật, không chỉ mock SQL.

## OCR đã bật có kiểm soát

Ảnh tổng hợp đi qua đăng nhập SRP → API consent → presigned S3 upload → queue
`production-ocr-queue` → worker → **Gemini `gemini-3.5-flash-lite`** → bản nháp.
Kết quả khớp cửa hàng `HOMEWALLET TEST STORE`, ngày `2026-11-13`, tổng **78.000
VND**, hai dòng **33.000/45.000 VND**. Sau đối chiếu mới xác nhận giao dịch;
API trả trạng thái `CONFIRMED`. Không gửi ảnh của hộ thật cho Google trong ca này.

Worker đã kiểm tra hộ, membership, bucket/prefix và consent audit trước đọc ảnh
hoặc đổi trạng thái. Kiểm tra trực tiếp từ chối hộ 1, thiếu consent, non-member
và prefix cũ. Quota dùng audit bền vững: **10 lần gọi/ngày UTC**, tối thiểu 30
giây giữa các lần, tối đa hai lần/receipt, tính cả retry; output tối đa 4096 token.
Ca kiểm tra giảm cap của lời gọi thử xuống 1 đã chặn đúng bằng dữ liệu audit thật;
replay receipt hoàn tất không tăng counter và không gọi thêm Google.

Canary đầu phát hiện thiếu quyền SELECT audit và dùng sai cột thời gian audit.
[PR #132](https://github.com/mkien14/homewallet-gr13/pull/132) sửa grant và dùng
cột `at`, bổ sung regression MySQL trước khi build candidate cuối. Không sửa
container đang chạy hoặc thêm cột DB để né lỗi. Model 3.6 từng trả 503 quá tải;
chọn 3.5 Flash Lite sau smoke và E2E đạt.

## Phục hồi, rollback và dữ liệu

- PITR/snapshot sang DB cô lập đạt với cùng candidate: khoảng **14,6/11,2 phút**
  đến kiểm tra ứng dụng; restore point trễ khoảng **254 giây**. Đã kiểm TLS,
  migration 006, runtime/audit grants, commit/rollback và auth/readiness.
- Thay một task API, failover Redis và RDS đạt; TLS MySQL/Redis và Lua sau
  failover đạt. AWS ghi nhận RDS failover hoàn tất, metadata AZ không đổi.
- Rollback **API :35 → :29 → :35** đạt. Sau cleanup chạy **:34** với phạm vi cuối;
  worker **:10**, jobs **:9**. Revision thử và candidate OCR lỗi đã deregister.
- Hộ thử 29, Cognito identities, DB user và toàn bộ version ảnh thử đã dọn;
  audit số lần gọi provider vẫn giữ để không reset quota. DB/SG/role phục hồi
  tạm đã dọn. Snapshot `hw-prod-before-core-20261113-df1fc11e` giữ đến review
  ngày **27/11/2026**; tag không tự xóa snapshot.
- **Hộ 1, ảnh/dữ liệu và queue/DLQ cũ giữ nguyên**; không receive/purge/replay
  queue cũ. Allowlist cuối không chứa hộ thử 29.

## Phạm vi bàn giao

Đây là production cho nhóm được duyệt, không mở signup công khai. Chỉ worker
nhận Gemini key; API gợi ý ngân sách vẫn dùng rule, Textract fallback tắt.
Ba Scheduler **DISABLED** theo quyết định đã chốt. Một ảnh tổng hợp chứng minh
canary của release, không thay benchmark chất lượng rộng của #34 hoặc SLA.
Chưa thử mất cả AZ hoặc chuyển endpoint primary sang DB phục hồi.

Bằng chứng: [release JSON](production-release-a5097aa-20261114.json),
[OCR/quota](production-ocr-a5097aa-20261114.json),
[restore/HA/rollback](production-resilience-a5097aa-20261114.json).
Xem [bàn giao vận hành](../runbooks/current-stack-production.md).
Biên bản ở nhánh `release/production-a5097aa`; Kiên giữ quyền commit/push/merge.
