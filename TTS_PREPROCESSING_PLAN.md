# Kế hoạch TTS Text Preprocessing / Sanitization

## Mục tiêu

Bổ sung giai đoạn deterministic, có thể test độc lập, trước khi chia chunk để text gửi Edge TTS có ranh giới câu rõ ràng. Ưu tiên bảo toàn nghĩa, không sửa văn phong hoặc ngữ pháp bằng suy đoán.

Pipeline:

```text
TXT / Step 2 grouping source
→ clean an toàn riêng cho TTS
→ TTS text preprocessing
→ sentence-aware chunking
→ Edge TTS
→ audio
```

### Quyết định đã xác nhận

- Dùng clean profile an toàn riêng cho TTS, giữ ngoặc, quote và paragraph.
- Mặc định xóa mọi URL rõ ràng, kể cả trong lời kể. Bare domain được giữ và bảo vệ khỏi punctuation rules.
- Email giữ mặc định; hỗ trợ remove/keep/replace.
- Không ghi đè source TXT, Step 2 hoặc canonical TXT/JSON của nhóm chương.
- Không dùng AI/LLM, không thêm dependency mạng cho preprocessing.
- Dùng target chunk TTS hiện tại là 700 ký tự; giá trị cấu hình cũ được giữ để tương thích nhưng không thay đổi target pipeline.
- Kiểm thử dùng unittest hiện có, không yêu cầu pytest hoặc Hypothesis.

## Hiện trạng trước triển khai

- Luồng nhóm chương chuẩn bị text tại `media/groups.py::prepare_tts`, Step 2 chỉ nhóm và xuất canonical files.
- Luồng cũ clean/chunk tại `MainWindow._on_clean_chunk`, TTS đọc bundle TXT/JSON dẫn xuất.
- Regex sentence/clause chưa bảo vệ decimal, IP, viết tắt hoặc quote đóng.
- Clean cũ mặc định bỏ quote/bracket và chuyển ký hiệu thành chữ, có thể phá cấu trúc trước sanitization.
- Resume MP3 có hash text và voice; TTS plan cần thêm phiên bản/config.
- Baseline: 141 tests pass.

## 1. Module và giao diện

Tạo `cleaning/tts_text_preprocessor.py`:

```python
preprocess_for_tts(text, config=None) -> str
preprocess_with_diagnostics(text, config=None) -> TTSPreprocessResult
```

Hai API dùng cùng implementation. Result chứa text, danh sách warnings và statistics; không log toàn novel.

Config lưu dưới `Settings.tts_preprocessing`, cung cấp mặc định cho config cũ:

| Thuộc tính | Mặc định |
|---|---|
| enabled | true |
| url_policy | remove |
| email_policy | keep |
| remove_emoji | true |
| remove_html | true |
| remove_markdown_formatting | true |
| sentence_per_line | false |
| max_blank_lines | 1 |
| abbreviations | Danh sách thông dụng Anh/Việt |
| boilerplate_patterns | [] |
| footnote_patterns | [] |

URL replace thành `[đường dẫn]`; email replace thành `[email]`. Validate policy, kiểu danh sách, giới hạn dòng trống và regex cấu hình.

Tạo bộ nhận diện token/boundary dùng chung, và helper clean + preprocess một chương. Trả chapter copy, không mutate chapter nguồn.

## 2. Clean profile và normalization

### Clean an toàn

- Quote/bracket mode: keep.
- Tắt global symbol map, thêm dấu chấm tự động và drop empty lines.
- Chuyển HTML, Unicode, whitespace cho sanitizer xử lý theo thứ tự thống nhất.
- Giữ custom cleaning rules đã được người dùng cấu hình rõ ràng.
- Công cụ clean ngoài luồng TTS giữ behavior cũ.

### Thứ tự xử lý

1. Chuẩn hóa CRLF/CR, Unicode line separators, NFC.
2. Decode entities lồng nhau trong token, không chạy lại toàn pipeline đến hội tụ.
3. Loại BOM/control/invisible sau decode để chúng không che khuất markup; giữ joiner có giá trị ngôn ngữ.
4. Xử lý emoji sequence theo policy.
5. Scan comments, xử lý HTML tag nhận diện được; block tags thành newline. Giữ dấu so sánh và tag chưa rõ.
6. Separator thành paragraph boundary; bỏ Markdown syntax cân bằng, giữ inner text/code.
7. URL/email theo policy; metadata kỹ thuật standalone và boilerplate/footnote cấu hình.
8. Bullet giữ nội dung; normalize Unicode whitespace và full-width punctuation bằng mapping hữu hạn.
9. Ellipsis về `…`, hai dấu chấm về `.`, punctuation lặp về `!`, `?`, `?!`.
10. Sửa horizontal spacing quanh punctuation và sau quote đóng; không tiêu thụ newline.
11. Normalize dash lời thoại đầu dòng về `— ` khi ngữ cảnh rõ ràng.
12. Heading/body có terminal dính body được tách; không đoán title không có delimiter.
13. Sentence-per-line tùy chọn dùng boundary chung, không tách abbreviation/token kỹ thuật.
14. Final cleanup, NFC và diagnostics CJK/script khác/mojibake/U+FFFD.

Các bước bảo vệ decimal, thousands, time/date, IP/version, domain, abbreviation/initials, Windows path, key:value và balanced JSON. Không dùng placeholder có thể va chạm với novel text.

### Không tự sửa

- Hoà/Hòa, ngữ pháp, OCR, l/I/1, rn/m.
- Mojibake, U+FFFD hoặc tên riêng CJK.
- Mojibake chỉ được nhận diện và ghi diagnostic; các chuỗi match, kể cả C1 byte
  nằm bên trong chuỗi lỗi, được giữ nguyên để người dùng tự review.
- Từ/câu lặp, nội dung trong ngoặc hoặc code.
- Ngoặc/quote thiếu, hyphenated words, slash.
- Literal `\n`, `\t`, `\r` khi source chưa xác nhận serialization.
- Số thành chữ hoặc fuzzy spam deletion.

## 3. Chunking

- Boundary preference: paragraph → sentence → clause → whitespace → hard split.
- Giữ separator khi pack; punctuation/closer đi cùng câu trước.
- Không chọn điểm cắt bên trong protected token.
- Ưu tiên giữ short quote nguyên khối; khi quá dài chọn sentence/clause trước whitespace.
- Heading là unit riêng, không nhập vào body và không chia nhỏ.
- Heading/protected token vượt limit: lỗi chuẩn bị với vị trí/chương, không phá cấu trúc.
- Từ thông thường quá dài: hard split có warning, tránh tách combining sequence.
- Bỏ chunk empty hoặc punctuation-only; processor cũng chặn các input đó trước request.
- Fallback retry dùng boundary an toàn gần midpoint; không sanitize lại text sau chunking.
- Không cắt heading trong fallback retry.

## 4. Tích hợp, worker và provenance

### Nhóm chương

- Step 2 giữ nguyên nhiệm vụ grouping/canonical export.
- `prepare_tts` nhận source canonical, xử lý preamble, heading/body trước `split_chapters`.
- Tổng hợp counters/warnings trong TTS plan; hiển thị qua worker message/job console.
- Snapshot source/document và Settings của batch; chuẩn bị text trên worker.
- Kiểm tra cancel trước xử lý, giữa các chương và trước ghi TTS plan.

### Luồng cũ

- Helper Qt-free chuẩn bị snapshot từ source Step 2 trước chunking.
- TXT/JSON dẫn xuất chứa text đã chuẩn hóa và provenance mới.
- Inputs từ 100.000 ký tự dùng worker; inputs nhỏ giữ đường chạy inline cho tương thích UI.
- Kết quả chỉ publish vào document khi source/job identity/Settings chưa đổi và chưa cancel.
- Bundle thiếu/khác provenance được chuẩn bị lại từ upstream source; không sửa các chunks cũ trực tiếp.
- Nếu không có source hoặc pipeline state không hợp lệ, báo yêu cầu chuẩn bị lại trước TTS.

### Failed overrides

- Replacement input được safe-clean/preprocess trước kiểm tra nội dung đọc được và limit.
- Giữ order; không tự tăng số chunk hoặc chia lại override.
- Khi gửi request dùng replacement đã chuẩn hóa, không sanitize lần nữa.

### Cache và invalidation

- Fingerprint gồm source, effective clean profile/rules, preprocessing version/config, chunker version, limit.
- TTS chunk plan schema mới: 2; cache cũ rebuild từ canonical source.
- Manifest MP3 giữ schema và quy tắc hash text + voice + order hiện có.
- Chunk khớp resume; chunk khác regenerate. Không xóa MP3 cũ do đổi plan.
- Overrides chỉ apply với plan ID tương ứng; file cũ giữ lại và báo warning khi không áp dụng.
- Config thay đổi rút authority audiobook/video; canonical group files vẫn còn.
- Cancel không gọi Edge TTS và không publish kế hoạch mới chưa được chuẩn bị xong.

## 5. Kiểm thử và nghiệm thu

### Unit/invariants

- 29 fixture trước/sau và idempotence ở mọi fixture thực hiện đủ 30 trường hợp bắt buộc.
- False positives: numbers/time/date/IP/version/domain, viết tắt/initials, path, JSON, math, code.
- HTML/entity/Markdown lồng nhau, invisible che markup, emoji sequence, quote chưa đóng, combining Unicode.
- Seed cố định cho text hỗn hợp, chạy cả sentence-per-line bật/tắt.
- Không có NUL/CR/BOM, whitespace thừa hoặc quá nhiều blank lines với default config.
- Không crash với empty string, mixed scripts hoặc novel lớn.

### Integration/UI

- Fake Edge TTS client kiểm tra text thực tế nhận được ở cả hai luồng.
- Hash/source/canonical TXT/JSON không đổi.
- Không mất/lặp nội dung hoặc cắt protected tokens, punctuation/closer/chapter heading.
- Resume cùng config, config thay đổi, cache schema cũ, stale override, edit lỗi, cancel, fallback.
- Settings round-trip, controls và downstream invalidation.
- Tests cũ có kỳ vọng global symbol expansion được cập nhật sang semantic preservation theo quyết định đã chốt.

### Benchmark

Chạy mỗi cỡ trong process mới, input đúng 1/10/50 MiB UTF-8. Ghi thời gian và peak RSS thực tế từ `/proc/self/status`; không đặt wall-clock threshold phụ thuộc máy.

```bash
.venv/bin/python scripts/benchmark_tts_preprocessing.py --size-mb 1
.venv/bin/python scripts/benchmark_tts_preprocessing.py --size-mb 10
.venv/bin/python scripts/benchmark_tts_preprocessing.py --size-mb 50
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -q
```

### Definition of Done

- [x] Module/API/config/diagnostics độc lập.
- [x] Cả hai luồng preprocess trước chunking.
- [x] Clean profile bảo toàn nghĩa và canonical files.
- [x] Chunker/fallback có context và chapter/quote handling.
- [x] Cache/resume/override phiên bản hóa, không xóa audio cũ.
- [x] Settings UI, worker snapshot và cancellation.
- [x] Unit, invariant, fake-client integration và offscreen UI tests.
- [x] Benchmark và báo cáo file/rules/tests/before-after/compatibility.

Kết quả triển khai và số liệu cuối cùng được ghi trong `TTS_PREPROCESSING_REPORT.md`. Unit tests xác minh text/tích hợp; chất lượng pause của giọng Edge TTS cần được nghe đánh giá riêng.
