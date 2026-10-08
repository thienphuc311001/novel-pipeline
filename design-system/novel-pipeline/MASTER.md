# Novel Pipeline — UI design system

The interface is a local production workspace for operators processing many chapter groups. The main tasks are selecting a batch, tracking progress, and recovering failed work. Preserve the existing import, normalization, TTS, video, YouTube, and session APIs.

## Layout — "choose and next" wizard

- One step on screen at a time: Bản thảo → Chia nhóm → Âm thanh → Video → YouTube. A slim top bar holds the project name, connection state, Phiên and Thiết lập; below it a 5-dot stepper (clickable, with per-stage counts).
- Each step is one card: a short title, only the choices the step needs (chips, tap-to-select group grid, image pickers), and a footer with **Quay lại** and exactly one primary action. When the step is done, the primary becomes **Tiếp tục**.
- Everything else (path inputs, text editor, chunk recovery, per-group inspection, exports, duplicate upload) lives in a collapsed **Tùy chọn nâng cao** section.
- Multi-job steps run as one click via `runSteps` (import → normalize, thumbnail → TTS); the next job starts only after the previous one completes.
- Jobs show in a bottom progress bar only while running or just failed; logs open on demand from it (or the Nhật ký button).
- Group picker preselects groups not yet done for the current stage; selection is shared across audio, video and YouTube. Steps warn and offer to drop selected groups missing a prerequisite (audio for video, video for YouTube).
- Autosave runs in the background and never disables controls; user actions wait for an in-flight save.
- Main column max 768px; works down to 375px without horizontal scrolling.

## Visual language

Minimal, calm, light neutral surface with restrained green accents. No decorative charts, gradients, or remote image assets.

Semantic tokens live in `frontend/src/index.css`: background `#f4f7f8`, foreground `#202d34`, primary `#176b4d`, muted text `#5d6e78`, danger `#b42f3a`. Components use semantic tokens, not new palette values. Step cards use 16px radii and a soft shadow; inner controls 8–12px.

Use the system sans-serif font stack for Vietnamese text without a required network font request. Monospace and tabular figures are for stage numbers, progress, and logs. Use the existing Lucide SVG icon family with consistent sizes; decorative icons are hidden from assistive technology.

## Behavior and status

- TTS is complete only with `tts_status = Completed` and an MP3 that is not reported missing. Partial audio never completes the stage.
- Video counts describe recorded MP4s; YouTube counts describe video IDs, not public publication. Backend validation remains authoritative.
- Show queued, running, and stopping labels accurately. Selection and production controls lock while a job is active.
- Preserve selected group IDs across audio, video, and YouTube. Search and pagination do not discard hidden selections.
- File upload is the primary import path. Absolute paths and detailed options use progressive disclosure.
- Keep confirmation dialogs for replacing source text, deleting groups, partial merges, and duplicate uploads.
- Keyboard focus follows route changes. Forms have visible labels; status includes text and never depends on color alone.
- Honor reduced motion. Keep visible focus indicators and avoid animation that changes layout bounds.

## Verification

Build and typecheck the frontend. Run the stage-summary tests. Exercise import, normalization, grouping, shared selection, TTS planning, per-group inspection, and confirmation cancellation in a real browser. Review all routes at 375, 768, 1024, 1440, and 1920px, including empty, error, and active-job states.
