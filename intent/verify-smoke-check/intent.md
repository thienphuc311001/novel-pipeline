# Intent: Make smoke-check failures observable

**Project:** novel-pipeline-v2
**Status:** Approved — implementation pending
**Source:** Read-only SDLC repository assessment and intent review
**Evidence status:** Static inspection only; no tests executed in this review

## 1. Problem — Vấn đề

Smoke check số Hán trong `verify.py` so sánh kết quả thực tế với
kỳ vọng và in dấu thành công/thất bại, nhưng vẫn trả về `True`
khi phép so sánh sai và không phát sinh exception.

Vì vậy, nếu kết quả chuyển đổi khác kỳ vọng, lỗi có thể không
được phản ánh trong tổng kết và exit code của lần chạy script.

`main()` đã có cơ chế trả exit code khác 0 khi một smoke check
báo thất bại hoặc phát sinh exception. Vấn đề đã xác minh là
smoke check số Hán không truyền tín hiệu thất bại khi kết quả
khác kỳ vọng.

Thông báo thành công hiện chứa “Application is ready”, trong
khi các kiểm tra của script chỉ bao phủ một phần chức năng core.

Việc đọc mã xác nhận cơ chế false positive; chưa xác nhận rằng
thuật toán chuyển đổi số Hán đang trả sai trên checkout hiện tại.

Phiên đánh giá này chưa chạy test. Các kết quả được ghi trong
tài liệu chưa được đối chiếu với checkout đang sử dụng.

## 2. Proposed outcome — Kết quả mong muốn

Phạm vi đã được owner phê duyệt cho vòng thay đổi này là tín hiệu
của smoke check số Hán và thông báo tổng kết của `verify.py`.

- Một case đạt khi kết quả thực tế khớp kỳ vọng, bao gồm `None`
  nếu đó là kết quả từ chối đầu vào được kỳ vọng.
- Bất kỳ case số Hán nào có kết quả khác kỳ vọng phải khiến
  smoke check số Hán được ghi nhận là thất bại.
- Thất bại đó phải xuất hiện trong tổng kết và khiến tiến trình
  trả exit code khác 0.
- Giữ hợp đồng hiện có: khi các smoke checks được chạy đều báo
  thành công, tiến trình trả exit code 0; khi có kiểm tra báo
  thất bại hoặc phát sinh exception, tiến trình trả khác 0.
- Thông báo cuối chỉ mô tả kết quả smoke checks, không khẳng định
  toàn bộ ứng dụng đã được kiểm chứng.
- Hành vi trong phạm vi thay đổi được bảo vệ bằng regression tests.

Việc sửa tín hiệu số Hán không đồng nghĩa các kiểm tra khác đã
được bổ sung khả năng phát hiện mọi kết quả sai.

## 3. Affected users and systems

**Người sử dụng dự kiến:** Developer, người kiểm thử và AI Coding
Agent đọc kết quả hoặc exit code của `verify.py`.

**Thành phần liên quan:**

- `verify.py`.
- Regression tests cho hành vi của script trong `tests/`.
- Tài liệu hướng dẫn xác minh, nếu owner yêu cầu cập nhật.

Vị trí tài liệu cần cập nhật chưa chốt. Hiện `STATUS.md` và
`FINAL_SUMMARY.md` có lệnh chạy `verify.py`; `INSTALL.md` hướng
dẫn chạy pytest và build frontend.

## 4. Scope — Phạm vi

Phạm vi dưới đây đã được owner phê duyệt.

**Trong phạm vi:**

- Phát hiện kết quả khác kỳ vọng trong smoke check số Hán.
- Phản ánh thất bại vào tổng kết và exit code.
- Regression tests cho đường thành công và thất bại.
- Giữ hành vi xử lý thất bại/exception hiện có.
- Làm rõ phạm vi của thông báo tổng kết.
- Cập nhật hướng dẫn xác minh tối thiểu nếu được yêu cầu.

**Ngoài phạm vi:**

- Thay đổi thuật toán hoặc quy tắc chuyển đổi số Hán.
- Sửa smoke check chunking hay các vấn đề khác của `verify.py`.
- Thay đổi giao diện React/PyQt6.
- Tích hợp AI, TTS hoặc YouTube.
- Thiết lập CI/CD hoặc chuẩn hóa test runner cho toàn repository.

## 5. Constraints — Ràng buộc

- Giữ nguyên hành vi chuyển đổi dữ liệu.
- Regression tests phải chạy offline với dữ liệu giả hoặc cố định.
- Không sử dụng dữ liệu thật, secrets hoặc tài khoản dịch vụ.
- Không loại bỏ các smoke checks và case hiện có.
- Giữ thay đổi tập trung, dễ review và có thể hoàn tác.
- Chưa chốt thuật toán xử lý kết quả, cách mô phỏng lỗi,
  tổ chức file test hoặc test runner trong intent này.

## 6. Success criteria — Tiêu chí thành công

- Khi các case số Hán hiện có khớp kỳ vọng, smoke check số Hán
  báo thành công.
- Một kết quả khác kỳ vọng, kể cả chấp nhận sai đầu vào có kỳ vọng
  `None`, khiến smoke check số Hán và tổng kết báo thất bại.
- Khi lỗi số Hán xảy ra và các kiểm tra khác báo thành công,
  tiến trình vẫn trả exit code khác 0.
- Khi tất cả smoke checks được chạy báo thành công, tiến trình
  trả exit code 0.
- Hành vi trả khác 0 khi kiểm tra báo thất bại hoặc phát sinh
  exception được giữ nguyên.
- Thông báo thành công không chứa khẳng định toàn ứng dụng sẵn sàng.
- Regression test phát hiện false positive phải thất bại vì
  hành vi lỗi trước bản vá và thành công sau bản vá.
- Có bằng chứng kiểm thử thực tế, gồm lệnh chạy, checkout được
  kiểm thử và kết quả, trước khi chấp nhận bản vá.

Các tiêu chí này chưa được xác nhận bằng thực thi trong phiên
review intent.

## 7. Open questions — Câu hỏi chưa giải quyết

### Approved owner decisions

- Vòng này chỉ sửa tín hiệu smoke check số Hán và thông báo tổng kết.
- Giữ các smoke checks khác và hợp đồng exit code hiện có.
- Thông báo chỉ báo kết quả smoke checks, không khẳng định toàn
  ứng dụng sẵn sàng.
- Chuẩn hóa test runner cho toàn repository nằm ngoài phạm vi.

### Open owner questions

1. Thông báo tổng kết cần diễn đạt kết quả smoke checks và
   giới hạn kiểm chứng như thế nào?
2. Có cần cập nhật hướng dẫn xác minh trong vòng này không?
   Nếu có, cập nhật tài liệu hiện đang hướng dẫn `verify.py`
   hay bổ sung hướng dẫn vào `INSTALL.md`?

### Technical Design questions — giải quyết sau khi duyệt phạm vi

3. Regression tests dùng runner nào phù hợp với repository?
   Có yêu cầu chạy được bằng cả pytest và unittest không?
4. Cách tổng hợp kết quả, mô phỏng lỗi, tổ chức test và kiểm tra
   exit code nào chứng minh được các tiêu chí trên?

Việc chuẩn hóa test runner cho toàn repository cần một quyết
định phạm vi riêng nếu được yêu cầu.
