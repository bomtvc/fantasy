---
type: "manual"
---

# rule.md — Quy tắc làm việc cho “augment code” trong VS Code

## Mục tiêu
- Thực hiện chỉnh sửa/mở rộng mã nguồn một cách an toàn, có kiểm soát.
- Tránh để lại rác thử nghiệm và **không** tạo thêm các tệp tóm tắt/hướng dẫn.

---

## Phạm vi áp dụng
- Tất cả thao tác “augment code” trong VS Code đối với kho mã này.
- Áp dụng cho mọi ngôn ngữ, mọi thư mục trừ khi có quy định cụ thể khác trong dự án.

---

## Nguyên tắc chung
1. **Tối thiểu hoá thay đổi ngoài phạm vi yêu cầu.**
2. **Không thay đổi API/public interface** trừ khi có chỉ định.
3. **Giữ nguyên format & style** hiện có (tuân thủ `.editorconfig`, formatter, linter nếu có).
4. **Ghi rõ lý do chỉnh sửa trong commit message** (ngắn gọn, có ngữ cảnh).

---

## Thử nghiệm & Dọn dẹp (bắt buộc)
- Được phép tạo **tạm thời** các tệp/thu mục phục vụ thử nghiệm, nhưng **phải xóa sau khi hoàn tất**.
- Sau khi test xong, **xóa các tệp/thư mục** sau (nếu được tạo trong quá trình augment):
  - Thư mục: `test/`, `tests/`, `__tests__/`, `tmp/`, `temp/`, `.temp/`, `.cache/`, `.pytest_cache/`, `coverage/`, `playground/`, `sandbox/`, `.vite/`, `dist-test/`
  - Tệp: `*.test.*`, `*.spec.*`, `*.snap`, `*.log`, `*.tmp`, `*.swp`, `*.bak`, `*.orig`, `coverage.*`, `jest.config.*` (tạo tạm), `vitest.config.*` (tạo tạm)
- Không để lại dữ liệu mẫu/rác:
  - `mock_*.*`, `sample_*.*`, `example_*.*`, `fixtures/**` (nếu chỉ dùng tạm để thử).
- Nếu cần giữ lại quy trình test chính thức của dự án, **chỉ dùng cấu hình sẵn có**; không để lại cấu hình test phụ/trùng lặp.

> Gợi ý: có thể thêm các pattern trên vào `.gitignore` trong **nhánh làm việc** nếu cần, nhưng trước khi merge phải đảm bảo không còn rác thử nghiệm.

---

## Tuyệt đối **không tạo** các tệp sau
- Tệp tóm tắt/hướng dẫn ở bất kỳ dạng nào, ví dụ:
  - `SUMMARY.md`, `TLDR.md`, `FINAL_SUMMARY.md`, `SUMMARY.txt`
  - `HUONG_DAN.md`, `INSTRUCTIONS.md`, `GUIDE.md`, `README-AUGMENT.md`
  - `KET_LUAN.md`, `TONG_KET.md`, `REPORT.md`
- **Không** tạo “tóm tắt cuối cùng” hay bất kỳ tài liệu tổng hợp hướng dẫn mới.
- Ghi chú (nếu cần) đặt **trong commit message** hoặc **comment inline** (PR review), **không** ở file riêng.

---

## Ghi log & tài liệu
- Dùng **commit message chuẩn**:
  - Cấu trúc: `type(scope): mô tả ngắn gọn` (ví dụ: `fix(auth): tránh crash khi refresh token`)
  - Thêm chi tiết kỹ thuật/ngữ cảnh ở phần thân commit nếu cần.
- **Không** viết nhật ký dài dòng vào repo; nếu cần, dùng mô tả PR.

---

## Kiểm tra trước khi kết thúc
- [ ] Chạy linter/formatter: không còn lỗi.
- [ ] Chạy test sẵn có (nếu dự án có): xanh.
- [ ] **Đã xóa toàn bộ file/folder test, temp, thử nghiệm** tạo trong quá trình làm.
- [ ] **Không có tệp tóm tắt/hướng dẫn mới** được thêm.
- [ ] Không thay đổi API/public interface ngoài yêu cầu.
- [ ] Commit message rõ ràng, có ngữ cảnh.

---

## Lưu ý bảo trì
- Ưu tiên thay đổi cục bộ, tránh lan sang module không liên quan.
- Giữ tương thích ngược khi có thể.
- Trước khi sửa lớn, cân nhắc mở PR nhỏ, độc lập, dễ review.

