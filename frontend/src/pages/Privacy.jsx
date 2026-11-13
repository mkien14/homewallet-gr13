import { Link } from "react-router-dom";
import { usePreferences } from "../preferences";
import { config } from "../config";

export default function Privacy() {
  const { t } = usePreferences();
  return <section className="card privacy-page">
    <p className="eyebrow">HomeWallet · 12/11/2026 · v1</p>
    <h1>{t("Quyền riêng tư và dữ liệu")}</h1>
    <h2>{t("Thông tin được lưu")}</h2>
    <p>{t("HomeWallet lưu thông tin tài khoản, thành viên hộ, giao dịch, ngân sách, hóa đơn và cài đặt thông báo để cung cấp các chức năng bạn sử dụng.")}</p>
    <h2>{t("Xử lý hóa đơn và gợi ý")}</h2>
    <p>{t("Khi bạn đồng ý tải hóa đơn, nội dung tệp có thể được gửi tới Google Gemini hoặc Amazon Textract để đọc và tạo bản nháp. Chỉ tải tài liệu bạn có quyền sử dụng; hãy che thông tin không cần thiết trước khi gửi.")}</p>
    <p>{t("Gợi ý ngân sách có thể dùng số liệu chi tiêu tổng hợp và tên danh mục với Gemini. Gợi ý và bản nháp cần được bạn kiểm tra; chỉ thao tác xác nhận hoặc lưu mới ghi nhận thay đổi nghiệp vụ.")}</p>
    <h2>{t("Phạm vi chia sẻ")}</h2>
    <p>{t("Dữ liệu chi tiêu được chia sẻ với các thành viên trong hộ theo quyền của họ. Bài cộng đồng đã duyệt có thể được người dùng đã đăng nhập xem. Đừng đăng dữ liệu tài chính riêng tư trong bài cộng đồng.")}</p>
    <h2>{t("Xóa và xuất dữ liệu")}</h2>
    <p>{t("Bạn có thể xóa hóa đơn theo quyền của mình. Chủ hộ có thể xuất dữ liệu và yêu cầu xóa hộ trong phần quản lý hộ. Rời hộ không xóa các giao dịch đã đóng góp cho hộ. Dữ liệu sao lưu hết hạn theo chính sách sao lưu và không được dùng cho hoạt động thông thường.")}</p>
    <h2>{t("Thông báo và hỗ trợ")}</h2>
    <p>{t("Bạn có thể tắt Web Push trên thiết bị trong mục Thông báo. Email xác minh tài khoản phục vụ bảo mật. Liên hệ nhóm vận hành để yêu cầu hỗ trợ về tài khoản hoặc dữ liệu.")}</p>
    <p><a href={`mailto:${config.supportEmail}`}>{config.supportEmail}</a></p>
    <p><Link to="/">{t("Quay về trang chủ")}</Link></p>
  </section>;
}
