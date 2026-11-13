# Rà soát PR dependency và thứ tự merge — 13/11/2026

## Phạm vi và kết quả

Đọc diff, head SHA, trạng thái merge và check runs trực tiếp từ GitHub API cho
11 PR đang mở. Main tại thời điểm rà soát là
`1bba075aa1a6dd609d180f4610fe4f55d527cbdf`. Snapshot nằm trong
[dependency-pr-review-20261113.json](dependency-pr-review-20261113.json).

Chín PR có 6/6 check thành công trên head đang mở; #124 và #126 có 5/6.
Trạng thái này không chứng minh kết quả CI sau khi ghép tất cả thay đổi.
Không merge, đóng PR, commit, push hoặc deploy dependency trong lần rà soát này.
Người vận hành thực hiện Git và merge sau khi xem diff.

## Sửa #124 và #126 trong bản local

Đã đọc log `Backend tests` của cả hai PR. Mỗi log có 221 passed, 59 skipped,
1 failed: `test_dependency_lock.py` kiểm tra SHA-256 của `requirements.txt`.
Hai PR sửa yêu cầu nhưng không cập nhật fingerprint của lock.

Lock của main đã chứa `cryptography==50.0.2` và `google-genai==3.2.0`, nên
cả hai phiên bản đều thỏa mãn yêu cầu mới. Bản local trên
`fix/production-live-rollout` nhận cả hai thay đổi:

```text
cryptography>=50.0.2
google-genai>=3.0.0
```

Đã đồng bộ SHA-256 LF trong `requirements.lock` thành
`cc4069ad47db8ff21d2902e51aa425a909a53248a8c0940d8a975e8385fde43c`.
Phần pin phiên bản và hash artifact của lock được giữ nguyên vì đây không phải
một lần resolve thư viện mới. Giữ nguyên phép kiểm tra lock, không bỏ assertion.
Kiểm tra tĩnh xác nhận mọi yêu cầu trực tiếp vẫn được lock đáp ứng.

**Sau khi PR từ nhánh local được CI thông qua và merge, đóng #124 và #126 vì
nội dung đã được thay thế. Không merge lại hai PR thiếu fingerprint này.**
Có thể ghi trong lý do đóng: “Superseded by the production rollout PR; both
requirement changes and the matching lock fingerprint are included.”

Những thay đổi này không tự bật Gemini/OCR và không đổi image đang chạy.
Không coi bằng chứng của release `1bba075` là bằng chứng triển khai commit mới.

## Thứ tự merge đề xuất

| Thứ tự | PR/nhánh | Quyết định và điều kiện |
| --- | --- | --- |
| 0 | `fix/production-live-rollout` | Commit/push bộ thay đổi local trước, mở PR vào main, chờ CI đạt rồi merge. Đây là cấu hình hạ tầng đã chạy thực tế và chứa bản sửa thay thế #124/#126. |
| 1 | [#128](https://github.com/mkien14/homewallet-gr13/pull/128) | Cognito JS SDK 3.1165.0; diff gồm package.json và lock. CI hiện 6/6; cần CI trên kết quả ghép mới. |
| 2 | [#127](https://github.com/mkien14/homewallet-gr13/pull/127) | python-dotenv cho dev, CI hiện 6/6. |
| 3 | [#125](https://github.com/mkien14/homewallet-gr13/pull/125) | pytest cho dev, CI hiện 6/6. Cùng file với #127: giữ cả pytest>=9.2.0 và python-dotenv>=1.2.4 nếu cần giải quyết conflict. |
| 4 | [#110](https://github.com/mkien14/homewallet-gr13/pull/110) | Checkout v7; đọc thay đổi hành vi với workflow đặc quyền. Repo không dùng pull_request_target/workflow_run để checkout mã PR. Giữ pin SHA trong candidate workflow. |
| 5 | [#108](https://github.com/mkien14/homewallet-gr13/pull/108) | setup-python v7; giữ Python ứng dụng 3.12, không đổi sang Python khác. |
| 6 | [#105](https://github.com/mkien14/homewallet-gr13/pull/105) | setup-terraform v4; giữ terraform_version 1.10.5. Runtime Node của action thay đổi, không phải nâng Terraform. |
| 7 | [#106](https://github.com/mkien14/homewallet-gr13/pull/106) | AWS credentials v6; không đổi role/account/OIDC permission. Có sẵn v6.3.0 ở dev và OIDC; PR chuyển chúng sang major tag v6. CI không thực hiện production assume-role. |
| 8 | [#109](https://github.com/mkien14/homewallet-gr13/pull/109) | Nâng bên đọc artifact lên v8 trước. Workflow tải theo name, không dựa vào thư mục lồng khi tải theo ID. |
| 9 | [#107](https://github.com/mkien14/homewallet-gr13/pull/107) | Nâng upload lên v7 sau bên đọc. Giữ tên/path artifact, checksum, scan và retention; giữ ZIP mặc định, không bật archive:false. |
| Sau bước 0 | [#124](https://github.com/mkien14/homewallet-gr13/pull/124), [#126](https://github.com/mkien14/homewallet-gr13/pull/126) | Đóng vì đã được thay thế, không merge. |

Các action chạy trên GitHub-hosted `ubuntu-latest`; không có self-hosted runner
cũ cần nâng riêng. Tài liệu chính thức: [Checkout v7](https://github.com/actions/checkout),
[setup-python v7](https://github.com/actions/setup-python/releases/tag/v7.0.0),
[setup-terraform v4](https://github.com/hashicorp/setup-terraform/releases/tag/v4.0.0),
[AWS credentials v6](https://github.com/aws-actions/configure-aws-credentials/releases/tag/v6.0.0),
[artifact upload/download](https://github.blog/changelog/2026-02-26-github-actions-now-supports-uploading-and-downloading-non-zipped-artifacts/).

### Cách thực hiện từng PR trên GitHub

1. Mở PR, kiểm tra base là main. Sau mỗi lần merge, cập nhật PR kế tiếp với main
   bằng **Update branch** nếu GitHub cung cấp; chờ checks của head mới hoàn tất.
2. Nếu có conflict, giữ cả thay đổi đã merge và thay đổi mới. Không chọn toàn bộ
   current/incoming khi chúng chứa hai nâng cấp khác nhau. Ví dụ file dev cuối:

   ```text
   -r requirements.txt
   pytest>=9.2.0
   python-dotenv>=1.2.4
   ```

3. Chỉ **Squash and merge** khi không còn conflict và checks thành công trên
   kết quả ghép hiện tại. CI thành công từ base cũ không thay thế lần kiểm tra này.
4. Không chạy workflow deploy trong khoảng giữa #109 và #107. Sau khi cả hai
   hoàn tất, Build release candidate trên main để kiểm tra upload, scan và đóng
   gói thực tế. Candidate thành công mới là điều kiện chuẩn bị phát hành mới.
5. Merge không tự triển khai: candidate image/frontend mới phải qua quy trình
   phát hành production có kiểm soát. Không dùng Deploy Dev lên stack đã promote,
   không apply Terraform với input dev mặc định, không bật lại lịch/OCR trong đợt này.

## Commit/push file local

Dùng danh sách file cụ thể và lệnh tại
[mục 9 runbook bàn giao](../runbooks/current-stack-production.md#9-commitpush-do-kiên-thực-hiện).
Danh sách đã bổ sung hai file dependency và biên bản này. Không stage DOCX, state,
tfvars hoặc thông tin operator trong LOCALAPPDATA. Không cần tạo thư mục repo mới.
