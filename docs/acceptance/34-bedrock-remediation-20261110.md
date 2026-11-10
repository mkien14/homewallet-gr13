# #34 — sửa kiểm tra quyền Bedrock và hướng hoàn tất benchmark

Ngày rà soát: **10/11/2026**, Asia/Bangkok. Làm việc tại `homewallet-gr13`,
nhánh `main`. Người vận hành AWS: Kiên.

**Kết luận:** đã xác định nguyên nhân lần Bedrock bị từ chối, xác nhận policy
hiện hành đã có bản sửa, sửa lỗi preflight và gọi thử Bedrock thành công bằng
Kiên. **#34 vẫn PARTIAL:** chưa có runtime bằng chính Hoàng sau sửa và chưa có
benchmark OCR hợp lệ theo cặp Gemini/Bedrock.

## 1. Nguyên nhân đã có bằng chứng

[Artifact chẩn đoán](34-bedrock-diagnosis-20261110.json) ghi CloudTrail event
`7cf96de8-6d85-469a-82b3-73bc94ed1887` lúc **18:19:14 ngày 08/11**:

- Người gọi là `user/hoang`, thao tác `Converse` tại Singapore.
- AWS trả `AccessDenied`, chỉ rõ **explicit deny trong identity policy** đối
  với Nova Lite ở `ap-southeast-2` (Sydney), một đích của profile APAC.
- Policy `homewallet-dev-d1-testing:v3` có `GuardOnlyApSoutheast1`: chặn ngoài
  Singapore và chỉ miễn trừ `iam:SimulatePrincipalPolicy`.
- Bản `v4` đã được tạo lúc **19:37:11 ngày 08/11**, sau lần lỗi. Nó miễn trừ
  thêm `bedrock:InvokeModel`; quyền Allow vẫn đến từ policy D3 giới hạn đúng
  profile và model đích. Lần rà soát này không sửa IAM.

Preflight cũ dùng `aws:RequestedRegion=ap-southeast-1` cho mọi resource nên
không phát hiện Deny ở đích Sydney. Đã tái hiện bằng chính hai policy lịch sử:
cùng resource Sydney, context Singapore trả `allowed`, context Sydney trả
`explicitDeny`. Đây là mô phỏng bổ sung cho lỗi runtime đã có trong CloudTrail.

AWS yêu cầu quyền trên inference profile và model ở các vùng đích; điều kiện
`bedrock:InferenceProfileArn` áp dụng khi kiểm tra model nền tảng. Xem
[tài liệu inference profile](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html).
Quyền `bedrock:InvokeModel` cũng chi phối `Converse`, theo
[tài liệu IAM Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/security_iam_id-based-policy-examples.html).

## 2. Phần đã khắc phục và kiểm tra

| Nội dung | Kết quả |
| --- | --- |
| IAM của Hoàng, profile + 6 model đích, đúng context từng vùng | 7/7 `allowed`, không thiếu context |
| Gọi model trực tiếp, không qua profile được duyệt | `implicitDeny` |
| Dùng profile khác hoặc model Nova Pro ngoài phạm vi | `implicitDeny` trong mô phỏng |
| Model Nova Lite ở Singapore | Availability/entitlement AVAILABLE, authorization AUTHORIZED |
| Gọi thật từ Kiên, một prompt văn bản tổng hợp | HTTP `200`, 9 input / 2 output token, 0,717 giây; đáp án đúng |
| Gọi thật từ Hoàng sau sửa | Chưa chạy: máy chỉ có profile `default` của Kiên |
| Ảnh pilot gửi trong lần rà soát này | **0** |

Phép gọi bằng Kiên chỉ chứng minh kết nối/model hoạt động với quyền của Kiên;
không thay thế phép gọi bằng Hoàng hoặc benchmark OCR. Token sử dụng được ghi
để đối chiếu chi phí; không suy ra hóa đơn bằng 0 từ phép gọi nhỏ này.

- [Bằng chứng IAM và gọi thật bằng Kiên](34-bedrock-admin-smoke-20261110.json).
- [Bằng chứng thiếu profile Hoàng](34-bedrock-hoang-profile-check-20261110.json).
- `ocr-lab/bedrock_access.py`: kiểm tra từng ARN với vùng tương ứng; chỉ thêm
  profile context cho model; từ chối kết quả thiếu hoặc mâu thuẫn.
- `ocr-lab/bedrock_access_check.py`: kiểm tra identity trước; tùy chọn đúng một
  `Converse` bằng văn bản, tối đa 8 output token, SDK một attempt. Chỉ lưu
  metadata và kết quả kiểm tra, không lưu nội dung model hoặc credentials.
- `d3_pilot_v2.py` dùng chung phần kiểm tra IAM đã sửa.
- `d3_run_history.json` và `pilot_run_guard.py` giữ hai lần pilot cũ ở trạng
  thái đã tiêu thụ, kể cả khi checkout khác không có lock trong `out/` bị ignore.
  Không xóa lock hoặc sửa ledger để chạy lại.

Kiểm tra local: **25/25 unittest PASS**, gồm parser/scoring/quota trước đó,
context vùng đích, kết quả IAM thiếu, identity sai, thiếu profile, chống ghi đè
artifact và chặn pilot cũ trước khi gọi provider. Các unittest dùng mock.
CI đã bổ sung job `OCR pilot offline checks` chạy cùng bộ kiểm tra; job này
không cần AWS/Gemini credentials và không gọi model.

## 3. Việc Hoàng làm tiếp — chỉ kiểm tra truy cập, chưa gửi ảnh

Chạy trên máy đã có phiên AWS của Hoàng. Không gửi access key/secret/token vào
chat hoặc repository. Nếu profile có tên khác, thay tên profile trong cả hai
lệnh; `--expected-user hoang` phải giữ nguyên.

```powershell
aws sts get-caller-identity --profile homewallet-d3-pilot --query Arn --output text
```

Kết quả phải là `arn:aws:iam::179923444714:user/hoang`. Nếu chưa có profile,
dùng cách đăng nhập AWS hiện có của nhóm để cấu hình phiên Hoàng; không tạo
access key mới chỉ để vượt qua bước này.

Từ thư mục gốc repo, với OCR virtualenv đã cài `ocr-lab/requirements.txt`:

```powershell
.\ocr-lab\.venv\Scripts\python.exe .\ocr-lab\bedrock_access_check.py `
  --profile homewallet-d3-pilot --expected-user hoang --invoke-synthetic `
  --output .\docs\acceptance\34-bedrock-hoang-smoke-20261110.json
```

Chạy **một lần**. Kỳ vọng `status=LIVE_CALL_PASS`,
`invocation_scope=hoang_live_identity`, `runtime.http_status=200` và
`pilot_images_sent=0`. Artifact đã tồn tại sẽ chặn chạy; đọc kết quả đã lưu,
không xóa file để thử liên tục. Nếu chỉ muốn kiểm tra IAM, bỏ
`--invoke-synthetic` và dùng tên artifact riêng.

## 4. Phần cần đủ trước một benchmark mới

Hai lần `d3-pilot` và `d3-pilot-v2` đã dùng hết quyền chạy một lần. Bản v2 có
hai Gemini response JSON không hợp lệ, một 503, một Bedrock AccessDenied; không
có dự đoán hợp lệ để so sánh. Không thể phục hồi nội dung response cũ vì không
lưu raw text; chưa đủ dữ kiện kết luận vì sao JSON sai.

1. Hoàng bàn giao artifact truy cập thật ở mục 3. Tìm bản report/lock gốc trên
   máy đã chạy; các file đó không có trong checkout `main` hiện tại. Giữ số
   liệu lịch sử trong `bedrock-benchmark.md`, không tạo lại như bằng chứng mới.
2. Xác nhận quota Gemini **mới** theo đúng project/key/model trong AI Studio.
   Timestamp 08/11 trong preflight cũ đã hết hạn; model-list không chứng minh
   còn quota generate. Cần đủ RPM/TPM/RPD cho n=10 và chi phí được đối chiếu.
3. Kiên chốt một run identity mới và hạn mức riêng cho lần chạy mới, vì quyết
   định cũ cấm rerun. Không dùng lại `--run` của hai runner lịch sử. Giữ cùng
   10 ảnh `021–030`, nguồn và quyền chia sẻ đã duyệt; không mở rộng thành 42.
4. Chuẩn bị cùng bytes ảnh cho cả hai provider, ghi hash/kích thước; ảnh gốc có
   ở `ocr-lab/data`, còn `data_small` không có trong checkout này. Tạo bản chuẩn
   bị ảnh offline trước khi gửi. Không lấy dữ liệu receipt của người dùng.
5. Runner mới cần ghi finish/stop reason, số output token và lỗi schema để phân
   biệt output bị cắt với JSON sai; kiểm tra parser bằng dữ liệu tổng hợp trước.
   Giữ prompt/schema và cách chấm chung, mỗi ảnh/provider một request, không
   tự retry. Dừng khi lỗi provider/quota hoặc vượt giới hạn chi phí.
6. Báo cáo n=10: model/version/ngày/region, số request thành công/lỗi/bỏ qua,
   schema-valid coverage, độ đúng trên dự đoán hợp lệ, độ bao phủ toàn tập,
   latency và chi phí. Ghi rõ mẫu thiếu; không gọi 0/10 do lỗi là độ chính xác
   OCR của model. Không dùng benchmark nhỏ để tự đổi provider production.

Khi có report hợp lệ theo cặp và Kiên review kết quả/giới hạn, mới chốt #34.
Nếu nhóm giữ quyết định không gửi ảnh thêm, ghi **PARTIAL với giới hạn**, không
đánh dấu benchmark PASS từ mô phỏng IAM hoặc phép thử văn bản.
