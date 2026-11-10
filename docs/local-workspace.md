# Thư mục làm việc sau khi hợp nhất ngày 10/11/2026

## Mở dự án ở đâu?

Tiếp tục mở **`homewallet-gr13`**, nhánh **`main`**, trong VS Code.
Mã #42, cấu hình VAPID, script runtime và bằng chứng #43 hiện có ở thư mục này.

- [Biên bản nghiệm thu #43 đã hoàn tất](acceptance/43-final-acceptance-20261110.md).
- [Kết quả SES/Scheduler và quy trình email E2E](acceptance/43-delivery-20261110.md).
- [Ma trận CM01–CM16](acceptance/43-cognito-email.md).
- [Trạng thái công việc của Chi](acceptance/chi-week10-status-20261109.md).
- [Biên bản D4/#36 đã đóng](acceptance/36-d4-evidence.md).
- [Rà soát việc nhóm còn lại](acceptance/team-open-work-20261110.md).
- [Khắc phục Bedrock/#34 và bước hoàn tất](acceptance/34-bedrock-remediation-20261110.md).
- [Nghiệm thu ngân sách #25/#37](acceptance/25-37-budget-20261110.md).

Các thư mục có hậu tố là Git worktree cho từng nhánh công việc. Nhánh ở các
worktree sau đã được hợp nhất vào `main` local:

| Worktree | Nhánh |
| --- | --- |
| `homewallet-gr13-42-43-locale` | `feat/42-43-cognito-locale-sync` |
| `homewallet-gr13-chi-acceptance` | `docs/chi-week10-acceptance` |
| `homewallet-gr13-fix32-runtime-db-credentials` | `fix/32-runtime-db-credentials` |
| `homewallet-gr13-fix33-monitoring-plan-safety` | `test/36-kien-ac3-load-evidence` |
| `homewallet-gr13-fix-d3-cross-region-policy` | `fix/d3-cross-region-bedrock-policy` |
| Worktree IAM Hoàng trong Temp | `fix/hoang-integration-test-s3-policy` |

Tên thư mục `fix33` được giữ từ trước; nhánh đang ở đó là bằng chứng D4/#36.
Các worktree cũ vẫn được giữ. Chọn thư mục `homewallet-gr13` cho công việc tiếp.

## Sao lưu và file riêng

Bản sao lưu ở thư mục ngang cấp **`_sao_luu_git_20261110-142452`**:

- `repository.bundle`: lịch sử Git trước hợp nhất.
- `manifest.json`: danh sách worktree, file và SHA-256 của bản sao.
- Các thư mục `*/files`: nội dung file chưa commit trước hợp nhất.
- `main-restoration.json`: file đã khôi phục và bản nháp được lưu trữ.
- `ignored-config/frontend.env.local.before`: cấu hình frontend trước khi bổ
  sung public VAPID key. File `.env.local` vẫn được Git ignore.

Git còn giữ nhánh `backup/main-before-consolidation-20261110` và stash
`b316fce1314eabfb3b8b7df6ac60efab40060e63` chứa các file local của main trước
hợp nhất. Không cần apply stash lên bản mới vì các file đã được khôi phục riêng.

Bản nháp D4 local được giữ tại
[archive/36-d4-evidence-local-before-consolidation-20261110.md](acceptance/archive/36-d4-evidence-local-before-consolidation-20261110.md).
Biên bản D4 hiện hành giữ quyết định đóng của nhóm và bằng chứng đầy đủ hơn.
Hai file Word hướng dẫn vẫn được giữ ở vị trí cũ, chỉ lưu local và được Git
ignore theo yêu cầu của người dùng; không đưa vào các commit sẽ push.
`hw33-receipt-probe.json` đã được đưa vào Git cùng các file công việc khác.

## Phạm vi

Việc hợp nhất này cập nhật repository local. #43 đã PASS trong phạm vi nghiệm
thu đã chốt, gồm hộp thư/nội dung/mã thật và xác nhận nhận push từ job.
Biên bản, artifact và cleanup đã hoàn tất; việc push lên GitHub do người dùng
thực hiện theo hướng dẫn tiếp theo. File Word hướng dẫn tuần chỉ giữ local.
