# Rà soát phần việc nhóm còn lại — 10/11/2026

Phạm vi: checkout `homewallet-gr13/main`, tài liệu giao việc tuần 10 lưu local,
biên bản đã merge, AWS read-only và phép thử Bedrock tổng hợp có giới hạn.
Không đánh đồng thiếu artifact trong repo với chưa làm; #29 có bằng chứng
riêng được Kiên xác nhận. File Word hướng dẫn tuần tiếp tục chỉ lưu local.

## Việc cần xử lý hoặc bổ sung bằng chứng

| Ưu tiên | Việc | Kết luận | Hướng hoàn tất / người phụ trách |
| --- | --- | --- | --- |
| 1 | **#34 — benchmark Bedrock/Gemini** | **PARTIAL**, lỗi quyền cũ đã chẩn đoán; policy hiện hành đã sửa, preflight đã sửa. Kiên gọi văn bản thật `200`; thiếu phiên Hoàng và benchmark theo cặp hợp lệ. | Hoàng chạy kiểm tra truy cập nhỏ bằng chính mình; bổ sung quota và run mới được Kiên chốt trước khi gửi ảnh. Xem [kết quả và các bước cụ thể](34-bedrock-remediation-20261110.md). Chi hỗ trợ quyền/model. |
| 2 | **#39 / sự cố DLQ thuộc theo dõi #33** | Receipt `1` được giữ để phục hồi; một lần thử gặp Gemini `ServerError`, rollback xác nhận ảnh và DB không đổi, transaction vẫn 0. | Kiên dùng quy trình phục hồi có kiểm soát sau kiểm tra readiness mới. Giữ receipt/S3/message, không redrive hàng loạt; kết quả thành công phải là một draft để review. Xem [biên bản](33-receipt1-recovery-20261110.md). |
| 3 | **#38 — README và bàn giao** | **README hiện chỉ 2 byte**, không có hướng dẫn sử dụng. Đây là thiếu sót xác định được trong repo. | Hoàng bổ sung cài đặt, biến môi trường mẫu, chạy/test/deploy/log, kiến trúc, chi phí có nguồn/ngày và giới hạn. Người khác clone và làm theo được. Dẫn tới các biên bản nghiệm thu hiện hành. |
| 4 | **#25 / #37 — nghiệm thu ngân sách** | Cần đối chiếu bằng chứng cuối. Đã có API/rule/LLM-fallback tests và bộ ca BUD-01–10; chưa tìm thấy bảng kết quả runtime đầy đủ cho các ca ngân sách trong repo. | Hoàng cùng Kiên/Thức gắn evidence đã có vào từng ca: dữ liệu sai/biên, danh mục lạ/trùng, fallback, lịch sử tháng và quyền hộ. Nếu chưa chạy, dùng fixture riêng. Không chạy lại các ca jobs đã đạt chỉ để có log mới. |
| 5 | **#40 — mobile** | Có mã responsive; chưa tìm thấy biên bản thiết bị thật với đủ `vi/en × sáng/tối` trong repo. | Thức cung cấp hoặc hoàn tất ma trận 4 cấu hình: auth/menu, upload-review, dashboard/budget, community/admin, notifications; kiểm tra bàn phím và tràn ngang. Sửa blocker rồi ghi thiết bị/browser và kết quả. |
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
