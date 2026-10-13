# Verify Smoke Check — Implementation Plan

> **For agentic workers:** Phương thức đã được owner chọn là Native, tuần tự. Dùng `superpowers:executing-plans` khi thực thi kế hoạch; không chia bản vá này cho nhiều implementer. Các bước chưa đánh dấu bên dưới chưa được thực hiện.

**Project:** novel-pipeline-v2

**Status:** Approved — conditional execution gates apply

**Goal:** Làm lỗi số Hán xuất hiện đúng trong kết quả checker, tổng kết và exit code; giữ phạm vi smoke checks rõ ràng.

**Architecture:** Sửa cách tổng hợp boolean trong checker hiện có. Giữ `main()` và entry point; kiểm chứng chúng bằng logic thật và child process thật.

**Tech stack:** Python 3.11+, `unittest.TestCase`, thư viện chuẩn; pytest bổ sung khi được môi trường hỗ trợ.

**Sources:** `intent/verify-smoke-check/intent.md` và `intent/verify-smoke-check/spec.md`, đều Approved.

**Implementation status:** Not started — chưa có bản vá hoặc kết quả test thực tế.

## 1. Quyết định đã chốt và điều kiện thực thi

| Hạng mục | Quyết định của owner |
| --- | --- |
| Lưu nguồn yêu cầu | Lưu đúng phiên bản spec Approved và kế hoạch này vào Git trước khi giao cho agent khác. |
| Phương thức | Native, tuần tự; không chia bản vá ba file cho nhiều agent. |
| Workspace | Ưu tiên checkout hiện tại; không reset hoặc stash thay đổi frontend/design ngoài nhiệm vụ. |
| Child process | Timeout 30 giây mỗi child. |
| Thứ tự validation | Chạy test mục tiêu trước. Chỉ chạy toàn suite sau khi xác nhận dependency và giới hạn mạng phù hợp. |
| T8 và baseline | Phân biệt lỗi môi trường/baseline với lỗi của bản vá; không báo GREEN giả khi một smoke check thật khác đang thất bại. |
| Bằng chứng | Phải có output thực tế của RED, GREEN và regression, không chỉ tuyên bố pass. |

Các execution gates:

- **G1 — Nguồn yêu cầu:** intent/spec/plan tồn tại, Approved và đã được Git theo dõi; spec đúng hash đã duyệt.
- **G2 — Baseline:** kiểm tra lại HEAD, working tree và ba file mục tiêu; nếu chúng có thay đổi mới hoặc code khác baseline, đối chiếu lại trước khi sửa. Không tự ghi đè hoặc reset.
- **G3 — Test mục tiêu:** interpreter hoạt động, cấu hình cách ly được đặt trước import `tests`, và harness dùng dữ liệu giả, chặn mạng trong các test smoke mới.
- **G4 — Full suite:** dependency đủ và điều kiện offline/giới hạn mạng đã được xác nhận; cho phép loopback cần thiết của test OAuth. Chưa đáp ứng thì không chạy toàn suite, ghi rõ trạng thái validation còn thiếu.
- **G5 — Nghiệm thu:** có bằng chứng RED đúng nguyên nhân, GREEN, regression và review phạm vi. Không coi approval của plan là bằng chứng test đã thành công.

Lượt lưu tài liệu Bài 4 không tự chạy các bước implementation bên dưới.

## 2. Baseline Git và nguồn đầu vào

| Hạng mục | Baseline đã đọc |
| --- | --- |
| Repository | `/home/thienphuc/Projects/phuc/novel-pipeline-v2` |
| Branch | `main` |
| Code baseline commit | `1f1d9699663c46fe1115e2eb5745ead787af24b1` |
| Intent | Approved, đã tracked trước khi lưu plan. |
| Spec | Approved; được lưu nguyên phiên bản trong commit tài liệu cùng plan. |
| File mục tiêu | `verify.py`, `INSTALL.md` không có thay đổi local; `tests/test_verify.py` chưa tồn tại tại baseline. |
| Ngoài nhiệm vụ | Sáu file frontend/design modified; `.archify/` untracked. |
| Interpreter | Có `.venv/bin/python`; `pyvenv.cfg` ghi `3.14.7`. Phiên bản hoạt động chưa được xác minh bằng thực thi. |
| Test hiện tại | Chưa chạy hoặc xác nhận pass/fail trong các lượt capture tài liệu. |

Commit lưu spec/plan sẽ thay đổi HEAD mà không đổi code baseline. Không yêu cầu
HEAD lúc thực thi bằng đúng commit cũ: kiểm tra quan hệ commit, diff và hash đầu
vào để phân biệt commit tài liệu với thay đổi source mới.

Hash đầu vào và source trước implementation:

```text
9b6a2c62ee405a58ee5ec7e9c4744ec749cc0270dd548de04bbba7eb977f6134  intent/verify-smoke-check/intent.md
3d0155ae3290cc6d295dddb849c7ab383a9383c44acea6cdde6c0a2fe18fe5c4  intent/verify-smoke-check/spec.md
dc2891f9b3061be032a8d68330fa2dffa39ef23c7d0a781c50376ca882fdd377  verify.py
a51a6db9b0814760cb24b53fb5910226cae2a422686c2720d95b23b19b34e16a  INSTALL.md
```

Giữ nguyên các thay đổi ngoài nhiệm vụ:

- `design-system/novel-pipeline/MASTER.md`
- `frontend/src/App.tsx`
- `frontend/src/components/job-panel.tsx`
- `frontend/src/hooks/use-workspace.ts`
- `frontend/src/index.css`
- `frontend/src/lib/types.ts`
- `.archify/`

## 3. Global constraints

- Giữ năm fixture, bốn smoke checks, thứ tự kiểm tra và hợp đồng mã `0`/`1`.
- Không sửa converter, chunking, UI, API, dependency hoặc báo cáo lịch sử.
- Test mới dùng `unittest.TestCase` và thư viện chuẩn.
- Dữ liệu cố định/giả; không đọc secrets, dùng tài khoản thật hoặc gọi dịch vụ bên ngoài.
- Giữ checker số Hán và `main()` thật trong các test chứng minh false positive.
- Không refactor import để làm test thuận tiện hơn.
- Không stage, hoàn tác, reset, stash hoặc ghi đè thay đổi ngoài nhiệm vụ.
- Python tối thiểu 3.11; không coi một lần chạy trên Python hiện có là chứng nhận cho mọi phiên bản.
- Ghi lệnh, interpreter, checkout, working-tree state và output thực tế khi validation.

## 4. Chính xác các file implementation dự kiến thay đổi

| File | Thao tác | Lý do |
| --- | --- | --- |
| `verify.py` | Sửa | Tổng hợp đúng kết quả số Hán; thay ba thông báo theo D3. |
| `tests/test_verify.py` | Tạo mới | Test helper, aggregation, exception, diagnostics, isolation và process exit code. |
| `INSTALL.md` | Sửa tối thiểu | Thêm lệnh smoke check, ý nghĩa exit code và giới hạn xác minh. |

Intent/spec/plan là đầu vào của implementation, không nằm trong bản vá sản phẩm
ba file. Việc lưu spec/plan vào Git thuộc bước capture tài liệu Bài 4.

## 5. Review Focus

1. Mismatch ở case đầu bị case thành công cuối che khuất.
2. `None` đúng kỳ vọng bị xem là lỗi, hoặc đầu vào cần trả `None` lại được chấp nhận sai.
3. Patch sai namespace khiến fault injection không thực sự đến checker.
4. Child không chạy `__main__`, hoặc launcher che mất `SystemExit`.
5. Import test trước cấu hình cách ly, hoặc patch/child process còn tồn tại sau test.

Các tình huống này được bảo vệ bởi T1, T2, T8–T10.

## 6. Các bước triển khai, dependencies và traceability

Tất cả bước implementation dưới đây **chưa thực hiện**.

- [ ] **S0 — Preflight:** kiểm tra approval, hash, Git state, interpreter và điều kiện regression. Đặt cấu hình test cách ly trước import `tests`.
- [ ] **S1 — Test trước production:** tạo `tests/test_verify.py` với T1–T10; giữ production code ở baseline.
- [ ] **S2 — RED:** chạy riêng mismatch helper, mismatch qua `main()` và mismatch ở child process; xác nhận lỗi assertion đúng nguyên nhân.
- [ ] **S3 — Sửa tín hiệu:** tổng hợp trong `test_chinese_numerals()` sao cho thất bại không bị đặt lại; tiếp tục case khi chỉ có mismatch.
- [ ] **S4 — Sửa thông báo:** thay count/success/failure bằng D3; giữ vòng bốn kiểm tra và `sys.exit(main())`.
- [ ] **S5 — GREEN:** chạy toàn bộ test mới bằng unittest; kiểm tra output, fault injection và exit code thực tế.
- [ ] **S6 — Tài liệu:** bổ sung tối thiểu phần verification của `INSTALL.md`.
- [ ] **S7 — Regression:** chạy regression liên quan; chỉ chạy full suite khi G4 được đáp ứng.
- [ ] **S8 — Review:** đối chiếu diff, phạm vi, compatibility và bằng chứng trước/sau; báo mọi giới hạn validation.

| Bước | Phụ thuộc | Điều kiện hoàn thành | Requirements / Design / Acceptance |
| --- | --- | --- | --- |
| S0 | Approval và execution gates | Đầu vào khớp; ba file mục tiêu không có thay đổi chưa xử lý; môi trường được ghi nhận. | N1–N4, D4–D5, AR1 |
| S1 | S0 | Test có assertion độc lập, logic thật; harness có timeout/cleanup. | R1–R7, D1–D5, AT1–AT9 |
| S2 | S1 | Fault hiện trong diagnostics; assertion thất bại do tín hiệu thành công sai, không phải import/setup error. | R2, R4, R7; D1, D2, D4, D5; AT2, AT3, AT8, AR2 |
| S3 | RED hợp lệ | Boolean đúng; không đổi fixture, converter, signature hoặc exception boundary. | R1–R5, D1–D2, AT1–AT6 |
| S4 | S3 | Đúng câu chữ và số đếm; runner/entry point được giữ. | R6, D3, AT7–AT8 |
| S5 | S4 | Test mới thành công; fault thật đến checker; process trả mã quan sát được. | R1–R7, D1–D5, AT1–AT9 |
| S6 | S5 | Lệnh, mã `0`/`1`, giới hạn được mô tả; không sửa lịch sử. | R8, D6, AR3 |
| S7 | S5–S6; G4 cho full suite | Ghi output/failure/skip; không tự sửa ngoài phạm vi. | R1–R7, N3–N4, D1–D5, AR2 |
| S8 | S7 | Chỉ ba file sản phẩm; đủ traceability; giới hạn validation được báo rõ. | R1–R8, D1–D6, AR1–AR3 |

Contract giữ nguyên:

- `test_chinese_numerals()` không tham số, phát diagnostics và trả boolean.
- `main()` không tham số, trả `0` hoặc `1`.
- Entry point gọi `sys.exit(main())`.
- Không thêm production flag, test hook, dependency injection parameter hoặc class kết quả.

Ba thông báo Approved:

```text
Smoke checks reported success. Full application validation was not performed.
One or more smoke checks failed. Review the results above.
Smoke checks reporting success: {passed}/{total}
```

## 7. Test design và dữ liệu độc lập

Class dự kiến: `VerifySmokeCheckTests` trong `tests/test_verify.py`.

| Test method | Assertion chính | Acceptance |
| --- | --- | --- |
| T1 `test_numerals_matching_cases_pass` | Converter/checker thật; năm fixture khớp; trả `True`; `None` đúng kỳ vọng thành công. | AT1 |
| T2 `test_numerals_mismatch_at_each_position_fails` | Subtests từng vị trí; trả `False`; output có input/actual/expected lỗi và diagnostics của case sau. | AT2 |
| T3 `test_main_numeral_mismatch_returns_one` | Converter bị inject; checker và main thật; mã `1`, số đếm `3/4` khi ba check khác thành công. | AT3 |
| T4 `test_main_all_checks_success_returns_zero` | Logic thật báo thành công; mã `0`, số đếm `4/4`. | AT4 |
| T5 `test_main_other_check_failures_continue` | Từng check ngoài mục tiêu báo `False`/`Exception` theo D4; giữ main/checker số Hán thật; mã `1`, check sau vẫn chạy. | AT5 |
| T6 `test_main_converter_exception_returns_one` | Converter phát `RuntimeError("synthetic converter failure")`; main ghi nhận thất bại và trả `1`. | AT6 |
| T7 `test_summary_messages_are_scoped` | Capture output thật hai nhánh; đúng D3 và số đếm; không khẳng định toàn ứng dụng sẵn sàng. | AT7 |
| T8 `test_process_success_runs_actual_script` | Chạy file thật; stdout/stderr và process return code `0` khi các check thật thành công. | AT8 |
| T9 `test_process_mismatch_runs_main_guard_and_exits_one` | Inject trong child; file thật chạy dưới `__main__`; mismatch trong output, số đếm `3/4`, return code `1`. | AT8 |
| T10 `test_repeated_runs_do_not_leak_fault_or_config` | Lượt bị inject rồi lượt bình thường không rò patch; cấu hình cách ly; không network attempt hoặc child còn sống. | AT9 |

T5 chứng minh phản ứng của aggregator với kết quả check khác, không chứng minh
check đó đúng. Doubles của T5 không thay thế chứng cứ T3/T9.

Literal data cho T2:

| Input | Expected | Actual được inject |
| --- | --- | --- |
| `九十八` | `98` | `97` |
| `一百零五` | `105` | `104` |
| `两万三千` | `23000` | `22999` |
| `一二` | `None` | `12` |
| `十十` | `None` | `20` |

Mỗi subtest chỉ sai một vị trí; các vị trí khác dùng literal đúng từ fixture
Approved. Không tính expected bằng converter hoặc checker đang kiểm thử.

## 8. Fault injection và entry point thật

### Lookup hiện tại

`verify.py:25` import converter bên trong checker. Patch
`chapters.chinese_to_int` trước lời gọi và giữ context patch trong suốt lời gọi.
Import `verify` trước đó không làm mất hiệu lực này.

Không tạo `verify.chinese_to_int` bằng `create=True`. Nếu source đổi thành import
ở module scope, dừng đối chiếu lookup mới trước khi sửa test. Không chuyển import
chỉ để làm test thuận tiện.

Assertion phải thấy actual đã inject trong diagnostics và kết quả checker.
Chỉ kiểm tra mock được gọi chưa đủ chứng minh phát hiện lỗi.

### AT8 ở cấp tiến trình

**Nhánh thành công:** arguments là `sys.executable`, `-B`, đường dẫn tuyệt đối đến
`verify.py`; cwd là repository root; cả bốn checks đều thật.

**Nhánh mismatch:** child chạy launcher test-only. Launcher cài patch converter
trong chính child rồi gọi `runpy.run_path` cho file thật với
`run_name="__main__"`. Để `sys.exit(main())` của file quyết định return code.

Không gọi `verify.main()` rồi tự tạo exit code thay entry point; không patch
`main()`/`sys.exit`, nuốt `SystemExit`, viết lại script hoặc thêm production switch.
Patch parent không tự trở thành fault injection của child.

Harness đã được owner đồng ý:

- Timeout 30 giây/child, là giới hạn chống treo, không phải benchmark.
- Dùng `subprocess.run` với capture stdout/stderr, text mode và encoding UTF-8.
- Dùng `sys.executable`, không dùng bare `python` có thể trỏ interpreter khác.
- Child có `NOVEL_PIPELINE_CONFIG_DIR` trỏ vào `TemporaryDirectory` của test.
- Guard mạng cho test smoke mới và child được cài trước logic mục tiêu; lỗi có marker cố định, không ghi địa chỉ/credentials.
- Restore patch và cleanup child/temp kể cả khi timeout.

Nếu T8 hoặc ba checks thật ngoài số Hán thất bại vì môi trường/baseline, báo
nguyên nhân; không ép chúng thành công, không đổi chúng sang stub để báo GREEN.

Không áp dụng guard chặn mọi socket lên toàn suite: test OAuth tại
`tests/test_youtube_auth.py:150` dùng HTTP loopback. G4 yêu cầu xác nhận giới hạn
mạng thích hợp, chặn kết nối bên ngoài nhưng cho phép loopback cần thiết.

## 9. Red → Green → Regression

| Kết quả | Dấu hiệu | Xử lý |
| --- | --- | --- |
| RED mong đợi | Fault hiện trong diagnostics; helper còn trả `True`, main/process còn trả `0`; assertion mong `False`/`1` thất bại. | Ghi output rồi triển khai S3–S4. |
| Lỗi test/harness | Không thấy fault; patch sai; child không chạy file; fixture/assertion sai. | Sửa harness, chạy lại RED; chưa sửa production. |
| Lỗi môi trường | ImportError, thiếu interpreter/module, Qt setup, Unicode, permission hoặc timeout. | Báo nguyên nhân; không coi là regression đã tái hiện. |
| GREEN | Test mới thành công sau bản vá; helper/main/process có output đúng. | Chuyển regression. |
| Regression thất bại | Test cũ/suite thất bại. | Phân loại theo baseline và output; báo rõ, không tự sửa ngoài scope. |

T1 và preservation tests có thể thành công trước bản vá. Bằng chứng RED phải từ
T2, T3 hoặc T9 và đúng lỗi mục tiêu. Không coi mọi mã khác 0 là RED hợp lệ.

Các lớp regression:

1. Test mới bằng unittest — bắt buộc.
2. Test chương và headless service liên quan.
3. Pytest bổ sung và normalization khi interpreter hỗ trợ.
4. Full Python suite chỉ khi G4 đã được đáp ứng.

Không dùng unittest discovery làm chứng cứ đã thu thập các lớp pytest và
fixture `tmp_path`. Không báo suite chưa chạy thành pass.

## 10. Lệnh dự kiến cho lượt implementation

Các lệnh test dưới đây chưa được chạy trong Bài 4. Chúng không cho phép cài
dependency hoặc sửa hệ thống để vượt qua lỗi môi trường.

### S0 — Preflight

```bash
cd /home/thienphuc/Projects/phuc/novel-pipeline-v2

git rev-parse HEAD
git merge-base --is-ancestor 1f1d9699663c46fe1115e2eb5745ead787af24b1 HEAD
git --no-optional-locks status --short --untracked-files=normal
git diff --cached --name-only
git ls-files --error-unmatch intent/verify-smoke-check/intent.md intent/verify-smoke-check/spec.md intent/verify-smoke-check/plan.md
sha256sum intent/verify-smoke-check/intent.md intent/verify-smoke-check/spec.md verify.py INSTALL.md

.venv/bin/python -B -c 'import sys, importlib.util; print(sys.version); print({name: importlib.util.find_spec(name) is not None for name in ("pytest", "PyQt6", "httpx", "fastapi", "PIL")})'
```

Module được tìm thấy chưa chứng minh dependency hoạt động; runtime vẫn cần
validation. Nếu baseline/hash source khác, đối chiếu thay đổi thay vì reset.

### Wrapper cách ly cho từng lượt validation

Khai báo lại nếu agent mở shell mới; không lưu wrapper vào repository.

```bash
smoke_run() (
  smoke_tmp=$(mktemp -d -t novel-verify.XXXXXX) || exit 2
  trap 'rm -rf -- "$smoke_tmp"' EXIT

  export NOVEL_PIPELINE_CONFIG_DIR="$smoke_tmp/config"
  export PYTHONDONTWRITEBYTECODE=1
  export PYTHONIOENCODING=utf-8
  export QT_QPA_PLATFORM=offscreen

  "$PWD/.venv/bin/python" -B "$@"
)
```

Đặt biến cách ly trước import `tests`: `tests/__init__.py:10` có tác dụng phụ tạo
cấu hình test khi override chưa tồn tại. Wrapper này không tự chặn egress toàn suite.

### Baseline runtime

```bash
smoke_run verify.py
```

Ghi output/exit code; không coi thông báo baseline là toàn ứng dụng sẵn sàng.

### S2 — RED

```bash
smoke_run -m unittest -v \
  tests.test_verify.VerifySmokeCheckTests.test_numerals_mismatch_at_each_position_fails \
  tests.test_verify.VerifySmokeCheckTests.test_main_numeral_mismatch_returns_one \
  tests.test_verify.VerifySmokeCheckTests.test_process_mismatch_runs_main_guard_and_exits_one
```

Kiểm tra assertion về false positive, không phải setup `ERROR`. Không bỏ qua
failure bằng `|| true` hoặc chuyển sang sửa source khi chưa có RED hợp lệ.

### S5 — GREEN

```bash
smoke_run -m unittest tests.test_verify -v
```

### S7 — Regression liên quan

```bash
smoke_run -m unittest -v \
  tests.test_chapter_clock_lines \
  tests.test_headless_service
```

Khi pytest được interpreter hỗ trợ:

```bash
smoke_run -m pytest -p no:cacheprovider -q \
  tests/test_verify.py \
  tests/test_chapter_normalization.py \
  tests/test_chapter_clock_lines.py \
  tests/test_headless_service.py
```

Chỉ sau khi G4 được xác nhận:

```bash
smoke_run -m pytest -p no:cacheprovider -q
```

### S8 — Review

```bash
git diff --check -- verify.py INSTALL.md
git diff -- verify.py INSTALL.md
git diff --no-index -- /dev/null tests/test_verify.py
git --no-optional-locks status --short --untracked-files=normal
```

`diff --no-index` có thể trả `1` vì hai nội dung khác nhau; đây không phải kết quả
test. Không stage toàn repo. Kế hoạch implementation này không tự yêu cầu commit
hoặc push source; commit tài liệu Bài 4 là một hành động đã được owner yêu cầu riêng.

## 11. Rủi ro, alternatives và rollback

| Rủi ro | Kiểm soát |
| --- | --- |
| Patch sai namespace hoặc chỉ ở parent | T2/T9 thấy actual đã inject trong output thật. |
| Launcher nuốt `SystemExit` | AT8 dùng exit tự nhiên và `CompletedProcess.returncode`. |
| Import trước cách ly | Wrapper/env child được đặt trước import test/application. |
| Full suite chặn cả loopback | G4 tách egress bên ngoài khỏi loopback OAuth fixture. |
| Consumer parse stdout cũ | Q1 chủ đích thay nhãn/tổng kết; ghi rủi ro vì usage consumer chưa xác minh. |
| Working tree có thay đổi người dùng | Chỉ ba file mục tiêu; không reset/stash/stage toàn repo. |

Alternatives đã cân nhắc:

- Return `False` ngay mismatch đầu: không chọn vì R3 cần diagnostics case sau.
- Thay script bằng pytest runner: mở rộng scope và thay dependency/CLI.
- Chuyển import lên module scope: không cần cho bản vá.
- Stub checker/main: không chứng minh lỗi mục tiêu.
- Chỉ test return value `main()`: không chứng minh `__main__`/process exit code.

Rollback:

- Trước commit source: hoàn tác đúng hunk của nhiệm vụ trong `verify.py`/`INSTALL.md`; chỉ xóa test mới sau khi xác nhận vẫn thuộc nhiệm vụ và không có thay đổi của người khác.
- Không `git reset --hard`, không hoàn tác toàn working tree.
- Nếu sau này source được commit riêng, revert đúng commit đó trong một lượt được cho phép.
- Rollback sẽ khôi phục cả hành vi false positive baseline; báo rõ giới hạn.

## 12. Tự phản biện và handoff

| Câu hỏi | Đánh giá |
| --- | --- |
| Rủi ro cao nhất? | S1/D5–AT8: fault injection/exit code có thể được mô phỏng sai nhưng vẫn trông hợp lệ. |
| Vượt scope? | Không có thay đổi sản phẩm ngoài ba file. Cài dependency, sửa suite cũ, frontend, chunking hoặc firewall toàn máy không thuộc plan. |
| Test không chứng minh hành vi thật? | T5 chỉ chứng minh phản ứng aggregator; không thay T3/T9 hoặc chứng minh thuật toán của check khác. |
| Compatibility? | Stdout thay đổi có chủ đích; callable API, converter và entry point giữ nguyên. Consumer của stdout chưa xác minh. |
| Agent mới có tự suy đoán? | File, test names, dữ liệu, lookup, exit path và kỳ vọng đã rõ. Agent phải dừng ở gate chưa đáp ứng, không tự suy đoán môi trường hoặc báo GREEN giả. |

Q1–Q5 trong spec đã chốt. Native, checkout hiện tại và timeout 30 giây đã được
owner đồng ý. Các gates còn lại là kiểm chứng môi trường/baseline thực tế, không
phải yêu cầu tự mở lại các quyết định sản phẩm đã phê duyệt.

Chưa đủ căn cứ cam kết full suite có thể chạy hoặc đã pass. Bài 4 hoàn tất ở việc
phê duyệt và lưu hợp đồng kế hoạch vào Git; các bước implementation và bằng chứng
RED/GREEN/regression thuộc lượt thực thi tiếp theo.
