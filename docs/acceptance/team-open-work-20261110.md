# Rà soát phần việc nhóm còn lại — 10/11/2026 (cập nhật #34 ngày 11/11)

Phạm vi: checkout `homewallet-gr13/main`, tài liệu giao việc tuần 10 lưu local,
biên bản đã merge, AWS read-only và phép thử Bedrock tổng hợp có giới hạn.
Không đánh đồng thiếu artifact trong repo với chưa làm; #29 có bằng chứng
riêng được Kiên xác nhận. File Word hướng dẫn tuần tiếp tục chỉ lưu local.

## Việc cần xử lý hoặc bổ sung bằng chứng

| Ưu tiên | Việc | Kết luận | Hướng hoàn tất / người phụ trách |
| --- | --- | --- | --- |
| 1 | **#34 — benchmark Bedrock/Gemini** | **PARTIAL / NO-GO cho ảnh:** Kiên xác nhận Hoàng đã chạy smoke bằng identity riêng, kết quả đúng mong đợi; artifact chưa có trong checkout. Quota Gemini mới chưa được xác nhận; pilot ảnh cũ đã khóa. | Không gửi ảnh hoặc gỡ guard. Nếu cần, thêm artifact smoke đã gửi; chỉ cân nhắc run ID mới sau khi Kiên xác nhận quota/chi phí và nhóm duyệt. Xem [quyết định và điều kiện](34-bedrock-remediation-20261110.md). |
| 2 | **#39 / sự cố DLQ thuộc theo dõi #33** | **SCOPE MISMATCH:** household `1` thuộc người ngoài nhóm; lần phục hồi đã gửi ảnh tới Gemini một lần và tạo transaction `39` ở `DRAFT`, chưa xác nhận. | Quyết định hiện tại: giữ draft, ảnh gốc và DLQ; không review, confirm, xóa, nhận hay redrive. Chờ chủ dữ liệu/người quản lý dữ liệu được chỉ định quyết định giữ hoặc xóa qua quy trình kiểm soát. Xem [biên bản và disposition](33-receipt1-recovery-20261110.md). |
| 3 | **#38 — README và bàn giao** | README đã được bổ sung hướng dẫn cài đặt, mock/dev/local, checks, deploy, bảo mật, kiến trúc và nguồn giá tham khảo ngày 11/11. Chưa có tổng dự toán tháng; phải đối chiếu Cost Explorer/Calculator cho kỳ và cấu hình cụ thể trước khi công bố con số. | Hoàng/nhóm rà lại các lệnh trên máy clone sạch và bổ sung dự toán nếu deliverable yêu cầu số tiền tháng. Xem [README](../../README.md). |
| 4 | **#25 / #37 — nghiệm thu ngân sách** | PASS trong phạm vi đã định: API dev 57/57; Gemini thật, fallback, lịch sử, ngưỡng 80/100, chống gửi trùng trên schema riêng; một email thật D1 đã được Kiên xác nhận; cleanup PASS. CLI job chạy trong ECS jobs. Lịch EventBridge định kỳ vẫn DISABLED. | Xem [biên bản](25-37-budget-20261110.md) và [artifact email](37-mailbox-20261110.json). Không chạy lại trên household thật; việc bật lịch định kỳ cần quyết định rollout riêng. |
| 6 | **Fixture D4 / #36** | #36 đã CLOSED; receipt `28` ở household `12` có disposition chưa chốt trong biên bản, local terminal/capture của Hoàng chưa được review. | Hoàng xác nhận nguồn fixture và bàn giao evidence đã che dữ liệu; Kiên chốt giữ/dọn đúng ID. Giữ nguyên dữ liệu khi chưa có quyết định. Không mở lại AC3/tải đã nghiệm thu. |
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
