# Verify Smoke Check — Implementation Plan

> **For agentic workers:** Native, tuần tự; dùng `superpowers:executing-plans` khi được giao implementation. Không chia bản vá ba file cho nhiều implementer. Tất cả checkbox dưới đây chưa thực hiện.

**Project:** novel-pipeline-v2

**Status:** Draft — Lesson 7 review revision; awaiting owner re-approval

**Goal:** Phát hiện mismatch số Hán qua Boolean, tổng kết và exit code thật; giới hạn thông báo ở phạm vi smoke checks.

**Architecture:** Sửa aggregate Boolean của checker hiện có. Giữ converter, bốn checks, `main()`, exception boundary và entry point; harness chỉ nằm trong test.

**Tech stack:** Python 3.11+, `unittest.TestCase`, thư viện chuẩn; pytest bổ sung nếu môi trường hỗ trợ.

**Spec:** `intent/verify-smoke-check/spec.md` — Approved. Intent tại cùng thư mục cũng Approved.

**Evidence:** Revision này chỉ đọc Git/mã/tài liệu/metadata. Chưa chạy interpreter, checker, launcher, test, build hoặc application. Review Session A và bản tổng hợp `plan-auditor` do owner cung cấp; không coi các nhãn “Verified” của reviewer là bằng chứng thực thi độc lập.

**Implementation:** Not started. Approval cũ của plan không tự áp dụng cho revision này.

## 1. Quyết định, phạm vi và gates

Giữ các quyết định đã duyệt: Q1–Q5 trong spec, Native tuần tự, timeout 30 giây/child, test mục tiêu trước, chỉ chạy full suite khi đủ điều kiện. Yêu cầu Bài 7 thay thế giả định “ưu tiên checkout main”: implementation dùng repository root của worktree được owner giao; không tự chuyển sang checkout khác.

Đề xuất kỹ thuật cho revision: phương án A ở §6 giữ T8 chạy script trực tiếp và cài guard bằng fixture `sitecustomize.py` tạm. Không đổi hợp đồng D5; owner duyệt phương án này cùng revision plan. Phương án B chỉ được chọn sau khi owner duyệt thay đổi D5.

- **G1 — Approval/provenance:** intent/spec đúng hash đã duyệt; revision plan được owner duyệt lại, tracked và có digest ngoài chính file. Worktree thực thi phải nhận đúng revision đó trước S1. Không dùng bản plan cũ còn Approved để bỏ qua review này.
- **G2 — Workspace/source:** ghi root, branch, HEAD, status, source hashes và diff. Chọn branch/worktree thực thi tường minh; nếu target/dependency source đã đổi, review delta trước khi sửa. Không reset/stash/ghi đè thay đổi chưa commit.
- **G3 — Target environment/harness:** interpreter tuyệt đối đã được chọn; ghi runtime version, prefix, nguồn module/dependency. Config tạm đặt trước import `tests`. Preservation tests và guard probes phải thực sự đạt; xác nhận child đúng source/worktree, encoding, entry point và setup markers trước RED.
- **G4 — Broad regression:** ghi dependency origins và import/collection kết quả thật; rà soát fake providers, cấu hình tạm và cơ chế chặn egress có bằng chứng nhưng cho phép loopback OAuth. Ghi cơ chế/lệnh kiểm chứng, kết quả control và phạm vi áp dụng. Chưa có cơ chế/đủ dependency thì không chạy full suite; báo gap và xin owner chấp nhận tập regression phù hợp, không tự nhận full-suite PASS/offline.
- **G5 — Acceptance:** RED đúng nguyên nhân, logic GREEN trước đổi messages, final GREEN, regression phù hợp và review đủ ba file mới/cũ. Failures/skips/unexecuted items phải xuất hiện trong báo cáo.

Approval của plan không phải lệnh thực thi hoặc bằng chứng runtime.

## 2. Baseline cập nhật và kiểm tra hash

### Snapshot chỉ đọc ngày 2026-10-13

| Nơi/hạng mục | Đã kiểm tra trong lượt revision |
| --- | --- |
| Checkout sửa tài liệu | `novel-pipeline-v2`, branch `main`, HEAD `ef085c089709bc0dac4fd13366743ce07720bf3c`. Trước revision chỉ có `.claude/agents/plan-auditor.md` untracked. |
| Worktree smoke ứng viên | `novel-pipeline-l7-smoke`, branch `lesson7-smoke`, cùng HEAD, status sạch; không có `.venv`. Không sửa worktree này. |
| Worktree chapters | `novel-pipeline-l7-chapters`, branch `lesson7-chapters`, cùng HEAD, status sạch. Không sửa worktree này. |
| Target source | `verify.py`, `INSTALL.md` tracked và không đổi; `tests/test_verify.py` chưa tồn tại. |
| Lịch sử | `ef085c0` có thay đổi frontend/design/artifacts; không thể nói mọi commit sau `1f1d969` chỉ sửa tài liệu. Diff từ `1f1d969` đến HEAD cho verify/INSTALL/tests/chapters/config/chunking/pipeline/cleaning/filtering rỗng. |
| Plan cũ | Hash `629c7162b964ecc2787933e1c44c3f1fbc8e58e39d0adbe7f99ca335b579e9d1`; đây là lịch sử, không phải digest của revision mới. |
| Python hiện có | Checkout sửa tài liệu có venv; cfg ghi 3.14.7, `include-system-site-packages = true`, executable symlink đến Python hệ thống. Không chạy để xác minh version hoạt động. |
| Metadata dependency | Venv có METADATA FastAPI 0.142.4, httpx 0.28.1, PyQt6 6.11.0, Pillow 12.3.0; cũng có package hệ thống. Metadata không chứng minh import/runtime. Không xác minh pytest hoạt động. |

Các tên worktree trên chỉ là snapshot, không phải đường dẫn dùng trong lệnh implementation. Revised plan hiện chỉ nằm trong checkout sửa tài liệu; hai worktree còn bản cũ cho đến khi owner cho phép chuyển đúng revision đã duyệt. Lượt này không commit/cherry-pick/copy vào chúng.

### Manifest nguồn đã đọc

```text
9b6a2c62ee405a58ee5ec7e9c4744ec749cc0270dd548de04bbba7eb977f6134  intent/verify-smoke-check/intent.md
3d0155ae3290cc6d295dddb849c7ab383a9383c44acea6cdde6c0a2fe18fe5c4  intent/verify-smoke-check/spec.md
dc2891f9b3061be032a8d68330fa2dffa39ef23c7d0a781c50376ca882fdd377  verify.py
a51a6db9b0814760cb24b53fb5910226cae2a422686c2720d95b23b19b34e16a  INSTALL.md
7830dac6b4d22f64bc1de12bbb1cb47685e1aebf54d9248b0da9a7bae11beaf1  tests/__init__.py
2303040aa137d7e59ed956ac5df11659bda88f9ea42f049cd891b2269e52242d  chapters/__init__.py
9db90ee69e6639642a9209ef778c63bd490755ae9371dabd89b8220730c28d44  chapters/numerals.py
7f1745df1e633d8fd61b442a9fc01ec30c15b4f4152228b58942fdc597d8557f  config/settings.py
```

S0 kiểm cả manifest, diff các thư mục liên quan và source của các regression được chọn; hash không thay thế review dependency graph. Hash target chỉ áp dụng trước implementation, không ép khớp sau bản vá.

Không nhúng digest hiện tại của plan vào chính plan: thay bytes để ghi hash sẽ lại đổi hash. Sau owner approval và cập nhật status được phép, tính SHA-256 cuối cùng, ghi bên ngoài file (biên bản/chat duyệt cùng commit), rồi truyền `SMOKE_APPROVED_PLAN_SHA256` vào S0. Không tự lấy hash working file làm giá trị “approved”. Sau mỗi revision phải duyệt/digest lại.

### Addendum cho spec, không sửa spec

- Spec §10: inventory “không có CLAUDE/AGENTS/Skills local” thuộc snapshot cũ. Nay `CLAUDE.md`/`AGENTS.md` tracked từ `80ece86`, Skill `chapter-data-integrity` từ `0b60d19`; agent file mới còn untracked ở checkout sửa tài liệu. Skill integrity không tự kích hoạt cho việc sửa smoke-reporting đơn thuần.
- Spec baseline `1f1d969` là lịch sử; code mục tiêu vẫn khớp hash. Kiến trúc/guidance mới không tự mở rộng scope.
- Intent §7 còn câu hỏi lịch sử; Q1–Q5 đã được spec §3 giải quyết. Không tự mở lại hoặc sửa intent/spec để đồng bộ câu chữ.
- Spec/intent giữ nguyên hash; thay hợp đồng D5/R/N phải được owner duyệt riêng.

## 3. Disposition của review

| Finding | Kết quả đối chiếu / xử lý |
| --- | --- |
| A C1; auditor baseline Major | Có bằng chứng Git: baseline/workspace cũ, venv absent ở worktree smoke. Root/interpreter động và nguồn dependency rõ tại §2/§8. |
| A M1; auditor RED Major | Sửa §5/§7: signal-first, count parser không phụ thuộc nhãn, D3 chỉ T7, thêm S3G. Count 3/4 vẫn cần kiểm; không loại nó khỏi acceptance. |
| A M2; auditor collection Minor | Import module `verify`, không đưa `test_*` production vào globals test; doubles rõ. Khả năng pytest collect/warning là suy luận chưa chạy, không ghi là đã tái hiện. |
| A M3; auditor T5/T6 unclear | T6 kiểm exception thoát helper, converter một call, main bắt lỗi/traceback và các check sau vẫn chạy. T5 có ma trận False/Exception và call order. |
| A M4–M5; auditor launcher Minor | Inline `-c` trong cùng test file; setup 78, unexpected launcher 79; root/path/env/encoding/cleanup và observation rõ. Không thêm file sản phẩm thứ tư. |
| A M6; auditor network Major | Mâu thuẫn T8 trực tiếp/guard là có thật trong plan cũ. Hai phương án §6; chọn đề xuất A, giữ D5. Không tuyên bố offline trước probes/validation. |
| A m1; auditor spec outdated | Addendum §2; không sửa approved spec hoặc phá hash của nó. |
| A m2; auditor hashes | Manifest mở rộng; digest plan nằm trong approval record ngoài file, không dùng self-hash. |
| A m3–m5 | Thêm `九十八 → None`, exact Boolean/int type; RED kỳ vọng 3 methods, 8 failures, 0 errors, exit 1. |
| A m6–m8; auditor encoding | Child UTF-8/bytecode env tự đặt; diff-check test mới; external/system-site venv phải báo origins và rủi ro. |

Các nhận xét không chấp nhận nguyên trạng:

1. “Sau 1f chỉ thay tài liệu” sai với toàn repo; “core phụ thuộc smoke đã đổi” chưa có bằng chứng: scoped Git diff và hashes xác nhận chúng chưa đổi.
2. “PROCEED WITH MINOR FIXES/no Critical” không phải quyền bắt đầu S1 khi còn các Major về RED/harness. Revision cần re-approval và G1–G3.
3. Git trạng thái/hash do subagent chỉ có Read/Grep/Glob báo lại không được coi là phép kiểm Git độc lập; lượt này đã kiểm bằng Git/hash.
4. Không patch `verify.chinese_to_int` hoặc `chapters.numerals.chinese_to_int` cho code hiện tại: `verify.py:25` import re-export tại `chapters/__init__.py:3`. Parser tại `chapters/numerals.py:192` dùng binding nội bộ nên injection re-export không lan sang chapter detection hiện tại.
5. `Settings()` tại `verify.py:57` dùng dataclass defaults (`config/settings.py:112`), không gọi `load()`; config không quyết định check hiện tại. Vẫn giữ config tạm theo N2, không loại isolation.

## 4. Global constraints và deliverables

- Giữ năm fixture, bốn checks và thứ tự; checker trả Boolean; `main()` trả `type(rc) is int`, giá trị 0/1; giữ `sys.exit(main())`.
- Không sửa converter/chunking/UI/API/dependencies, báo cáo lịch sử hoặc approved intent/spec.
- Không thêm production hook/flag/class/parameter; không chuyển import để hỗ trợ test.
- Data cố định/giả; không secrets/tài khoản thật/provider calls. Không mở rộng `Exception` thành `BaseException`.
- Native tuần tự trong worktree thực thi; không reset/stash/ghi đè hoặc stage ngoài nhiệm vụ.
- Mọi kết quả runtime bên dưới là kỳ vọng, chưa quan sát; Python 3.11+ floor không được chứng nhận chỉ bằng một interpreter.

| File sản phẩm | Thao tác / mục tiêu |
| --- | --- |
| `verify.py` | Aggregate mismatch và ba messages D3; giữ runner/entry point. |
| `tests/test_verify.py` | Tạo mới toàn bộ tests, helpers, launcher text và nội dung guard fixture. |
| `INSTALL.md` | Bổ sung tối thiểu vào `## Tests and migration parity`: lệnh từ repo root, 0/1 và giới hạn smoke checks. |

Temporary `sitecustomize.py`/config là tài nguyên runtime trong `TemporaryDirectory`, không là deliverable repo thứ tư. Revision plan là tài liệu chuẩn bị; không nằm trong bản vá sản phẩm ba file.

## 5. Test design, imports và binding

### Imports/isolation trong tests/test_verify.py

- `REPO_ROOT = Path(__file__).resolve().parents[1]`; `VERIFY_PATH = REPO_ROOT / "verify.py"`.
- Dùng `import verify` (module), không `from verify import test_*`, không star import/alias hàm production vào tên `test_*` tại module test.
- Commands chạy từ execution root bằng `python -m ...`, bỏ inherited PYTHONPATH; assert `Path(verify.__file__).resolve() == VERIFY_PATH`. Sai module/root là harness error. `import verify` hiện chỉ import sys/Path và định nghĩa hàm, không tự chạy checks (`verify.py:4–5,124`).
- Config tạm được wrapper đặt trước import package `tests`; `tests/__init__.py:10–24` có mkdir nếu override thiếu. setUp đặt config/output riêng và network patches trước import/application calls; context/addCleanup restore kể cả assertion lỗi.
- Patch `chapters.chinese_to_int` trong context trước gọi checker; lưu original. Sau mỗi test assert re-export được restore và `assertIs(chapters.chinese_to_int, chapters.numerals.chinese_to_int)` trên baseline đã đối chiếu. Không `create=True`.
- Không vô hiệu hóa collection của production hoặc thêm pytest config ngoài scope. Pytest collect-only phải thấy đúng 10 methods của `VerifySmokeCheckTests`, không các hàm smoke nhập vào globals.
- Wrapper/child dùng -B và bytecode env trước startup. Bỏ wrapper có thể tạo __pycache__ (đã ignored); không hứa set flag trong test sẽ ngăn bytecode của chính module trước import.

### Doubles và expectations

`main()` và numeral checker thật ở mọi test main/false positive. In-process T3–T7 dùng `patch.object(verify, name, ...)` cho ba check `test_imports`, `test_chapter_detection`, `test_chunking`; main lookup globals khi gọi (`verify.py:95–100`). Không dùng các target này trong runpy child; T8/T9 giữ cả bốn checks thật.

T4/T5/T7 success branches dùng converter response map literal để cô lập aggregator; T1 và lượt restored của T10 kiểm converter thật. T5 thay kết quả/exception của đúng check không liên quan, không tuyên bố chứng minh thuật toán check đó.

Private harness interfaces trong cùng test file:
- `_summary_counts(stdout: str) -> tuple[int, int]`: lấy đúng một summary line, hỗ trợ nhãn baseline `Results: P/T tests passed` và D3 `Smoke checks reporting success: P/T`; không đếm diagnostics/markers.
- `_run_verify_child(*, inject_mismatch: bool) -> subprocess.CompletedProcess[str]`: sinh guard/launcher/env tạm, chạy bounded child, trả captured output sau cleanup; setup/launcher failures phát test-only `HarnessError`, không giả lập returncode.
- Mismatch assertions tìm đúng diagnostic line của input (actual/expected và dấu thất bại), không tìm None/12 trong toàn bộ stdout.

| ID / method trong VerifySmokeCheckTests | Assertions và phạm vi |
| --- | --- |
| T1 `test_numerals_matching_cases_pass` | Literal outputs của converter thật khớp năm fixture; checker thật `assertIs(result, True)`; None/None là success. |
| T2 `test_numerals_mismatch_at_each_position_fails` | Sáu subtests ở bảng dưới. Đầu tiên `assertIs(result, False)`; failure message chứa captured diagnostics/calls. Sau đó exact input-line, call_args_list đủ năm input đúng thứ tự và converter call_count=5. Mismatch không short-circuit. |
| T3 `test_main_numeral_mismatch_returns_one` | Converter 九十八→97, các case khác literal đúng; ba doubles True. Type int rồi rc=1 là assertion tín hiệu trước count (3,4); converter 5 calls, ba doubles mỗi cái 1 call; không assert D3. |
| T4 `test_main_all_checks_success_returns_zero` | Matching map + ba doubles True; type int, rc=0, counts (4,4), đủ call order; không đếm năm cases như năm checks. |
| T5 `test_main_other_check_failures_continue` | Sáu subtests: mỗi ba doubles lần lượt False hoặc RuntimeError cố định; còn lại True. Matching converter, main/checker thật; int 1, (3,4), mỗi check vẫn gọi một lần theo thứ tự, đặc biệt các check sau lỗi. |
| T6 `test_main_converter_exception_returns_one` | Hai patch contexts riêng: helper phải propagate RuntimeError; rồi main phải catch chính exception đó. Chi tiết exception boundary bên dưới. |
| T7 `test_summary_messages_are_scoped` | Hai subtests success/failure có int rc/count đúng trước text. Chỉ test này kiểm exact D3 count/success/failure, emitted output không chứa whole-application-readiness claim; không source-string test. |
| T8 `test_process_success_runs_actual_script` | Script trực tiếp, cả bốn checks thật; natural rc=0, (4,4), all-phase diagnostics, observer main_calls=1/main return int 0, guard evidence; stderr không Traceback. Không khóa nhãn D3. |
| T9 `test_process_mismatch_runs_main_guard_and_exits_one` | Child injection 九十八→-987654321; real checks/main/guard. Returncode int 1 trước count/text; exact sentinel ở diagnostic input đó, năm numeral lines, chapter/chunk output, (3,4), observer main_calls=1/int return 1, guard evidence. |
| T10 `test_repeated_runs_do_not_leak_fault_or_config` | In-process và child lượt inject rồi normal với config/temp riêng. Restore converter/network/env; synthetic network probes bị chặn, reset probe counters trước target; normal results không giữ sentinel. Child return/reap và TemporaryDirectory cleanup kiểm được; không suy từ “timeout không xảy ra” rằng mọi process khác trên máy đã chết. |

Literal T2 (expected độc lập, chỉ một vị trí sai/subtest):

| Input | Expected | Injected actual |
| --- | --- | --- |
| 九十八 | 98 | 97 |
| 一百零五 | 105 | 104 |
| 两万三千 | 23000 | 22999 |
| 一二 | None | 12 |
| 十十 | None | 20 |
| 九十八 | 98 | None |

Không thêm fixture production thứ sáu. Các vị trí khác dùng literal expected đúng; không suy expected từ converter/checker. Không dùng truthiness để thay equality.

### T6 / exception boundary quan sát được

- Converter raises `RuntimeError("synthetic converter failure")` ngay input 九十八.
- Gọi helper thật trong assertRaisesRegex; converter `assert_called_once_with("九十八")`. Nếu checker tự catch rồi return False, test phải fail.
- Context mới gọi main thật với ba doubles True: type int, rc=1, counts (3,4); converter đúng một call, không case sau; stdout có caught-exception diagnostic, stderr có Traceback và RuntimeError synthetic.
- Ledger/call assertions chứng minh imports chạy trước, chapter detection/chunking chạy sau exception, mỗi double một call. Mismatch thường ở T2 vẫn phải có năm calls; exception không có nghĩa tiếp tục vòng case nội bộ.

## 6. Subprocess, network và entry-point observation

### Hai phương án và lựa chọn

| Phương án | Cách làm / quan hệ spec |
| --- | --- |
| **A — Đề xuất dùng** | T8 vẫn `[sys.executable, "-B", str(VERIFY_PATH)]`. Test tạo sitecustomize.py trong temp dir, PYTHONPATH child chỉ trỏ bootstrap đó để cài guard/observer trước script. T9 cùng bootstrap + inline -c launcher/runpy. Giữ D5 path 1 trực tiếp và path 2 runpy; không thêm sản phẩm/dependency. |
| **B — Không chọn trong revision** | Guard/observer nằm trong inline -c launcher cho cả T8/T9, sau đó runpy file thật dưới __main__. Vẫn kiểm guard thật, nhưng thay đường success trực tiếp đã duyệt ở D5:189–190; cần owner duyệt amendment/re-approve spec trước khi dùng. |

Không chọn T8 trực tiếp “không có guard” rồi tuyên bố AT9 offline. Không thêm launcher/sitecustomize cố định vào repository hoặc chỉnh firewall toàn máy. A chỉ là thiết kế: chưa chứng minh bootstrap/profile/network patches hoạt động trên interpreter thực thi.

### Child protocol của A

- T8 command như bảng; T9 `[sys.executable, "-B", "-c", launcher_text, str(VERIFY_PATH)]`. launcher_text và guard source là string trong tests/test_verify.py; file guard chỉ sinh trong TemporaryDirectory.
- `cwd=REPO_ROOT`; T9 insert root vào sys.path trước import chapters. T8 script dir tự là root; bootstrap dir chỉ phục vụ startup. Kiểm module source paths thuộc worktree; không lấy code từ vị trí external venv.
- Env copy os.environ, không dump values; bỏ inherited PYTHONPATH/PYTHONHOME/PYTHONSTARTUP/PYTHONUSERBASE, rồi set PYTHONPATH duy nhất guard_dir, PYTHONNOUSERSITE=1, PYTHONUTF8=1, PYTHONIOENCODING=utf-8, PYTHONDONTWRITEBYTECODE=1, NOVEL_PIPELINE_CONFIG_DIR=temp/config, QT_QPA_PLATFORM=offscreen. Env truyền expected verify/root/temp paths cho bootstrap, không production fault switches.
- Không dùng -I/-S/-E vì chúng có thể bỏ bootstrap/env. Interpreter là sys.executable của runner, không bare python hoặc canonicalize symlink làm mất venv context.
- Guard patch `socket.socket.connect`, `connect_ex`, `socket.create_connection`, `socket.getaddrinfo` trước application logic; mọi call raise `RuntimeError("SMOKE_NETWORK_BLOCKED")`, không log host/address/credential.
- Bootstrap self-check binding rồi synthetic probes cho bốn primitives, xác nhận bị chặn trước kết nối; reset probe counters trước target. Parent requires `SMOKE_GUARD_READY`, `SMOKE_GUARD_PROBES=4`, report operational attempts=0 và bindings vẫn active. Mất marker/probe/setup là harness error; attempt trong logic là isolation failure, không false-positive RED.
- Observer dùng sys.setprofile để đếm call/return của chính `main` có code filename VERIFY_PATH và frame globals __name__=="__main__"; atexit xuất một `SMOKE_OBSERVATION` record với main_calls, main_return_type/value và network attempts. Không wrap/stub main, patch sys.exit, bắt SystemExit hay viết lại source. Main_calls khác 1 là entry-point assertion failure.
- T9 setup import chapters đúng worktree, giữ original converter; patch re-export, delegate original cho các input khác, inject sentinel cho 九十八. Không import verify rồi gọi main. Gọi runpy.run_path(file, run_name="__main__"); file quyết định natural exit qua sys.exit.
- Compile-check guard/launcher strings trong helper trước khi spawn; syntax failure là HarnessError/ERROR, không chạy child. Bootstrap installation được bọc handler Exception và terminate 78 (stderr marker được flush; không chỉ raise để site startup bỏ qua). Nếu bootstrap không được nạp hoặc không phát đủ health records, parent vẫn báo harness error dù script tình cờ thoát 0.
- Reserved **78** = bootstrap/launcher setup failure với `SMOKE_HARNESS_SETUP_FAILED`; **79** = unexpected Exception trong launcher/runpy với `SMOKE_HARNESS_RUN_FAILED`. Handler chỉ catch Exception, không SystemExit/BaseException; để SystemExit từ script truyền ra tự nhiên.
- Parent phân loại 78/79, OSError launch, decode error, TimeoutExpired là HarnessError/ERROR trước khi dùng chúng làm chứng cứ rc=1. Các diagnostics/missing markers cũng được kiểm; không coi mọi exit 1 là script numeral failure.
- `subprocess.run(capture_output=True, text=True, encoding="utf-8", errors="strict", check=False, timeout=30, cwd=REPO_ROOT, env=child_env)`. run chờ/reap child; timeout kill/reap child trực tiếp rồi phát lỗi. Capture failure output, cleanup temp bằng context manager kể cả error; không có descendants được thiết kế.
- T8/T9 giữ import/chapter/chunk checks thật. Nếu T8 baseline không đạt hoặc check khác hỏng, ghi cause và dừng nghiệm thu AT8; không stub/fix ngoài scope.

Guard chỉ chứng minh các Python network primitives đã nêu khi probes/observations thực sự đạt. Không suy rộng thành sandbox cho native code, processes khác hoặc toàn suite. Toàn suite cần G4 riêng: test OAuth `tests/test_youtube_auth.py:150–186` dùng loopback thật; guard deny-all của smoke không được phủ lên nó.

## 7. Thứ tự implementation và traceability

Tất cả bước sau chưa chạy:

- [ ] **S0 — Preflight:** G1/G2, root/branch/interpreter rõ, hashes và dependency provenance; config trước imports.
- [ ] **S1 — Tests/harness:** tạo test file T1–T10 + private helpers/protocol §5–6; production giữ baseline.
- [ ] **S1H — Harness/preservation checkpoint:** chạy T1/T4/T5/T6/T8. Expected PASS/exit 0, guard probes/observer đúng. ERROR/baseline failure phải xử lý/phân loại trước RED; không sửa product để làm harness chạy.
- [ ] **S2 — Signal RED:** chạy đúng T2/T3/T9. Signal-first, evidence fault và main/entry-point thật. Kỳ vọng 3 methods, 8 failures (T2 sáu subtests + T3 + T9), 0 errors, runner exit 1 trên baseline phù hợp.
- [ ] **S3 — Logic only:** sửa aggregate checker, không đổi messages/import/signature/exception boundary; evaluate năm cases khi chỉ mismatch.
- [ ] **S3G — Logic GREEN:** chạy lại T2/T3/T9 và T6: PASS/exit 0. Chạy T7 riêng: expected 2 message failures/0 errors/exit 1 vì D3 chưa sửa. Không dùng T7 RED làm bằng chứng false positive.
- [ ] **S4 — Messages:** chỉ thay count/success/failure theo D3; giữ real runner/entry point.
- [ ] **S5 — Final GREEN:** toàn module unittest PASS/exit 0; optional pytest collection/run nếu hỗ trợ. AT9 cần guard/cleanup chứng cứ thực tế.
- [ ] **S6 — INSTALL:** minimal insertion vào Tests and migration parity, theo R8/D6.
- [ ] **S7 — Regression:** bounded related suite trước; full suite chỉ khi G4 đáp ứng, không silent skip required evidence.
- [ ] **S8 — Review:** diff cả test mới, chỉ ba product files, command/output/type/diagnostics/checkpoint evidence và validation gaps.

| Steps | Requirements / Design / Acceptance | Completion |
| --- | --- | --- |
| S0/S1/S1H | N1–N4; D4–D5; AT1/AT4–AT6/AT8–AT9, AR1 | Đúng approved inputs/worktree; preservation/harness thật đạt. |
| S2 | R2/R4/R7; D1/D2/D4/D5; AT2/AT3/AT8, AR2 | Tín hiệu baseline True/0 trong khi diagnostic chứng minh injection; không ERROR. |
| S3/S3G | R1–R5/R7; D1/D2/D4/D5; AT1–AT6/AT8, AR2 | Logic GREEN khi messages còn baseline. |
| S4/S5 | R1–R7; D1–D5; AT1–AT9 | Exact D3 và final runtime output/exit/isolation đạt. |
| S6 | R8; D6; AR3 | Command, 0/1, limits; historical reports untouched. |
| S7/S8 | R1–R8/N1–N4; D1–D6; AR1–AR3 | Appropriate regression, full-scope diff và before/after evidence. |

Review focus: sticky failure, numeric→None và None→numeric, wrong namespace,
swallowed converter exception, launcher rc=1 masquerading as script failure,
missing __main__, failed guard bootstrap, polluted import path/shared venv.

### RED/ERROR classification

| Kết quả | Kỳ vọng / handling |
| --- | --- |
| Valid RED | Primary assertIs(False) hoặc integer rc=1 fail vì actual True/0. Failure message ghi actual/diagnostics/child observation. Summary là 8 failures, 0 errors, Ran 3 tests, exit 1. |
| Assertion FAIL khác | Missing fault, wrong main_calls/count/type, real unrelated check fail: entry/harness/baseline defect; không phải AR2. Review trước sửa product. |
| ERROR / launcher 78/79 / timeout | Import/path/setup/decode/guard error: sửa harness hoặc báo dependency thiếu; không gọi RED/GREEN. Wrong local-module resolution là harness, không gộp mọi ImportError vào environment. |
| Zero tests / wrong ID | Invalid evidence. Stdlib Python 3.14 đã đọc tại `/usr/lib/python3.14/unittest/main.py:11,274–275` định nghĩa exit 5 cho zero tests; chưa chạy và interpreter thực thi có thể khác. Luôn kiểm Ran-count/errors, không chỉ exit. |
| Logic GREEN | S3G signal tests pass, T7 còn message RED được ghi riêng. |
| Final GREEN/regression | Exact selected checks pass; báo skips/failures và suite không chạy, không lấy báo cáo lịch sử thay output. |

## 8. Commands sau re-approval (không chạy trong revision)

Chạy từ worktree thực thi đã được owner giao. Operator cung cấp ba giá trị từ
approval/environment record: SMOKE_EXECUTION_BRANCH, SMOKE_PYTHON (đường dẫn tuyệt
đối interpreter đã tồn tại), SMOKE_APPROVED_PLAN_SHA256. Không tự điền bằng current
branch/hash, không hardcode checkout main.

### S0 — Workspace và integrity

```bash
SMOKE_REPO_ROOT=$(git rev-parse --show-toplevel) || exit 2
cd -- "$SMOKE_REPO_ROOT" || exit 2
: "${SMOKE_EXECUTION_BRANCH:?Set owner-designated execution branch}"
: "${SMOKE_PYTHON:?Set absolute approved interpreter path}"
: "${SMOKE_APPROVED_PLAN_SHA256:?Set digest from owner approval record}"
case "$SMOKE_PYTHON" in /*) ;; *) exit 2 ;; esac
test -x "$SMOKE_PYTHON" || exit 2
test "$(git branch --show-current)" = "$SMOKE_EXECUTION_BRANCH" || exit 2
git rev-parse --show-toplevel
git rev-parse HEAD
git worktree list --porcelain
git merge-base --is-ancestor ef085c089709bc0dac4fd13366743ce07720bf3c HEAD
git --no-optional-locks status --short --untracked-files=all
git diff --cached --name-only
git ls-files --error-unmatch intent/verify-smoke-check/intent.md intent/verify-smoke-check/spec.md intent/verify-smoke-check/plan.md
printf '%s  %s\n' "$SMOKE_APPROVED_PLAN_SHA256" intent/verify-smoke-check/plan.md | sha256sum -c -
sha256sum intent/verify-smoke-check/intent.md intent/verify-smoke-check/spec.md verify.py INSTALL.md tests/__init__.py chapters/__init__.py chapters/numerals.py config/settings.py
git diff --stat 1f1d9699663c46fe1115e2eb5745ead787af24b1 HEAD -- verify.py INSTALL.md tests chapters config chunking pipeline cleaning filtering
git diff -- verify.py INSTALL.md tests/__init__.py chapters/__init__.py chapters/numerals.py config/settings.py
test ! -e tests/test_verify.py
```

So từng digest với manifest §2, không chỉ quan sát sha256sum exit 0. Mỗi lệnh cần
đọc exit/output; shell list không tự là gate PASS. Nếu ancestor/hash/status khác,
review delta và cập nhật approval record, không reset. Record regression-source
hashes và diff khi chúng khác snapshot.

Interpreter: ưu tiên venv riêng nếu đã có; không cài/tạo venv bằng plan này.
Dùng venv ngoài worktree cần Technical Lead xác nhận quyền dùng, dependency ổn định,
không pip/upgrade khi hai phiên dùng chung và module source luôn từ execution root.
Ghi pyvenv.cfg, sys.prefix/base_prefix, sys.path/module origins; system-site-packages
làm environment không hermetic. Giữ absolute venv/bin/python path, không thay bằng
symlink target /usr/bin/python. Không có lựa chọn hợp lệ thì G3 chưa đạt.

### Wrapper dùng cho từng lượt validation

Khai báo trong shell hiện tại, không lưu thành file repo:

```bash
smoke_run() (
  cd -- "$SMOKE_REPO_ROOT" || exit 2
  smoke_tmp=$(mktemp -d -t novel-verify.XXXXXX) || exit 2
  trap 'rm -rf -- "$smoke_tmp"' EXIT
  unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE
  export NOVEL_PIPELINE_CONFIG_DIR="$smoke_tmp/config"
  export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
  export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 QT_QPA_PLATFORM=offscreen
  "$SMOKE_PYTHON" -B "$@"
)
smoke_run -c 'import sys, importlib.util; print(sys.version); print("executable", sys.executable, "prefix", sys.prefix, "base_prefix", sys.base_prefix); print("sys.path", sys.path); print({n: (s.origin if (s := importlib.util.find_spec(n)) else None) for n in ("pytest", "PyQt6", "httpx", "fastapi", "PIL")})'
```

Không dump os.environ. find_spec/metadata chỉ là inventory, không chứng minh import
hay test hoạt động. Wrapper cách ly config/encoding/bytecode; network guard thuộc
harness T1–T10, wrapper không tự chặn egress cho regression/full suite.

### S1H — Preservation và baseline runtime từ T8

```bash
smoke_run -m unittest -v \
  tests.test_verify.VerifySmokeCheckTests.test_numerals_matching_cases_pass \
  tests.test_verify.VerifySmokeCheckTests.test_main_all_checks_success_returns_zero \
  tests.test_verify.VerifySmokeCheckTests.test_main_other_check_failures_continue \
  tests.test_verify.VerifySmokeCheckTests.test_main_converter_exception_returns_one \
  tests.test_verify.VerifySmokeCheckTests.test_process_success_runs_actual_script
```

Expected 5 methods, PASS/exit 0, không ERROR; baseline script run nằm trong T8 có
guard. Bỏ standalone `smoke_run verify.py` của plan cũ vì không có guard bootstrap.

### S2 — Signal RED

```bash
smoke_run -m unittest -v \
  tests.test_verify.VerifySmokeCheckTests.test_numerals_mismatch_at_each_position_fails \
  tests.test_verify.VerifySmokeCheckTests.test_main_numeral_mismatch_returns_one \
  tests.test_verify.VerifySmokeCheckTests.test_process_mismatch_runs_main_guard_and_exits_one
```

Expected exit 1/Ran 3/8 failures/0 errors theo §7, không `|| true`. Ghi dòng
assertion đầu tiên và fault output; bất kỳ sai lệch count/cause nào đều phải giải
thích, không đổi expected để ép đạt RED.

### S3G — Logic checkpoint trước messages

```bash
smoke_run -m unittest -v \
  tests.test_verify.VerifySmokeCheckTests.test_numerals_mismatch_at_each_position_fails \
  tests.test_verify.VerifySmokeCheckTests.test_main_numeral_mismatch_returns_one \
  tests.test_verify.VerifySmokeCheckTests.test_process_mismatch_runs_main_guard_and_exits_one \
  tests.test_verify.VerifySmokeCheckTests.test_main_converter_exception_returns_one
smoke_run -m unittest -v tests.test_verify.VerifySmokeCheckTests.test_summary_messages_are_scoped
```

Lệnh đầu expected PASS/exit 0; lệnh thứ hai expected hai message failures/exit 1,
0 errors. Lưu hai kết quả riêng; không để exit của lệnh sau che mất checkpoint đầu.

### S5 — Final GREEN và optional collection

```bash
smoke_run -m unittest tests.test_verify -v
```

Expected 10 methods, no failures/errors, exit 0. Chỉ nếu pytest đã được xác nhận:

```bash
smoke_run -m pytest -p no:cacheprovider --collect-only -q tests/test_verify.py
smoke_run -m pytest -p no:cacheprovider -q tests/test_verify.py
```

Collection phải đúng 10 class methods, không extra production tests. Chưa chạy thì
không khẳng định absence của PytestReturnNotNoneWarning hay pytest compatibility.

### S7 — Related regression; full suite có gate riêng

```bash
smoke_run -m unittest -v tests.test_chapter_clock_lines tests.test_headless_service
```

Hai module dùng unittest.TestCase (`test_chapter_clock_lines.py:20`,
`test_headless_service.py:15`). Có pytest thì bổ sung:

```bash
smoke_run -m pytest -p no:cacheprovider -q tests/test_verify.py tests/test_chapter_normalization.py tests/test_chapter_clock_lines.py tests/test_headless_service.py
```

Full suite chỉ sau G4 và trong cơ chế egress/loopback đã kiểm chứng, không chỉ
wrapper ở trên:

```bash
smoke_run -m pytest -p no:cacheprovider -q
```

Không dùng unittest discovery thay collection pytest fixture `tmp_path`.
Nếu G4 không đạt, báo rõ chưa chạy full suite và bằng chứng subset; không tự thêm
dependency, sửa tests cũ hoặc chạy provider thật.

### S8 — Diff gồm test mới

```bash
git diff --check -- verify.py INSTALL.md
git diff -- verify.py INSTALL.md
git diff --no-index --check -- /dev/null tests/test_verify.py
git diff --no-index -- /dev/null tests/test_verify.py
git --no-optional-locks status --short --untracked-files=all
git diff --cached --name-only
```

Diff --no-index có thể trả 1 vì file mới khác /dev/null; đọc whitespace/error output,
không coi exit đó là test FAIL/PASS. Chỉ ba product paths được thay đổi; output
validation ghi trong báo cáo/chat, không thêm log/launcher cố định vào repo.
Không tự commit/push hoặc sửa hai worktree khác.

## 9. Approved messages và INSTALL review

D3 giữ nguyên exact text:

```text
Smoke checks reported success. Full application validation was not performed.
One or more smoke checks failed. Review the results above.
Smoke checks reporting success: {passed}/{total}
```

T7 kiểm emitted text/count ở cả hai nhánh; không khóa separator/decorations khác.
R8 insertion chỉ ở Tests and migration parity: `python verify.py` từ root,
0 là các checks reported success, 1 là failure/caught exception; không full
application validation/provider parity, chỉ numeral signal được sửa. Không đổi
historical pass counts hoặc architecture/setup ngoài mục này.

## 10. Rủi ro, alternatives và rollback

| Rủi ro | Kiểm soát / điều chưa xác minh |
| --- | --- |
| Shared external venv đổi trong lúc hai sessions chạy | Explicit interpreter/provenance và freeze usage; metadata/runtime origins chưa chứng minh dependency hoạt động. |
| Bootstrap silently fails hoặc Python bỏ PYTHONPATH | Mandatory health/probe markers, reserved 78, no -I/-S/-E; G3 runtime checkpoint trước production. |
| Launcher rc=1 che import/setup | Reserved 78/79, main observer, exact injected line, later-check diagnostics/counts. |
| Guard chỉ Python-level / full suite cần loopback | Giới hạn claim; G4 riêng, không áp deny-all lên toàn suite. |
| Call short-circuit hoặc exception bị swallow | T2 call_count=5; T6 helper raises/main catches, count=1 và later checks chạy. |
| API/stdout compatibility | Callable interfaces giữ; stdout D3 thay có chủ đích đã duyệt; consumer parsing hiện chưa xác minh. |
| Plan ở worktree vẫn là bản cũ | G1 exact approved digest/revision delivery; không tự sửa/cherry-pick vào hai worktree trong lượt revision. |

Không chọn early-return khi mismatch (R3); đổi runner sang pytest; chuyển import;
stub checker/main; chỉ test main return thay process; zero-network claim chỉ từ
không có provider calls quan sát được.

Rollback chỉ sau authorization: hoàn tác đúng task hunks trong verify/INSTALL,
xóa test mới chỉ khi chắc không chứa sửa của người khác. Không reset --hard hoặc
rollback toàn tree; nếu commit product riêng thì revert đúng commit được phép.
Khôi phục baseline cũng khôi phục false positive, phải báo rõ.

## 11. Owner decisions và readiness

- **O1 — Owner:** re-approve revision plan và phương án A; capture final approved
  digest/commit bên ngoài file, chuyển đúng revision vào execution worktree bằng
  hành động được cho phép riêng. Không sửa spec trong lượt này.
- **O2 — Technical Lead/operator:** chỉ định execution branch và absolute interpreter.
  External/system-site venv cần xác nhận usage/provenance; không auto chọn main venv.
- **O3 — Technical Lead/QA, owner acceptance:** đáp ứng G3/G4 bằng runtime evidence;
  nếu full suite unavailable, owner chấp nhận tập regression và gap rõ ràng.
- **Alternative B:** chỉ nếu owner muốn, phải duyệt amendment D5/spec trước chọn;
  không phải mặc định hoặc cách tự vượt lỗi của A.

**Assessment:** Ready for owner review/re-approval về nội dung kế hoạch; **chưa Ready
for implementation** khi G1–G3 chưa đạt. Không có bằng chứng runtime để gọi acceptance
PASS. Nếu A không qua harness checkpoint, báo Changes Required và review phương án
thay thế; không âm thầm đổi D5.

## 12. Self-review / handoff

- Rủi ro cao nhất là observer/guard/launcher tạo chứng cứ giả; S1H và signal-first RED
  là gates trước product.
- Không có deliverable sản phẩm thứ tư, source algorithm/UI/dependency change.
- T5 chỉ aggregator, không correctness của các check khác; T8/T9 mới là process proof.
- Tránh tự chứng nhận Python 3.11+, offline sandbox hay pytest từ metadata.
- Agent mới có root/interpreter/input-digest gates, exact test names/data,
  doubles/binding, exception/call-count contracts, process protocol và commands.
- Những phần chưa kiểm chứng được giữ là gates/decisions, không biến thành facts.
  Các checkbox và trạng thái implementation tiếp tục Not started.
