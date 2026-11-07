# D2 / #29 — Các bước kiểm chứng và bàn giao

Nhánh: `feat/29-community-admin-api`. Contract: [community-api.md](community-api.md).
Ngày chuẩn bị: 2026-11-07. **Local đã kiểm thử; dev/CI remote và xác nhận contract còn chờ.**

## Bước 1 — Review contract

Hoàng gửi link contract trong PR để Kiên/Thức xác nhận. Bản hướng dẫn tuần 10
không chứa mục 2 nên chưa được coi tài liệu mới là contract đã thống nhất.
Cần chốt user chưa có household, các chuyển status, author null, mẫu ngân sách
dạng text và audit chung `COMMUNITY_POST_UPDATED`.

## Bước 2 — Chạy test local không cần AWS

Từ root repo, PowerShell:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_community.py -q -p no:cacheprovider
Pop-Location
```

Nếu chưa có môi trường backend, tạo virtualenv và cài `backend/requirements-dev.txt`.
Không dùng virtualenv của ocr-lab. Bộ này verify JWT ký bằng RSA test, stub hồ sơ
user và chặn truy cập DB ở các ca bị từ chối. Không gọi Cognito thật.

## Bước 3 — Chạy MySQL 8.4 riêng

Các lệnh dưới đây tạo container test không mount volume. Mật khẩu trong ví dụ
chỉ dành cho database local tạm. Không dùng cấu hình RDS hay database cá nhân.

```powershell
docker run --detach --rm --name homewallet-d2-mysql --publish 127.0.0.1:13307:3306 --env MYSQL_ROOT_PASSWORD=d2-local-test-only mysql:8.4
docker exec homewallet-d2-mysql mysqladmin ping -h localhost -pd2-local-test-only
```

Chờ `mysqld is alive` rồi chạy trong một terminal PowerShell dành riêng cho test:

```powershell
$env:HOMEWALLET_COMMUNITY_MYSQL = '1'
$env:HOMEWALLET_TEST_DB_HOST = '127.0.0.1'
$env:HOMEWALLET_TEST_DB_PORT = '13307'
$env:HOMEWALLET_TEST_DB_USER = 'root'
$env:HOMEWALLET_TEST_DB_PASSWORD = 'd2-local-test-only'
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_community.py tests/test_community_mysql.py -ra -p no:cacheprovider
$d2ExitCode = $LASTEXITCODE
Pop-Location
Write-Output "D2 exit code: $d2ExitCode"
docker stop homewallet-d2-mysql
```

Fixture MySQL chỉ chấp nhận localhost/127.0.0.1, tạo tên database ngẫu nhiên
`hw_d2_<uuid>_test`, chạy SQL migration trong database đó và drop đúng database
này khi test xong. Lệnh CREATE DATABASE/USE homewallet trong migration 001 bị bỏ
qua. Không gọi `jobs.migrate` trực tiếp cho test vì job đó chọn DB `homewallet`.

Khi opt-in `HOMEWALLET_COMMUNITY_MYSQL=1`, lỗi kết nối hoặc migration là **FAIL**,
không skip. Khi không opt-in, sáu ca MySQL được skip có lý do.
CI có job `Community authorization and MySQL acceptance` dùng MySQL 8.4 và opt-in;
phải xem kết quả job này, không chỉ job backend chung.

## Ma trận kiểm tra

| ID | Ca | Kỳ vọng | Bằng chứng local | Dev |
| --- | --- | --- | --- | --- |
| D2-01 | Thiếu token trên cả bốn endpoint | 401 | `test_all_routes_require_auth` PASS | Chờ |
| D2-02 | Member/role owner/admin tự khai báo/group sai | GET/PATCH admin 403 | `test_only_exact_verified_group_grants_admin` PASS | Chờ |
| D2-03 | Token sửa payload, hết hạn, sai issuer/client, ID token | 401 dù khai group admin | Các test JWT trong `test_community.py` PASS | Chờ |
| D2-04 | POST hợp lệ cho hai type, kể cả admin gửi bài | 201, PENDING, trim, đúng giới hạn | Test lifecycle/boundaries MySQL PASS | Chờ |
| D2-05 | Tự gửi status/author/household/role/group; tự nâng qua /me | 422, không cấp quyền | Test validation/self-promote PASS | Chờ |
| D2-06 | Member đọc feed với status=PENDING/HIDDEN/ALL | Chỉ APPROVED | Test lifecycle MySQL PASS | Chờ |
| D2-07 | Admin không filter/filter từng trạng thái | Đủ dữ liệu, đúng sort | Test filters/order MySQL PASS | Chờ |
| D2-08 | Duyệt/sửa/ẩn/đưa lại PENDING | Feed phản ánh trạng thái và nội dung | Test lifecycle MySQL PASS | Chờ |
| D2-09 | JSON sai, thiếu/thừa trường, sai kiểu/giới hạn/status | 400/422; không ghi bài | Test validation PASS; invalid PATCH MySQL PASS | Chờ |
| D2-10 | Admin PATCH ID không tồn tại | 404, không audit | Test missing post MySQL PASS | Chờ |
| D2-11 | Audit cho mỗi create/PATCH thành công | Đúng actor/action/entity/time; không body/email/dữ liệu hộ | Test private audit MySQL PASS | Chờ DB |
| D2-12 | Ghi audit thất bại sau insert/update | Bài và audit cùng rollback | Hai test fault injection MySQL PASS | Local đủ; không phá DB dev |
| D2-13 | Tác giả thiếu display_name | author=null; không fallback email ở POST/GET/PATCH | Test author privacy MySQL PASS | Chờ |
| D2-14 | POST route mock trên backend | 404, không nâng quyền | Test mock endpoint PASS | Chờ |
| D2-15 | Script nghiệm thu với API và MySQL thật local | 16 checks pass; bài test kết thúc HIDDEN | Test evidence runner MySQL PASS | Chờ |
| D2-16 | UI member/admin, refresh token, sửa localStorage | UI đúng quyền; backend vẫn chặn truy cập trái quyền | Lint; cần kiểm tra trình duyệt | Chờ Thức |

Các test authorization mô phỏng role owner trong user profile để kiểm tra role đó
không thay thế group. Nghiệm thu dev vẫn cần tài khoản household owner thực tế.

## Bước 4 — Chuẩn bị group, migration và deploy dev

- Chi review resource `module.cognito.aws_cognito_user_group.community_admins`.
  Module dev truyền name=`homewallet-dev`, nên group là `homewallet-dev-admins`.
  Không gắn IAM role và không tự thêm user trong Terraform.
- Kiên kiểm tra account/region/state, review plan, apply từ main theo quy trình nhóm.
  Nếu group đã được tạo thủ công, Kiên xử lý import vào state trước khi apply;
  không tạo group khác để né trùng tên.
- Kiên thêm đúng tài khoản dev được chọn; lưu bằng chứng danh sách thành viên
  đã che định danh. Tài khoản member dùng kiểm thử không thuộc group.
- Xác nhận backend image chứa community blueprint và migration
  `005_community_posts.sql` đã được áp dụng. Lưu commit/image và thời điểm deploy.
- Đăng nhập lại để lấy access token mới. Backend verify JWT offline nên thay đổi
  membership không làm token cũ tự mất claim ngay; không kỳ vọng thu hồi tức thì
  trên token đã cấp. Kiểm tra member/admin với token mới.

Các bước AWS này **chưa chạy** trong lần chuẩn bị local. Terraform validate không
phải bằng chứng plan/apply, group tồn tại hay user đã có quyền.

## Bước 5 — Chạy bằng chứng HTTP trên dev

Script [verify-d2-community.py](../scripts/verify-d2-community.py) tạo **một bài
synthetic**, duyệt/sửa/ẩn và luôn cố ẩn lại khi kết thúc. Không xóa bài/audit.
Script đọc token từ env, không nhận token qua command line, không in response body,
email hay token. Dùng HTTPS cho dev; HTTP chỉ được dùng với localhost.

Nhập token trong terminal riêng bằng prompt ẩn (không dán vào command history):

```powershell
$d2MemberSecret = Read-Host 'Member access token' -AsSecureString
$d2AdminSecret = Read-Host 'Admin access token' -AsSecureString
$env:HOMEWALLET_D2_MEMBER_TOKEN = [System.Net.NetworkCredential]::new('', $d2MemberSecret).Password
$env:HOMEWALLET_D2_ADMIN_TOKEN = [System.Net.NetworkCredential]::new('', $d2AdminSecret).Password
try {
  python scripts/verify-d2-community.py --base-url https://YOUR-DEV-API-ORIGIN
  Write-Output "D2 dev exit code: $LASTEXITCODE"
} finally {
  Remove-Item Env:HOMEWALLET_D2_MEMBER_TOKEN, Env:HOMEWALLET_D2_ADMIN_TOKEN -ErrorAction SilentlyContinue
  Remove-Variable d2MemberSecret, d2AdminSecret -ErrorAction SilentlyContinue
}
```

Thay origin bằng môi trường dev đã deploy, không dùng production. Chạy với
`VITE_USE_MOCK=0` khi kiểm tra UI. Nếu `cleanup-hide` FAIL, Hoàng/Kiên dùng admin
ẩn thủ công đúng `post_id` được trả về và ghi nhận lỗi; không chạy đi chạy lại vô hạn.

`status=PASS` chỉ có nghĩa các HTTP checks pass. `audit_status` cố ý vẫn là
`PENDING_DB_VERIFICATION`: bước tiếp theo phải kiểm tra DB thật.

## Bước 6 — Đối chiếu audit và hoàn tất evidence

Qua kết nối DB dev đã được nhóm cấp quyền, thay `123` bằng post_id synthetic:

```sql
SELECT id, actor_id, action, entity, entity_id, at
FROM audit_logs
WHERE entity = 'community_post' AND entity_id = 123
ORDER BY id;
```

Một lần script thành công có 5 dòng: 1 CREATED của member, 4 UPDATED của admin
(approve, edit, hide, cleanup-hide). Lần PATCH hide cuối vẫn ghi audit dù status
đã là HIDDEN; đây là semantics đã ghi trong contract. So actor_id với hai user
test bằng phiên DB riêng; không đưa token/email vào evidence.

Lưu các mục sau trong PR/báo cáo nhóm:

- Commit/image, môi trường, ngày giờ, người chạy, command và exit code.
- JSON script, request IDs, post_id, các dòng audit đã làm sạch.
- Bằng chứng migration 005/group membership và kiểm tra UI member/admin.
- Kiên/Thức xác nhận contract; lỗi còn lại có owner và quyết định xử lý.

## Kết quả local ngày 2026-11-07

| Kiểm tra | Kết quả | Giới hạn |
| --- | --- | --- |
| `test_auth.py` + `test_community.py` | 87 passed | RSA test, không gọi Cognito |
| Ba file D2/auth, bật MySQL 8.4 | 93 passed, exit 0 | 6 integration tests; DB local riêng |
| Backend regression, bật MySQL D2 | 167 passed, 44 skipped, exit 0 | 44 ca DB cũ cần `homewallet_test` riêng; toàn bộ ca D2 đã chạy |
| Terraform fmt / validate dev | PASS | Chưa plan/apply |
| Frontend lint | PASS | Không phải UI acceptance |
| Frontend tests / production build | 72 passed / PASS, exit 0 | Không thay thế UI acceptance trên dev |
| CI remote / AWS dev / review contract | Chưa chạy / chờ | Không đánh dấu D2 Done |

Đóng D2 sau khi contract được xác nhận, CI mới xanh, các ca dev bắt buộc pass,
audit được đối chiếu và không có khả năng user tự nâng quyền.
