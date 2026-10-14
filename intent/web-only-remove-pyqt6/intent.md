# Intent: Remove PyQt6 and use the web application

**Project:** novel-pipeline-v2

**Status:** Approved — owner approval, 2026-10-13; implementation pending

**Source:** Yêu cầu của owner ngày 2026-10-13; owner xác nhận bỏ desktop PyQt6 và giữ CLI như công cụ nội bộ.

**Evidence:** Đọc tĩnh repository tại HEAD `36a1dd71685f19d70bb9a7f81b32d5c271f45333`, branch `codex/lesson9-eval-ci`. Chưa chạy application, build hoặc test trong lượt này.

## 1. Problem — Vấn đề

Repository hiện duy trì hai giao diện: web React/FastAPI và desktop PyQt6.
Owner muốn sử dụng web làm giao diện ứng dụng duy nhất, bỏ dependency và code
desktop PyQt6, đồng thời giữ CLI để phục vụ công việc nội bộ.

PyQt6 không chỉ xuất hiện ở entry point desktop: nhiều tests phụ thuộc GUI,
và một số file trộn kiểm thử core với kiểm thử Qt. Vì vậy, chỉ xóa dependency
hoặc bỏ qua toàn bộ các file test này có thể làm mất coverage nghiệp vụ còn cần
cho web app. Đây là rủi ro suy ra từ mã, chưa phải regression đã quan sát.

Tài liệu hiện còn yêu cầu giữ desktop đến khi xác minh parity TTS/video/YouTube.
Việc chuyển sang web-only cần chốt bằng chứng cần có và cập nhật hướng dẫn hiện
hành; chưa có căn cứ trong lượt này để khẳng định web đã đạt đầy đủ parity.

## 2. Evidence — Bằng chứng đã xác minh

Đường dẫn và dòng dưới đây thuộc checkout đã đọc; phải kiểm tra lại trước implementation.

| Thông tin | Bằng chứng |
| --- | --- |
| Entry point desktop sử dụng QApplication, QTimer và MainWindow. | `app.py:7`, `app.py:14` |
| Dependency desktop được tách riêng; requirements web tham chiếu core. | `requirements-desktop.txt:1–3`, `requirements.txt:1–6` |
| Web có entry point FastAPI chạy loopback và frontend React/Vite. | `backend/__main__.py:7–14`, `backend/app.py:13–24`, `frontend/package.json` |
| Media service có các action chuẩn bị TTS, thumbnail, video và YouTube; sự tồn tại của action chưa chứng minh runtime thành công. | `pipeline/media_service.py:1–5`, `pipeline/media_service.py:22–28` |
| Các test web/headless đã tồn tại. | `tests/test_web_api.py:19`, `tests/test_web_jobs.py:1`, `tests/test_headless_media.py:22` |
| Có test trộn core/media và Qt trong cùng file. | `tests/test_tts_preprocessing.py:352–375`, `tests/test_video_pages.py:406–414` |
| Guidance còn giữ desktop cho đến khi có bằng chứng parity thực tế. | `CLAUDE.md:35`, `INSTALL.md:64`, `INSTALL.md:94–97` |
| Google OAuth loại Desktop app được dùng qua media service; đây là hợp đồng OAuth, không phải dependency GUI PyQt6. | `pipeline/media_service.py:499–504`, `media/youtube_auth.py:109–126`, `tests/test_youtube_auth.py:71–78` |
| CLI có entry point độc lập. | `pipeline/__main__.py:1–4` |

**Chưa xác minh:** ma trận đầy đủ chức năng desktop/web, mọi phụ thuộc gián tiếp
vào Qt, kết quả test hiện tại, khả năng chạy trong môi trường không cài PyQt6,
khả năng phục hồi sessions/artifacts thực tế và parity với dịch vụ bên ngoài.

## 3. Outcome — Kết quả mong muốn

- Web app là giao diện duy nhất được hỗ trợ cho người dùng.
- Không cần cài PyQt6 hoặc cấu hình Qt để cài đặt, chạy web và chạy tập tests
  được giữ lại cho sản phẩm web/core.
- Không còn entry point hoặc code desktop PyQt6 trong phiên bản được hỗ trợ.
- CLI `python -m pipeline` vẫn hoạt động như công cụ nội bộ; core tiếp tục phục
  vụ cả HTTP và CLI mà không phụ thuộc GUI.
- Các nghiệp vụ web được owner chấp nhận giữ lại tiếp tục hoạt động: nhập và
  xử lý chương, grouping/editing, settings/sessions, TTS, thumbnail, video và
  YouTube, bao gồm failure, cancel, retry/resume và provenance tương ứng.
- Coverage cho hợp đồng dữ liệu và nghiệp vụ còn được hỗ trợ được bảo toàn;
  hướng dẫn sử dụng/kiểm thử hiện hành thống nhất với web-only.

## 4. Scope — Phạm vi

**Trong phạm vi:**

- Rà soát phụ thuộc PyQt6 và phân loại code/test chỉ dành cho desktop với code
  hoặc assertions còn cần cho web/core.
- Loại bỏ giao diện desktop, entry point và dependency PyQt6 sau khi các điều
  kiện kiểm chứng được phê duyệt đã được đáp ứng.
- Bảo toàn hoặc chuyển coverage nghiệp vụ từ các tests có Qt sang kiểm thử
  phù hợp cho web/core; không xóa coverage chỉ để collection thành công.
- Điều chỉnh tối thiểu tài liệu hiện hành, guidance và cấu hình kiểm thử/cài
  đặt bị ảnh hưởng. Danh sách file cụ thể thuộc Spec/Plan sau này.
- Ghi nhận gap desktop/web và trình owner quyết định nếu gap ảnh hưởng đến
  chức năng cần giữ; không âm thầm loại bỏ hoặc xây thêm chức năng.

**Ngoài phạm vi:**

- Xóa CLI nội bộ, viết lại core, thay thuật toán số Hán/chunking/TTS hoặc thiết
  kế lại giao diện web ngoài nhu cầu chuyển đổi đã được duyệt.
- Chuyển thành dịch vụ public/multi-user, đổi authentication hay triển khai cloud.
- Đổi OAuth client Google từ Desktop app sang Web application chỉ vì bỏ Qt.
- Xóa/migrate dữ liệu người dùng, cấu hình thật, tài khoản hoặc artifacts.
- Tiếp tục Eval Bài 9, xây Orchestrator hoặc viết lại các báo cáo lịch sử.

## 5. Constraints — Ràng buộc

- Bảo toàn source/canonical text, thứ tự chương và hợp đồng transformations;
  giữ provenance, resume và kiểm tra tính hợp lệ của media artifacts.
- Giữ tương thích dữ liệu settings/sessions/artifacts đang được hỗ trợ; nếu
  phát hiện cần migration, phải có quyết định phạm vi riêng trước khi thực hiện.
- Không xóa helper Qt-free chỉ vì tên có chữ `legacy` hoặc `desktop`; xác minh
  callers và nhu cầu tương thích trước khi quyết định số phận của nó.
- Giữ API local-only và cơ chế lưu credentials an toàn hiện có. Không đọc hoặc
  ghi lộ `.env`, secrets, tokens, API keys hay dữ liệu truyện thật.
- Regression tự động dùng fixtures/fake providers, cấu hình và output tạm.
  Kiểm chứng provider thật/tài khoản thật cần được owner cho phép riêng.
- Không coi skip toàn bộ tests có Qt, build thành công hoặc fixture media là
  bằng chứng đầy đủ về chất lượng web hay parity dịch vụ thật.
- Bảo toàn thay đổi chưa commit và các worktrees; không reset/stash/ghi đè
  công việc khác. Thay đổi phải review được và rollback chỉ phần được phép.

## 6. Success criteria — Tiêu chí thành công

| ID | Tiêu chí cần chứng minh trước nghiệm thu |
| --- | --- |
| S1 | Cài đặt và chạy web trong môi trường không có PyQt6; truy cập được giao diện và API theo hướng dẫn. Không cần Qt/display/offscreen configuration. |
| S2 | Code được giữ lại không import PyQt6/UI desktop; dependency được hỗ trợ không kéo PyQt6 vào. Desktop entry point bị loại bỏ và tài liệu không còn hướng dẫn người dùng chạy nó. |
| S3 | CLI nội bộ vẫn khởi động và thực hiện một tác vụ core với fixture, không cần PyQt6. |
| S4 | Tập regression web/core được chốt ở Spec được collect và chạy không có Qt; các assertions quan trọng từ tests hỗn hợp được giữ hoặc thay bằng coverage tương đương, có traceability. |
| S5 | Các workflow web được owner chốt có bằng chứng success và failure/recovery phù hợp; ghi rõ phần offline, phần tích hợp thật và phần chưa kiểm chứng. |
| S6 | Fixtures xác nhận source/canonical text, formats, provenance và khả năng phục hồi sessions/artifacts không bị thay đổi ngoài phạm vi. Không dùng dữ liệu thật để chứng minh. |
| S7 | Hướng dẫn cài/chạy/test và quy tắc dự án phản ánh web-only; việc dùng Google Desktop app OAuth không bị loại bỏ nhầm. |
| S8 | Có báo cáo với commands, interpreter/dependencies, checkout, results, failures/skips và gaps; có human approval trước nghiệm thu hoặc merge. |

Các tiêu chí trên là yêu cầu tương lai; chưa có tiêu chí nào được xác nhận bằng
thực thi trong lượt tạo Intent này.

## 7. Owner decisions và Open questions

**Đã được owner xác nhận:** bỏ desktop PyQt6; giữ web làm giao diện ứng dụng;
giữ CLI như công cụ nội bộ.

**Approval record:** Owner phê duyệt bản Intent này bằng phản hồi `approved`
ngày 2026-10-13. Phạm vi, ràng buộc và tiêu chí thành công được phê duyệt;
phản hồi này không tự giải quyết các câu hỏi dưới đây hoặc cho phép xóa code.

1. **Product Owner:** Những chức năng desktop nào phải có trên web trước khi
   bỏ Qt? Chức năng chỉ tồn tại ở desktop, nếu có, được bổ sung hay bỏ có chủ đích?
2. **Product Owner / QA:** Bằng chứng nào đủ để thay chính sách giữ desktop hiện
   có? Có yêu cầu kiểm chứng TTS/video/YouTube thật trước khi xóa hay chấp nhận
   mức offline/integration cụ thể và ghi nhận giới hạn?
3. **Technical Lead:** Những tests/assertions hỗn hợp, helpers và callers nào
   cần giữ/chuyển? Chốt inventory, coverage mapping và regression set trong Spec.
4. **Product Owner / Technical Lead:** Phạm vi tương thích sessions/artifacts và
   hệ điều hành cần nghiệm thu là gì? Không mặc định mọi nền tảng đã được kiểm tra.

## 8. Authorization — Phạm vi phê duyệt

Intent đã được owner phê duyệt. Bước tiếp theo là lập Spec/Plan, giải quyết các
câu hỏi còn mở và xin phê duyệt kế hoạch triển khai. Phê duyệt Intent không tự
cho phép xóa source, thay dependencies, chạy build/test, commit, push, merge
hoặc deploy.
