"""Qt-free consumers of the existing group media/provenance contracts.

Batches are ordered, preserve completed artifacts on cancellation, and report
``status='partial'`` whenever any selected group failed. Only explicitly safe
YouTube errors may cross this service boundary.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import subprocess
import threading
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path

from pipeline.document import PipelineStateError

MEDIA_ACTIONS = {
    "prepare", "thumbnail", "tts", "merge_partial", "edit_chunk", "video",
    "preview", "youtube_connect", "youtube_disconnect", "upload",
    "youtube_metadata", "youtube_retry_thumbnail", "youtube_retry_playlist",
}
_BATCH_ACTIONS = {"prepare", "thumbnail", "tts", "merge_partial", "video", "upload"}
_YOUTUBE_ACTIONS = {action for action in MEDIA_ACTIONS if action.startswith("youtube_")} | {"upload"}
_FATAL_VIDEO_ERRORS = (
    "no space left on device", "permission denied", "read-only file system",
    "no such file or directory", "error opening input",
    "invalid data found when processing input", "inputs changed", "input disappeared",
)


class MediaCancelled(RuntimeError):
    """Cancellation retains validated artifacts, but never publishes a partial MP4."""


def _check_cancel(cancel_event):
    if cancel_event.is_set():
        raise MediaCancelled("Đã hủy; các tệp đã hoàn thành được giữ lại.")


def _is_cancelled_error(error, cancel_event):
    if isinstance(error, MediaCancelled):
        return True
    from media.youtube import UploadCancelled
    from media.youtube_auth import YouTubeAuthError
    if isinstance(error, UploadCancelled) or (isinstance(error, YouTubeAuthError) and error.code == "cancelled"):
        return True
    # Older pure preparation/merge helpers expose cancellation as a descriptive
    # RuntimeError. Do not turn unrelated I/O or provider failures into cancellation.
    return cancel_event.is_set() and (
        str(error).startswith("Đã hủy chuẩn bị TTS;")
        or str(error) in {"Video preparation cancelled", "Đã hủy gộp audiobook.",
                          "Đã hủy tạo audiobook; không gộp MP3."}
    )


def _selected_groups(document, options, *, single=False):
    ids = [options.get("group_id")] if single else options.get("group_ids")
    if (not isinstance(ids, list) or not ids or
            any(not isinstance(value, str) or not value for value in ids)):
        raise PipelineStateError("Chọn ít nhất một nhóm chương hợp lệ.")
    if len(set(ids)) != len(ids):
        raise PipelineStateError("Danh sách nhóm chương không được trùng lặp.")
    # Validate membership up front, not every artifact: a broken first group's
    # files must not prevent later selected groups from being processed.
    document.require_chapter_groups(validate_files=False)
    groups = {group.group_id: group for group in document.chapter_groups}
    if any(value not in groups for value in ids):
        raise PipelineStateError("Nhóm chương đã chọn không tồn tại trong phiên này.")
    return [groups[value] for value in ids]


def _processor(document, group, settings, cancel_event, progress):
    from media.groups import prepare_tts
    from media.tts import TtsProcessor

    plan, chunks = prepare_tts(document, group.group_id, settings, cancel_event=cancel_event)
    processor = TtsProcessor(
        chunks, Path(group.output_dir) / "audio_chunks", voice=settings.tts_voice,
        max_concurrency=settings.tts_max_concurrency,
        timeout_seconds=settings.tts_timeout_seconds,
        retry_count=settings.tts_retry_count,
        fallback_retry_count=settings.tts_fallback_retry_count,
        cancel_event=cancel_event, progress=progress,
    )
    processor.preparation_plan = plan
    return processor


def _merge(processor, result, group, settings, cancel_event, *, partial=False):
    from media.channel_intro import prepare_job_intro

    _check_cancel(cancel_event)
    # The existing intro cache/staging helper owns all fingerprints. Wrap only
    # its network save so cancellation also stops a custom intro generation.
    factory = processor.client_factory

    class CancellableClient:
        def __init__(self, text, voice):
            self.client = factory(text, voice)

        async def save(self, path):
            task = asyncio.create_task(self.client.save(path))
            try:
                while not task.done():
                    if cancel_event.is_set():
                        raise MediaCancelled("Đã hủy tạo intro kênh.")
                    await asyncio.wait({task}, timeout=0.1)
                return await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                if cancel_event.is_set():
                    Path(path).unlink(missing_ok=True)

    staged = prepare_job_intro(processor.audio_dir, settings, client_factory=CancellableClient)
    _check_cancel(cancel_event)
    processor.merge(
        result, Path(group.output_dir) / "audiobook.mp3", skip_failed=partial,
        intro_path=Path(staged["path"]) if staged else None,
        intro_text=staged["text"] if staged else "",
        intro_voice=staged["voice"] if staged else "",
    )


def _tts(document, group, settings, cancel_event, progress, *, partial=False):
    from media.artifacts import atomic_write_json
    from media.groups import record_media, record_tts_provenance, save_job_state
    from media.tts import TtsFailure, TtsResult

    if not partial:
        group.state.update(tts_status="Generating", failures=[])
        group.state.pop("last_error", None)
        # Withdraw old output authority without deleting recoverable files.
        group.state.pop("audiobook", None)
        group.state.pop("video", None)
        save_job_state(group)
    processor = _processor(document, group, settings, cancel_event, progress)
    plan = processor.preparation_plan
    group.state["tts_plan_id"] = plan["plan_id"]
    for warning in plan.get("warnings", []):
        progress(0, len(processor.chunks), str(warning))
    if partial:
        processor.validate_dependencies()
        processor._load_manifest()
        successful = [chunk.order for chunk in processor.chunks if processor._is_resumable(chunk)]
        missing = [chunk.order for chunk in processor.chunks if chunk.order not in successful]
        if not successful or not missing:
            raise PipelineStateError("Partial merge requires both valid audio chunks and missing chunks.")
        result = TtsResult(str(processor.audio_dir), str(processor.manifest_path), skipped=successful,
                           failures=[TtsFailure(order, "", "", "Missing", "Explicitly excluded", 0) for order in missing])
        group.state.update(tts_status="Generating", successful_orders=successful)
        group.state.pop("last_error", None)
        group.state.pop("audiobook", None)
        group.state.pop("video", None)
        save_job_state(group)
        _merge(processor, result, group, settings, cancel_event, partial=True)
        manifest = json.loads(processor.manifest_path.read_text(encoding="utf-8"))
        manifest.update(partial_audiobook=True, excluded_chunks=missing, audiobook_path=result.audiobook_path)
        atomic_write_json(processor.manifest_path, manifest)
        group.state.update(tts_status="Partial", excluded_chunks=missing)
    else:
        result = processor.run()
        # Publish chunk outcomes before merging; intro/disk failures must still
        # leave failed-chunk details and resume progress visible to the caller.
        group.state.update(failures=[asdict(item) for item in result.failures],
                           successful_orders=result.successful_orders,
                           tts_status="Cancelled" if result.cancelled else "TTS Incomplete")
        save_job_state(group)
        if not result.failures and not result.cancelled:
            _merge(processor, result, group, settings, cancel_event)
            group.state["tts_status"] = "Completed"
            group.state.pop("excluded_chunks", None)
        if result.cancelled:
            save_job_state(group)
            raise MediaCancelled("Đã hủy TTS; các đoạn MP3 đã hoàn thành được giữ lại.")
    group.state.update(failures=[asdict(item) for item in result.failures], successful_orders=result.successful_orders)
    if result.audiobook_path:
        record_tts_provenance(group, processor)
        record_media(group, "audiobook", result.audiobook_path)
    save_job_state(group)
    row = {"path": result.audiobook_path, "tts_status": group.state["tts_status"],
           "successful_orders": result.successful_orders, "failures": group.state["failures"]}
    if result.failures and not partial:
        row.update(status="failed", error=f"{len(result.failures)} đoạn TTS lỗi; hãy sửa hoặc tiếp tục TTS.")
    return row


def _run_ffmpeg(command, duration, cancel_event, progress):
    """Drain both pipes concurrently with fixed memory and a bounded progress queue."""
    from media.video import parse_progress_line

    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, bufsize=0)
    chunks = queue.Queue(maxsize=64)
    errors = deque(maxlen=8)  # At most 32 KiB of stderr diagnostics.
    stopped = threading.Event()

    def read_stdout():
        try:
            while not stopped.is_set():
                data = process.stdout.read(4096)
                if not data:
                    break
                while not stopped.is_set():
                    try:
                        chunks.put(data, timeout=0.1)
                        break
                    except queue.Full:
                        pass
        finally:
            process.stdout.close()

    def read_stderr():
        try:
            while True:
                data = process.stderr.read(4096)
                if not data:
                    break
                errors.append(data)
        finally:
            process.stderr.close()

    readers = [threading.Thread(target=read_stdout), threading.Thread(target=read_stderr)]
    for reader in readers:
        reader.start()
    buffer = b""
    state = {}
    last = {"elapsed": 0.0, "percentage": 0.0, "speed": 0.0, "eta": 0.0}
    termination_deadline = None
    try:
        while process.poll() is None or readers[0].is_alive() or not chunks.empty():
            if cancel_event.is_set() and process.poll() is None:
                if termination_deadline is None:
                    process.terminate()
                    termination_deadline = time.monotonic() + 3
                elif time.monotonic() >= termination_deadline:
                    process.kill()
            try:
                data = chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            buffer += data
            lines = buffer.split(b"\n")
            buffer = lines.pop()[-8192:]
            for line in lines:
                # Only FFmpeg's known progress keys can grow parser state.
                if line.split(b"=", 1)[0] not in {
                    b"out_time", b"out_time_us", b"out_time_ms", b"speed", b"progress",
                }:
                    continue
                update = parse_progress_line(state, line[:8192].decode("utf-8", "replace"), duration)
                if update is not None:
                    last = update
                    progress(round(update["percentage"] * 10), 1000,
                             f"Video: {update['elapsed']:.1f}s / {duration:.1f}s · "
                             f"{update['speed']:.1f}x · còn {update['eta']:.1f}s")
        code = process.wait()
        readers[1].join()
        _check_cancel(cancel_event)
        return code, b"".join(errors).decode("utf-8", "replace").strip(), last
    finally:
        stopped.set()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for reader in readers:
            reader.join()


def render_video(capabilities, media, timeline, *, audio_copy, cancel_event, progress):
    """Verified encoder fallback, guarded temporary output, and real result validation."""
    from media.video import build_video_command, validate_rendered_video, VideoRenderResult
    from media.video_pages import require_unchanged, source_fingerprint, validate_timeline_timestamps

    candidates = list(capabilities.verified_candidates)
    if not candidates:
        raise PipelineStateError("No verified H.264 encoder is available.")
    target = Path(media.video_path)
    partial = target.with_name(f".{target.stem}.part.mp4")
    target.parent.mkdir(parents=True, exist_ok=True)
    source = timeline.source or source_fingerprint(media)
    attempts = []
    try:
        for candidate in candidates:
            _check_cancel(cancel_event)
            require_unchanged(timeline.source_files)
            if source_fingerprint(media) != source:
                raise PipelineStateError("Video inputs changed; regenerate Step 4.")
            partial.unlink(missing_ok=True)
            progress(0, 1000, f"Rendering with {candidate.name}…")
            try:
                command = build_video_command(capabilities.ffmpeg_path, candidate, Path(timeline.concat_path),
                                              Path(media.audiobook_path), partial, audio_copy=audio_copy)
                code, diagnostics, last = _run_ffmpeg(command, timeline.audiobook_duration, cancel_event, progress)
                if code:
                    raise RuntimeError(diagnostics or f"FFmpeg exited with status {code}.")
                duration = validate_rendered_video(partial, timeline.audiobook_duration, capabilities.ffprobe_path)
                validate_timeline_timestamps(partial, timeline, capabilities.ffprobe_path)
                _check_cancel(cancel_event)
                require_unchanged(timeline.source_files)
                if source_fingerprint(media) != source:
                    raise PipelineStateError("Video inputs changed during rendering; regenerate Step 4.")
                os.replace(partial, target)
                return VideoRenderResult(str(target), duration, target.stat().st_size, candidate.name,
                                         candidate.backend, float(last["speed"] or 0),
                                         "copy" if audio_copy else "aac-192k", attempts, dict(source))
            except MediaCancelled:
                raise
            except (OSError, ValueError, RuntimeError) as error:
                message = str(error)
                attempts.append(f"{candidate.name} failed: {message}")
                partial.unlink(missing_ok=True)
                if any(marker in message.lower() for marker in _FATAL_VIDEO_ERRORS):
                    raise RuntimeError(attempts[-1]) from error
        raise RuntimeError("\n\n".join(attempts))
    finally:
        partial.unlink(missing_ok=True)


def _video(document, group, options, capabilities, cancel_event, progress):
    from media.groups import record_job_visuals, record_video
    from media.video import mp3_copy_is_safe, probe_audio, validate_rendered_video
    from media.video_pages import prepare_video_timeline

    if group.state.get("tts_status") != "Completed":
        raise PipelineStateError("Complete every TTS chunk before Step 4; partial audiobooks cannot be rendered.")
    record_job_visuals(group, options.get("cover_image", ""), options.get("qr_image", ""))
    media = document.require_step4_outputs(group.group_id)
    audio = probe_audio(Path(media.audiobook_path), capabilities.ffprobe_path)
    _check_cancel(cancel_event)
    try:
        existing = document.require_step5_outputs(group.group_id)
        validate_rendered_video(Path(existing.video_path), audio.duration, capabilities.ffprobe_path)
        return {"status": "skipped", "path": existing.video_path}
    except (PipelineStateError, ValueError, OSError, RuntimeError):
        pass
    timeline = prepare_video_timeline(media, capabilities.ffprobe_path, cancel_event=cancel_event, progress=progress)
    _check_cancel(cancel_event)
    copy = mp3_copy_is_safe(Path(media.audiobook_path), capabilities.ffmpeg_path,
                            capabilities.ffprobe_path, temp_dir=Path(group.output_dir))
    _check_cancel(cancel_event)
    result = render_video(capabilities, media, timeline, audio_copy=copy,
                          cancel_event=cancel_event, progress=progress)
    record_video(document, group.group_id, result)
    return {"path": result.output_path, "video": result.to_dict()}


def _preview(document, group, options, cancel_event, progress):
    from media.video_pages import file_states, load_narration, page_chapter_label, render_page, require_unchanged

    media = document.require_step4_outputs(group.group_id)
    cover, qr = options.get("cover_image", ""), options.get("qr_image", "")
    if not all(isinstance(value, str) and value and Path(value).is_file() for value in (cover, qr)):
        raise PipelineStateError("Add both page images (1:1 left + QR right) before previewing.")
    _check_cancel(cancel_event)
    # Read the actual full-chunk narration, including saved failed-chunk edits,
    # without rewriting its plan with newly changed settings.
    records = load_narration(media)
    inputs = file_states([media.thumbnail_path, media.audiobook_path, media.tts_manifest_path,
                          cover, qr, *(record["mp3_path"] for record in records)])
    target = Path(group.output_dir) / "page_preview.png"
    partial = target.with_name(".page_preview.part.png")
    chunk = records[0]
    try:
        render_page(media.thumbnail_path, partial, title=media.title,
                    chapter=page_chapter_label(chunk["chapter"], group.label), text=chunk["text"],
                    left_image=cover, right_image=qr)
        _check_cancel(cancel_event)
        require_unchanged(inputs)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    progress(1, 1, "Đã render preview đầy đủ 1920×1080.")
    return {"path": str(target.resolve()), "group_id": group.group_id}


def _safe_youtube_error(error):
    from media.youtube import YouTubeUploadError
    from media.youtube_auth import YouTubeAuthError

    return (str(error) if isinstance(error, (YouTubeUploadError, YouTubeAuthError)) else
            "YouTube operation failed. Check the connection and local job access, then retry.")


def _upload_metadata(group, settings, options):
    from media.youtube import load_upload_state, UploadMetadata

    state = load_upload_state(group.output_dir)
    duplicate = options.get("allow_duplicate", False)
    if not isinstance(duplicate, bool):
        raise ValueError("allow_duplicate phải là boolean.")
    if state and state.get("status") != "rejected" and not duplicate:
        row = dict(state.get("metadata") or {})
        row.setdefault("contains_synthetic_media", False)
    else:
        shared = options.get("metadata", {})
        per_group = options.get("group_metadata", {})
        titles = options.get("titles", {})
        if not all(isinstance(value, dict) for value in (shared, per_group, titles)):
            raise ValueError("metadata, group_metadata và titles phải là object.")
        override = per_group.get(group.group_id, {})
        if not isinstance(override, dict):
            raise ValueError("Metadata của từng nhóm phải là object.")
        row = dict(shared, **override)
        row.setdefault("title", titles.get(group.group_id, f"{group.title} | {group.label}"))
        if group.group_id in titles and "title" not in override:
            row["title"] = titles[group.group_id]
        if "tags" not in row:
            row["tags"] = settings.tags_for_uploaded_title(group.title) or []
    metadata = UploadMetadata(**row)
    metadata.validate(require_future=not (state and state.get("status") != "rejected" and not duplicate))
    return metadata


def _youtube_group(action, document, group, options, metadata, auth, settings, cancel_event, progress):
    from media.groups import save_job_state
    from media.youtube import load_upload_state, UploadMetadata, YouTubeUploader, YouTubeUploadError
    from media.youtube_auth import YouTubeAuthError

    channel = auth.account["channel_id"]
    uploader = YouTubeUploader(auth.session(), auth.secret_store, cancel_event=cancel_event,
                              progress=lambda update: progress(int(update.get("bytes_sent", 0)),
                                  max(1, int(update.get("total_bytes", 1))), "Đang upload YouTube…"),
                              # Only fixed local messages go to logs, not remote exception data.
                              log=lambda message: progress(0, 1, message))
    state = load_upload_state(group.output_dir)
    if state and state.get("channel_id") != channel and not options.get("allow_duplicate", False):
        raise YouTubeAuthError("Reconnect the channel used for this job before retrying.", "reconnect")
    if action == "youtube_metadata":
        try:
            value = UploadMetadata(**options.get("metadata", {}))
            value.validate()
        except ValueError as error:
            raise YouTubeUploadError(str(error)) from None
        except TypeError:
            raise YouTubeUploadError("Metadata chứa trường không hỗ trợ hoặc sai kiểu dữ liệu.") from None
        state = uploader.update_video_metadata(group.output_dir, channel, value)
    elif action == "youtube_retry_playlist":
        playlist = options.get("playlist_id")
        if playlist is not None and playlist != state.get("playlist_id"):
            raise YouTubeUploadError("Retry Playlist phải dùng playlist đã lưu của video này.")
        state = uploader.retry_playlist(group.output_dir, channel)
    elif action == "youtube_retry_thumbnail":
        media = document.require_step5_outputs(group.group_id)
        state = uploader.retry_thumbnail(media.output_dir, media.thumbnail_path, channel)
    elif state.get("status") == "completed" and state.get("video_id") and not options.get("allow_duplicate", False):
        return {"status": "skipped", "youtube": state}
    else:
        media = document.require_step5_outputs(group.group_id)
        if state.get("video_id") and not options.get("allow_duplicate", False):
            if not state.get("thumbnail_uploaded"):
                state = uploader.retry_thumbnail(media.output_dir, media.thumbnail_path, channel)
            if state.get("playlist_id") and not state.get("playlist_added"):
                state = uploader.retry_playlist(media.output_dir, channel)
        else:
            state = uploader.upload(media.video_path, media.thumbnail_path, media.output_dir, metadata,
                                    channel, allow_duplicate=options.get("allow_duplicate", False))
    group.state["youtube"] = state
    save_job_state(group)
    if state.get("video_id"):
        used = state.get("updated_metadata") or state.get("metadata") or {}
        try:
            settings.remember_uploaded_title_tags(group.title, used.get("tags", []))
        except OSError:
            progress(0, 1, "Video đã upload, nhưng chưa lưu được bộ tag vào Settings.")
    if auth.account is None:
        raise YouTubeAuthError("Authentication failed; reconnect before resuming the batch.", "reconnect")
    row = {"youtube": state}
    if state.get("status") != "completed":
        row.update(status="failed", error=state.get("error") or state.get("thumbnail_error") or
                   state.get("playlist_error") or "Upload chưa hoàn thành; tiếp tục các bước còn thiếu.")
    return row


def execute_media(action, document, settings, options, *, cancel_event, progress):
    """Execute one existing media operation; caller serializes document mutation."""
    from media.groups import edit_failed_chunk, prepare_tts, record_media, save_job_state

    if action not in MEDIA_ACTIONS:
        raise ValueError(f"Unknown media action: {action}")
    if not isinstance(options, dict):
        raise ValueError("Media options must be an object.")
    options = json.loads(json.dumps(options))  # Freeze mutable publishing drafts.
    frozen = settings.clone()
    youtube = action in _YOUTUBE_ACTIONS
    auth = None
    try:
        _check_cancel(cancel_event)
        if action in {"youtube_connect", "youtube_disconnect"}:
            from media.youtube_auth import YouTubeAuth
            auth = YouTubeAuth(frozen.youtube_client_secrets_path)
            _check_cancel(cancel_event)
            if action == "youtube_disconnect":
                auth.disconnect()
                return {"account": None, "cancelled": False}
            return {"account": auth.connect(cancel_event=cancel_event), "cancelled": False}
        groups = _selected_groups(document, options, single=action not in _BATCH_ACTIONS)
        if action == "merge_partial" and options.get("allow_partial") is not True:
            raise PipelineStateError("Xác nhận allow_partial=true để gộp bỏ qua các đoạn thiếu.")
        if action == "preview":
            return _preview(document, groups[0], options, cancel_event, progress)
        if action == "edit_chunk":
            _check_cancel(cancel_event)
            order, text = options.get("order"), options.get("text")
            if type(order) is not int or not isinstance(text, str):
                raise ValueError("order phải là số nguyên và text phải là chuỗi.")
            edit_failed_chunk(document, groups[0].group_id, frozen, order, text)
            # The desktop operation saves the override and immediately retries.
            action = "tts"
        metadata = {}
        if youtube:
            from media.youtube_auth import YouTubeAuth, YouTubeAuthError
            from media.youtube import YouTubeUploadError
            auth = YouTubeAuth(frozen.youtube_client_secrets_path)
            _check_cancel(cancel_event)
            if not auth.restore():
                raise YouTubeAuthError("Chưa kết nối YouTube. Hãy kết nối tài khoản Google.", "reconnect")
            if action == "upload":
                # Invalid metadata belongs to its own row, not the entire batch.
                for group in groups:
                    try:
                        metadata[group.group_id] = _upload_metadata(group, frozen, options)
                    except ValueError as error:
                        metadata[group.group_id] = YouTubeUploadError(str(error))
                    except TypeError:
                        metadata[group.group_id] = YouTubeUploadError("Metadata chứa trường không hỗ trợ hoặc sai kiểu dữ liệu.")
                    except Exception as error:
                        metadata[group.group_id] = error
        capabilities = None
        results = []
        for index, selected in enumerate(groups):
            if cancel_event.is_set():
                break
            group = selected

            def report(done, total, message, index=index, label=group.label):
                fraction = min(1.0, max(0.0, done / max(1, total)))
                progress(round((index + fraction) * 1000), len(groups) * 1000, f"{label}: {message}")

            try:
                group = document.require_group_artifacts(group.group_id)
                if action == "prepare":
                    plan, chunks = prepare_tts(document, group.group_id, frozen, cancel_event=cancel_event)
                    save_job_state(group)
                    row = {"plan": plan, "chunk_count": len(chunks)}
                elif action == "thumbnail":
                    from media.thumbnail import generate_thumbnail
                    path = options.get("image_path", "")
                    if not isinstance(path, str) or not path.strip():
                        raise ValueError("Chọn ảnh thumbnail.")
                    result = generate_thumbnail(Path(path).expanduser(), Path(group.output_dir), title=group.title,
                                                chapter=group.label, quality=frozen.thumbnail_jpeg_quality)
                    target = Path(group.output_dir) / "thumbnail.jpg"
                    Path(result).replace(target)
                    group.state["thumbnail_source"] = str(Path(path).expanduser().resolve())
                    record_media(group, "thumbnail", target)
                    row = {"path": str(target.resolve())}
                elif action in {"tts", "merge_partial"}:
                    row = _tts(document, group, frozen, cancel_event, report, partial=action == "merge_partial")
                elif action == "video":
                    if capabilities is None:
                        from media.video import detect_video_capabilities
                        report(0, 1, "Đang kiểm tra encoder FFmpeg thực tế…")
                        capabilities = detect_video_capabilities()
                    _check_cancel(cancel_event)
                    row = _video(document, group, options, capabilities, cancel_event, report)
                else:
                    value = metadata.get(group.group_id)
                    if isinstance(value, Exception):
                        raise value
                    row = _youtube_group(action, document, group, options, value, auth,
                                         settings, cancel_event, report)
                results.append(dict(row, group_id=group.group_id, status=row.get("status", "completed")))
                report(1, 1, row.get("error", "Hoàn thành."))
            except Exception as error:
                cancelled = _is_cancelled_error(error, cancel_event)
                message = _safe_youtube_error(error) if youtube else str(error)
                if action in {"tts", "merge_partial"}:
                    group.state["tts_status"] = "Cancelled" if cancelled else "TTS Incomplete"
                # Synchronize durable upload progress, even after cancellation or
                # a remote failure; never put credential material in job_state.
                if youtube:
                    from media.youtube import load_upload_state
                    try:
                        group.state["youtube"] = load_upload_state(group.output_dir)
                    except Exception:
                        pass
                group.state["last_error"] = message
                try:
                    save_job_state(group)
                except OSError:
                    message += " (Cannot save job state; check disk space/permissions.)"
                results.append({"group_id": group.group_id, "status": "cancelled" if cancelled else "failed", "error": message})
                if cancelled:
                    break
                if youtube and (isinstance(error, YouTubeAuthError) or auth.account is None or "authentication" in message.lower()):
                    break
        failed = any(row["status"] == "failed" for row in results)
        cancelled = cancel_event.is_set() or any(row["status"] == "cancelled" for row in results)
        return {"groups": results, "cancelled": cancelled,
                "status": "partial" if failed else "cancelled" if cancelled else "completed"}
    except Exception as error:
        if youtube:
            from media.youtube import YouTubeUploadError
            from media.youtube_auth import YouTubeAuthError
            if _is_cancelled_error(error, cancel_event):
                return {"groups": [], "cancelled": True}
            raise YouTubeUploadError(_safe_youtube_error(error)) from None
        if _is_cancelled_error(error, cancel_event):
            return {"groups": [], "cancelled": True}
        raise
    finally:
        if auth is not None and auth.account is not None:
            try:
                auth.session().close()
            except Exception:
                # A close failure must never expose HTTP session internals.
                progress(0, 1, "Không thể đóng phiên YouTube sạch; hãy kết nối lại trước tác vụ tiếp theo.")
