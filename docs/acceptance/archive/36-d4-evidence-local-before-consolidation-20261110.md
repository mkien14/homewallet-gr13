# D4 / #36: báo cáo bằng chứng

> Bản nháp local được lưu lại khi hợp nhất về main ngày 10/11/2026.
> Biên bản hiện hành và quyết định CLOSED nằm tại
> [36-d4-evidence.md](../36-d4-evidence.md). Các trạng thái chờ trong bản nháp
> bên dưới được giữ làm lịch sử, không thay thế kết luận mới hơn.

**Cập nhật 09/11/2026:** Kiên đã chạy AC3 và bài tải đọc độc lập trên dev.
Kết quả thực tế, số liệu CloudWatch và giới hạn OCR nằm trong
[36-d4-kien-run-20261109.md](36-d4-kien-run-20261109.md). Mục bổ sung ngay dưới
ghi ca Member mới; các mục sau đó là khung lập ngày 08/11/2026. Những ô “chưa
có” trong khung cũ không còn là trạng thái hiện tại của AC3 và tải đọc.

## Bổ sung AC3: quyền Member trong household 12

Kiên cung cấp ảnh UI, Console và Network của phiên tài khoản mới đã tham gia
household 12 với role `member`. Response headers của hai request nghiệm thu ghi
`Mon, 09 Nov 2026 05:40:29 GMT`, tương ứng **12:40:29 ngày 09/11/2026** tại
Asia/Bangkok. Request đi qua `https://daoedidcrnf1f.cloudfront.net`.

| Ca | HTTP kỳ vọng | HTTP thực tế | X-Request-Id | Kết luận |
| --- | ---: | ---: | --- | --- |
| GET `/api/me`: household 12, role `member` | 200 | 200 | Không lưu ID đầy đủ | PASS |
| GET `/api/households/12/members` bằng Member | 200 | 200 | `18956e89-80aa-46ae-bb5a-4281d7ef8461` | PASS |
| POST `/api/households/12/invite-code` bằng Member | 403 | 403 | `c1837d20-3fa5-41d2-893d-6f374ed9cf97` | PASS |

HTTP 403 là kết quả từ chối quyền mong đợi; không có bằng chứng mã mời đã đổi.
Ảnh do Kiên cung cấp trong cuộc trao đổi ngày 09/11; biên bản không lưu email
cá nhân, token, mật khẩu hay mã mời. **Receipt 28 giữ nguyên** đến khi nhóm
thống nhất cách dọn. Bổ sung này mở rộng bằng chứng AC3 về quyền Member; OCR
vẫn `Partial/Blocked` theo phạm vi D4 đã chốt.

Ngày mở báo cáo: 08/11/2026 (Asia/Bangkok).
Người tổng hợp: Hoàng. Người review/nghiệm thu và theo dõi tải: Kiên.
Chi hỗ trợ monitoring khi cần.

Đây là khung ghi nhận, chưa phải biên bản PASS. Kiên báo Hoàng đã chạy xong
mục 4; chưa có output đính kèm để đối chiếu. Chưa nhận bằng chứng tải nhẹ và
chưa có kết quả OCR hợp lệ đủ để công bố so sánh.

## Trạng thái và người phụ trách

| Phần | Người thực hiện | Trạng thái hiện tại | Điều kiện đóng |
| --- | --- | --- | --- |
| AC3 | Hoàng | Đã báo chạy xong; chờ bằng chứng | Output các ca và cấu hình lần chạy được Kiên review; ghi giới hạn nếu thiếu request ID |
| OCR | Hoàng tổng hợp, Kiên giữ gate | Partial/Blocked | Có report thực tế hoặc blocker/owner rõ; không suy diễn thành metric 42 mẫu |
| Tải nhẹ | Hoàng chạy, Kiên theo dõi | Chờ bằng chứng | Thống kê client và CloudWatch cùng cửa sổ thời gian; ghi rõ nếu phải dừng |
| Làm sạch bằng chứng, kiểm kê fixture | Hoàng + Kiên | Chờ thực hiện | Không lộ dữ liệu nhạy cảm; chỉ dọn receipt test đã xác định đúng ID |
| Review cuối | Kiên | Chưa nghiệm thu toàn bộ | Kết luận từng phần dựa trên artifact, giữ Partial/Blocked nếu còn thiếu |

## Cấu hình của lần chạy

- Dev endpoint dự kiến: `https://daoedidcrnf1f.cloudfront.net`.
- Account/region: `179923444714` / `ap-southeast-1`.
- Baseline đã từng kiểm tra: API `hw-api:19`, commit
  `95658d3b2bdfaad9b1930416f4b265e5861da16e`.
- Commit/image digest thực tế của lần chạy: chưa ghi nhận trong báo cáo này.
- Giờ bắt đầu/kết thúc kèm timezone: chưa ghi nhận.
- Phiên bản script/cấu hình client tải: chưa ghi nhận.

Đối chiếu baseline với deployment thực tế; nếu có thay đổi, điền bản đã chạy.
Không dùng ngày tạo báo cáo thay cho timestamp kiểm thử.

## AC3 — Hoàng bổ sung từ lần chạy mục 4

| Ca | Kỳ vọng | Thực tế | Artifact/request ID |
| --- | --- | --- | --- |
| Không token GET /api/me | 401 | Chưa đính kèm | Chưa có |
| B xem thành viên household A | 404 | Chưa đính kèm | Chưa có |
| B xem receipt thuộc household A | 404 | Chưa đính kèm | Chưa có |
| A xem thành viên household của mình | 200 | Chưa đính kèm | Chưa có |

- Hai user thuộc hai household khác nhau: chờ bằng chứng.
- Household ID A/B, receipt ID đã tạo: chờ Hoàng ghi nhận.
- Output PASS/FAIL cuối: chờ đính kèm.
- Giới hạn: script cũ không tự lưu request ID hoặc dọn receipt. Không tạo
  thêm một lần chạy chỉ để lấp ô trống; ghi rõ phần không còn truy xuất được.
- Bốn ca trên không bao phủ toàn bộ quyền owner/member, token hết hạn hoặc
  mọi loại token không hợp lệ; không mở rộng kết luận ngoài các ca đã chạy.

## OCR — Hoàng tổng hợp bằng chứng D3

- Phạm vi được ghi nhận đã duyệt: ảnh 021–030 cho Gemini/Bedrock; không có
  phê duyệt chạy mới/mở rộng 42 ảnh trong quyết định D4 hiện tại.
- Workspace đã kiểm tra có 20 ảnh dev và 10 ảnh test; thiếu 32 ảnh test.
- Tài liệu D3 ghi hai lần thử kết thúc một phần; chưa có so sánh độ chính
  xác trên dự đoán hợp lệ. Nội dung này là ghi nhận tài liệu, không thay thế
  report gốc.
- Report/lock gốc: chưa đính kèm; Hoàng tìm từ máy đã chạy, Kiên hỗ trợ truy
  nguồn. Không xóa/recreate lock để chạy lại.
- Khi có report: ghi model/config, số mẫu, attempted/valid/error/skipped,
  latency, retry, token usage và chi phí ước tính; phân biệt với hóa đơn.
- Nhãn ground truth dùng chấm offline. Không công bố accuracy 42 mẫu từ
  pilot 10 ảnh; không xem lỗi/skipped là chất lượng OCR trên dự đoán hợp lệ.
- Trạng thái giữ: Partial/Blocked cho đến khi có bằng chứng; không gọi thêm
  API để hoàn thiện báo cáo nếu chưa có phê duyệt riêng.

## Tải nhẹ — Hoàng chạy sau tín hiệu sẵn sàng của Kiên

- Route: GET `/api/dashboard?period=2026-11`; token của user test riêng.
- Profile: tối đa 5 client đồng thời, tối đa 2 phút, không retry tự động khi
  lỗi. Không upload, OCR hoặc LLM; `/api/ping` dùng kiểm tra đường đi.
- Không suy ra thông lượng xử lý OCR/LLM từ bài tải đọc dashboard.
- Điều kiện dừng: xuất hiện 5xx hoặc queue tăng liên tục; ghi mốc quan sát
  và người ra tín hiệu dừng. Lỗi mạng/timeout cũng được thống kê, không bỏ qua.
- Kiên kiểm tra service ổn định, target healthy, commit/digest và khả năng
  đọc CloudWatch ngay trước tải. Không có monitoring thì hoãn tải.

| Chỉ số | Kết quả/artifact |
| --- | --- |
| Thời gian bắt đầu/kết thúc thực tế, timezone | Chưa có |
| Số client tối đa thực tế | Chưa có |
| Tổng request và phân bố HTTP status | Chưa có |
| Lỗi mạng/timeout | Chưa có |
| p50/p95, đơn vị và tập request được tính | Chưa có |
| API/worker CPU và memory trước/trong/sau | Kiên bổ sung |
| ALB-generated / target-generated 5xx | Kiên bổ sung |
| SQS visible/in-flight và DLQ visible | Kiên bổ sung |
| Metric period/statistic và thời điểm dữ liệu xuất hiện | Kiên bổ sung |
| Log đã làm sạch, request ID nếu có | Hoàng + Kiên bổ sung |
| Có dừng sớm không, lý do và timestamp | Chưa có |

Giữ cửa sổ thu metrics đủ trước/sau lần chạy để bao phủ độ trễ xuất hiện dữ
liệu và chu kỳ CloudWatch. Không diễn giải thiếu datapoint là CPU/5xx/queue
bằng 0. Ghi rõ sample size, cache behavior nếu biết và giới hạn bài tải.
Chưa có ngưỡng p95 nghiệm thu được nhóm chốt; báo cáo số đo, không tự đặt
ngưỡng hoặc khẳng định đạt SLA.

## Review và dữ liệu test

- Hoàng che Authorization, token, email cá nhân, receipt text và secret khỏi
  artifact. Không commit ảnh/nhãn/raw output khi chưa có quyền chia sẻ tương ứng.
- Hoàng ghi ID fixture; Kiên phối hợp dọn đúng receipt test. Chưa xác định
  đúng ID thì giữ dữ liệu và ghi việc còn lại; không xóa theo phỏng đoán.
- Kết luận của Kiên: chờ review. Tách kết quả AC3, OCR, tải nhẹ; phần bị
  blocker vẫn giữ Partial/Blocked, không ghi toàn bộ D4 PASS.
