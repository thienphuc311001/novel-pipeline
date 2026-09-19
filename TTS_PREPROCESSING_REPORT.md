# Báo cáo triển khai TTS preprocessing

## Kết quả

Đã tích hợp ở cả luồng nhóm chương và luồng legacy:

```text
Step 2 / grouping source
→ safe cleaning (giữ cấu trúc, áp dụng custom rules rõ ràng)
→ TTS preprocessing (deterministic, in-memory)
→ sentence-aware chunking
→ Edge TTS
→ MP3 / audiobook
```

Source TXT, Step 2 và canonical TXT/JSON nhóm chương không bị ghi đè. TXT/JSON dẫn xuất của legacy chứa nội dung đã chuẩn hóa. Không dùng LLM hoặc thêm dependency cho sanitization.

## File tạo/sửa

### Tạo mới

| File | Vai trò |
|---|---|
| `cleaning/tts_text_preprocessor.py` | Config, result, string API, diagnostics API, normalization và provenance |
| `cleaning/tts_boundaries.py` | Protected technical tokens, JSON scanner, sentence/clause boundary, fallback split |
| `cleaning/tts_prepare.py` | Safe clean + preprocess chapter copy, tổng hợp diagnostics |
| `media/tts_preparation.py` | Chuẩn bị legacy document snapshot, preamble và bundle |
| `tests/test_tts_preprocessing.py` | 17 test methods với fixture, subtest và invariant/integration/UI scenarios |
| `scripts/benchmark_tts_preprocessing.py` | Benchmark offline 1/10/50 MiB UTF-8 |
| `TTS_PREPROCESSING_PLAN.md` | Kế hoạch chi tiết, quyết định và acceptance checklist |
| `TTS_PREPROCESSING_REPORT.md` | Báo cáo này |

### Sửa

- `cleaning/textclean.py`: thêm `CleaningOptions.for_tts`, không đổi mặc định clean ngoài TTS.
- `chunking/splitter.py`: boundary có context, quote/heading/token handling, combining-safe hard fallback; bỏ thuật toán recursive pack cũ không còn dùng; sửa offset hard-split diagnostics khi tổng hợp nhiều chương.
- `config/settings.py`: lưu `tts_preprocessing`, mặc định tương thích config cũ.
- `media/groups.py`: preprocess trước split, plan schema 2, versions/config fingerprint, diagnostics, cancel, normalized overrides và stale-override warning.
- `media/artifacts.py`: optional preprocessing provenance trong JSON bundle legacy.
- `media/tts.py`: safe fallback retry, chặn empty/punctuation-only requests.
- `ui/grouped_pipeline.py`: batch/source snapshot, chuẩn bị trên worker, diagnostics, cancellation và publish plan identity.
- `ui/main_window.py`: legacy preparation worker cho text từ 100.000 ký tự, snapshot/cancel, rebuild bundle cũ, config invalidation downstream.
- `ui/settings_dialog.py`: enable, URL/email policies, emoji, sentence-per-line và advanced JSON.
- `tests/test_chapter_groups.py`, `tests/test_settings_dialog.py`: đổi hai expectation về global symbol expansion sang giữ `&`/`10%`, theo clean profile đã được chọn. Các checks bảo toàn canonical/source và UI behavior vẫn giữ.
- `README.md`: hướng dẫn tính năng và liên kết plan/report.

## Rules đã triển khai

- NFC, line endings và Unicode line/paragraph separators.
- BOM, zero-width/control/directional/soft-hyphen cleanup; giữ joiner có giá trị ngôn ngữ, và giữ emoji sequence khi policy cho phép.
- Decode HTML entities lồng nhau; scan HTML comments, structural tags thành newline, bỏ recognized markup và giữ unknown angle-bracket prose/math.
- Markdown delimiter pairing có stack, hỗ trợ nested formatting, giữ inner text và code.
- Unicode horizontal whitespace, leading/trailing space, tối đa một blank line mặc định.
- Full-width punctuation bằng mapping hữu hạn, không dùng NFKC toàn văn.
- `...`/`. . .`/chuỗi ellipsis về `…`; `..` về `.`; dấu lặp về `!`, `?`, `?!`.
- Sửa spacing sau punctuation/quote đóng, gồm câu dính `?Ta`, `!Hắn`, `.Ta`, `…Sau`; giữ newline.
- Dash thoại đầu dòng về `— `; không đổi hyphen trong từ hay số âm.
- Heading có explicit terminal/body dính được tách; title trở thành chunk logical riêng.
- URL remove/keep/replace, email keep/remove/replace; URL dính ngay sau `...` và scheme chữ hoa có tests.
- Metadata kỹ thuật standalone `chapter_id=`/`source_url=`; boilerplate/footnote chỉ theo regex cấu hình.
- Separator và bullet cleanup, giữ text của item.
- Diagnostics CJK, punctuation CJK, script khác, mojibake, U+FFFD và preserved linguistic joiners.
- Protected numbers, thousands, date/time, IP/version, common domain, abbreviation/initials, Windows paths, key:value và nested balanced JSON.
- Chunking paragraph/sentence/clause/space preference, quote/closer handling, no punctuation-only requests, oversized token/heading errors và combining-safe hard split.

Counters được log trong job console; không log toàn novel.

## Những rule không tự sửa

Không sửa chính tả Hoà/Hòa, ngữ pháp, OCR, từ/câu lặp, mojibake, U+FFFD, tên riêng CJK hoặc nội dung trong ngoặc. Không dịch, không chuyển số thành chữ, không đoán ngoặc đóng và không chuyển literal `\n` thành newline. Custom clean rules do người dùng cấu hình vẫn có thể chủ động thay đổi văn bản trước sanitization.

C1/control bytes bên trong chuỗi mojibake đã match được giữ nguyên; control bytes không thuộc chuỗi match vẫn đi qua control-character rule. Không tuyên bố đã phục hồi encoding hoặc khôi phục dữ liệu mất.

## Kiểm thử

Baseline: 141 tests. Latest regression run: **161 tests pass**, skipped 1 test do dependency OAuth tùy chọn không cài đặt.

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -q
```

Đã chạy thành công toàn suite và `git diff --check`.

Coverage mới:

- Đủ 30 trường hợp bắt buộc: 29 fixtures trước/sau, warnings tương ứng và idempotence ở từng fixture.
- 300 bộ text hỗn hợp sinh với seed cố định, sentence-per-line bật/tắt.
- Nested entities/Markdown, invisible che markup, four-or-more markers, full sample yêu cầu, Unicode combining, mixed scripts, emoji và unclosed quote/comment.
- Decimal/time/date/IP/version/abbreviation/initials/path/JSON/math false positives; JSON nested giữ punctuation literal.
- Chunk conservation, length, quote/closer placement, atomic heading, oversized tokens và safe retry split.
- Fake Edge TTS clients ở cả nhóm và legacy; kiểm tra text thực sự nhận được, không gọi service live.
- Resume cùng text/config, đổi URL policy, rebuild old cache, normalized override, stale override warning, cancel và empty inputs.
- Settings round-trip, actual controls, config invalidation của audiobook/video.
- Offscreen worker cancel và chuẩn bị thành công input legacy hơn 100.000 ký tự.
- Byte comparison của source/canonical group TXT/JSON trước và sau.

## Benchmark

Input là UTF-8 MiB, gồm prose tiếng Việt, missing spaces, ellipsis, quote và HTML. Mỗi cỡ chạy process mới trên máy hiện tại. Peak RSS lấy từ `VmHWM` của `/proc/self/status`, gồm interpreter/input/output/temporary allocations; không phải số đo toàn GUI hoặc end-to-end Edge TTS.

| Input | Input chars | Output chars | Thời gian | Peak RSS |
|---|---:|---:|---:|---:|
| 1 MiB | 855.994 | 791.724 | 0,871 s | 33,1 MiB |
| 10 MiB | 8.559.814 | 7.917.776 | 8,086 s | 167,7 MiB |
| 50 MiB | 42.799.034 | 39.589.036 | 38,858 s | 731,0 MiB |

Thời gian tăng gần tuyến tính với cỡ input. Bản đầu thay cả từng space đơn gây allocation dư; đã đổi regex chỉ xử lý whitespace cần chuẩn hóa. Peak 50 MiB giảm từ khoảng 983 MiB xuống khoảng 731 MiB trong bản cuối. Architecture vẫn load toàn text vào RAM, cần tính đến memory khi dùng novel rất lớn; không triển khai streaming.

Chạy lại:

```bash
.venv/bin/python scripts/benchmark_tts_preprocessing.py --size-mb 1
.venv/bin/python scripts/benchmark_tts_preprocessing.py --size-mb 10
.venv/bin/python scripts/benchmark_tts_preprocessing.py --size-mb 50
```

## Ví dụ before/after

Input (bắt đầu bằng BOM):

```text
\uFEFFChương 327: Đại chiến.....Hắn nhìn lên trời!!!!!!“Không thể nào!”Lâm Phàm hét lên.<br><br>Ngươi là ai?Ta không biết...https://example.com
```

Output:

```text
Chương 327: Đại chiến

Hắn nhìn lên trời! “Không thể nào!” Lâm Phàm hét lên.

Ngươi là ai? Ta không biết…
```

Đã có regression test so sánh chính xác output trên và chạy lại để xác nhận idempotence.

## Tương thích và giới hạn thực tế

- Canonical group files, group IDs, filename conventions và manifest audio schema giữ nguyên.
- TTS text plan schema 2 và version/config identity khiến plan cũ dựng lại. Tách heading riêng hoặc thay text có thể thay chunk count/order, nên một phần MP3 cũ cần regenerate; file cũ không bị xóa do invalidation.
- Resume chỉ dùng record có hash text/voice/order khớp. Old overrides giữ file nhưng không apply khi plan ID đổi, có warning rõ ràng.
- Bật URL keep bảo vệ URL trong punctuation rules; bare domains được bảo vệ cho các đuôi thông dụng và abbreviations có thể cấu hình.
- Code inner text không bị blanket deletion; những quy tắc metadata kỹ thuật rõ ràng/policy URL hoặc custom rules vẫn có hiệu lực theo cấu hình.
- Step 2 nhận trực tiếp normalized text từ Step 1; Han characters trong nội dung được giữ nguyên và không còn residue scan, dictionary review hoặc translation gate. Chinese chapter headers/numerals chỉ còn là nhận diện cấu trúc chương.
- Cancel được kiểm tra ở ranh giới chuẩn bị/chương/trước ghi plan; không interrupt giữa một regex đang chạy. Kết quả worker stale/cancelled không được publish vào document.
- Unit/integration tests không chứng minh pause nghe tự nhiên của giọng Edge TTS. Không thực hiện request live hoặc đánh giá audio bằng tai trong lần triển khai này.
