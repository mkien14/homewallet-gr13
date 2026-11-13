# Rà soát phần việc nhóm còn lại — 10/11/2026 (cập nhật #34 ngày 11/11)

Phạm vi: checkout `homewallet-gr13/main`, tài liệu giao việc tuần 10 lưu local,
biên bản đã merge, AWS read-only và phép thử Bedrock tổng hợp có giới hạn.
Không đánh đồng thiếu artifact trong repo với chưa làm; #29 có bằng chứng
riêng được Kiên xác nhận. File Word hướng dẫn tuần tiếp tục chỉ lưu local.

## Việc cần xử lý hoặc bổ sung bằng chứng

| Ưu tiên | Việc | Kết luận | Hướng hoàn tất / người phụ trách |
| --- | --- | --- | --- |
| 1 | **#34 — benchmark Bedrock/Gemini** | **PARTIAL / NO-GO cho ảnh:** Kiên xác nhận Hoàng đã chạy smoke bằng identity riêng, kết quả đúng mong đợi; artifact chưa có trong checkout. Quota Gemini mới chưa được xác nhận; pilot ảnh cũ đã khóa. | Không gửi ảnh hoặc gỡ guard. Nếu cần, thêm artifact smoke đã gửi; chỉ cân nhắc run ID mới sau khi Kiên xác nhận quota/chi phí và nhóm duyệt. Xem [quyết định và điều kiện](34-bedrock-remediation-20261110.md). |
| 2 | **#39 / sự cố DLQ thuộc theo dõi #33** | **CLOSED theo quyết định admin ngày 11/11/2026.** Household `1` thuộc người ngoài nhóm; transaction `39` là `DRAFT`, ảnh và DLQ được giữ ở trạng thái cuối đã ghi nhận. | Đóng đầu việc/acceptance tracking theo quyết định Kiên; không thực hiện thêm thao tác dữ liệu. Việc đóng không được hiểu là đã xác nhận giao dịch, xóa dữ liệu, xử lý DLQ, hoặc có consent của chủ dữ liệu. Xem [biên bản recovery](33-receipt1-recovery-20261110.md). |
| 3 | **#38 — README và bàn giao** | README đã được bổ sung hướng dẫn cài đặt, mock/dev/local, checks, deploy, bảo mật, kiến trúc và nguồn giá tham khảo ngày 11/11. Chưa có tổng dự toán tháng; phải đối chiếu Cost Explorer/Calculator cho kỳ và cấu hình cụ thể trước khi công bố con số. | Hoàng/nhóm rà lại các lệnh trên máy clone sạch và bổ sung dự toán nếu deliverable yêu cầu số tiền tháng. Xem [README](../../README.md). |
| 4 | **#25 / #37 — nghiệm thu ngân sách** | PASS trong phạm vi đã định: API dev 57/57; Gemini thật, fallback, lịch sử, ngưỡng 80/100, chống gửi trùng trên schema riêng; một email thật D1 đã được Kiên xác nhận; cleanup PASS. CLI job chạy trong ECS jobs. Lịch EventBridge định kỳ vẫn DISABLED. | Xem [biên bản](25-37-budget-20261110.md) và [artifact email](37-mailbox-20261110.json). Không chạy lại trên household thật; việc bật lịch định kỳ cần quyết định rollout riêng. |
| 6 | **Fixture D4 / #36** | **CLOSED theo quyết định admin ngày 11/11/2026.** Bằng chứng AC3/Member/tải đọc giữ nguyên; receipt `28` và terminal/capture của Hoàng không được xử lý thêm trong phạm vi đầu việc này. | Kiên chấp nhận đóng #36 với các giới hạn đã ghi. Việc đóng không đồng nghĩa receipt `28` đã được dọn hoặc disposition dữ liệu đã được kiểm chứng. Không mở lại AC3/tải đã nghiệm thu. |
| 7 | **#38 / #41 — báo cáo, phụ lục, video demo** | Chưa xác nhận đủ bản cuối qua repo; tài liệu có thể nằm ngoài repo. Slide nằm ngoài phần rà soát này. | Hoàng tổng hợp trạng thái Done/Partial/Not deployed, PR/commit, số liệu có nguồn và video demo bằng tài khoản test. Cả nhóm đối chiếu với dev; không mô tả OCR benchmark đã thành công. |

## Những phần đã có bằng chứng, không cần làm lại

- **#29:** CLOSED/PASS theo Kiên; bằng chứng runtime giữ riêng. Xem
  [biên bản cuối](29-final-acceptance-20261110.md).
- **#31:** WAF CloudFront nghiệm thu theo phạm vi COUNT đã duyệt.
- **#32:** DB runtime least privilege phase 2 đã được Kiên nghiệm thu.
- **#33:** alarm/dashboard/SNS đã có bằng chứng; receipt DLQ ở trên là sự cố
  vận hành theo dõi riêng, không phủ nhận phần giám sát đã đạt.
- **#36:** AC3/Member và tải đọc có bằng chứng; CLOSED theo quyết định nhóm,
  với giới hạn D3 và fixture được ghi rõ.
- **#42 / #43:** locale và email E2E trong phạm vi chốt đã PASS. Xem
  [43-final-acceptance-20261110.md](43-final-acceptance-20261110.md).
- **#40:** Kiên xác nhận Thức đã nghiệm thu mobile và gửi bằng chứng riêng cho
  Kiên. Bằng chứng được giữ ngoài repo; không yêu cầu chạy lại.
- **#26 và một phần #37:** API thông báo/đọc, đăng ký-hủy push và nhận push đã
  có bằng chứng; Scheduler chạy ba CLI job thật trên schema test, gửi SES
  simulator và push; chạy lặp bỏ qua theo key. Không coi phần này vẫn BLOCKED
  bởi SES sandbox. Xem [runtime fixture](43-runtime-20261110.md) và
  [Scheduler delivery](43-delivery-20261110.md). Các ca này không thay thế toàn
  bộ ma trận ngân sách #25/#37 hoặc mọi browser/đường lỗi của push.
- Hướng dẫn tuần 10 ghi #15/#22/#23/#24/#27/#28/#30 là baseline đã có; lần rà
  này không kiểm thử lại để cấp nghiệm thu mới cho những phần đó.

## Quyết định admin bổ sung — 11/11/2026

- Kiên, với vai trò admin, quyết định **đóng #39 và #36 ngay**, không yêu cầu thao
  tác hoặc xử lý dữ liệu bổ sung. Giữ nguyên các trạng thái cuối và giới hạn trong
  biên bản; trạng thái đóng là quyết định quản lý công việc, không phải xác nhận
  giao dịch, xóa dữ liệu, xử lý DLQ hay xác minh consent.
- Kiên quyết định **nghiệm thu và đóng #27, #28, #30** kể từ 11/11/2026. Đây là
  chấp nhận của admin dựa trên baseline đã có; không ghi thành lần chạy kiểm thử
  mới hoặc bằng chứng runtime mới.

## Quyết định rollout đang được giữ

- Lịch Scheduler định kỳ gốc vẫn **DISABLED** theo phạm vi ca nghiệm thu; lịch
  một lần và schema test đã dọn. Khi nhóm muốn chạy thường xuyên, Kiên phải
  rà recipient/dữ liệu/chi phí và chọn thời điểm bật. Đây là quyết định vận hành.
- Auth cutover sang flow mới là rollout riêng; locale Hosted UI/PKCE đã đạt.
- Giữ WAF COUNT, hostname CloudFront, RDS single-AZ/một NAT và provider OCR
  hiện tại theo quyết định nhóm.

## Đối chiếu GitHub và giới hạn

API GitHub công khai lúc rà soát trả **0 issue mở, 0 PR mở**. Các số #25–43 ở
đây là mã công việc trong tài liệu, không thể dùng số issue đang mở làm bằng
chứng mọi hạng mục đã đạt. CI trên main `242e20f` thành công:
[run 42806181887](https://github.com/mkien14/homewallet-gr13/actions/runs/42806181887).
Đây là baseline trước thay đổi #34 trong lần rà soát này, không phải kết quả CI
của commit sửa mới.

Rà soát không có quyền xem bằng chứng riêng ngoài workspace. Các dòng “cần đối
chiếu” sẽ được đóng bằng artifact sẵn có nếu nhóm đã chạy; không yêu cầu tạo
lại dữ liệu, gửi lại email hoặc chạy OCR chỉ vì bằng chứng chưa được đưa vào repo.

## Thứ tự đề nghị

1. Hoàn tất truy cập Hoàng và chốt cách kết thúc #34; có hoặc không chạy OCR mới
   đều phải ghi đúng giới hạn trong báo cáo.
2. Bổ sung README và ma trận nghiệm thu ngân sách/mobile bằng evidence đã có.
3. Xử lý receipt/fixture theo đúng disposition; đóng gói phụ lục và video.
4. Kiên kiểm tra CI, bản dev và quyết định lịch/auth trước khi bàn giao.
