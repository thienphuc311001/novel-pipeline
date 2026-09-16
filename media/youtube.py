"""YouTube resumable uploads with durable job state and separate follow-up stages.

No Qt or OAuth implementation lives here. A requests-compatible authenticated
session and OS-backed secret store are injected by the desktop worker. Resumable
URLs are bearer-like secrets and deliberately never enter the job JSON or logs.
"""

from __future__ import annotations

import json
import os
import random
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Any, Callable
from urllib.parse import urlparse


API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"
STATE_NAME = "youtube_upload.json"
TRANSIENT = {408, 429, 500, 502, 503, 504}


class YouTubeUploadError(RuntimeError):
    """Safe to display; never contains response bodies, request URLs or tokens."""


class UploadCancelled(YouTubeUploadError):
    pass


class DuplicateUploadError(YouTubeUploadError):
    pass


class ResumeUncertainError(YouTubeUploadError):
    pass


class _NetworkError(YouTubeUploadError):
    pass


@dataclass
class UploadMetadata:
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    category_id: str = "22"
    privacy: str = "private"
    made_for_kids: bool = False
    playlist_id: str | None = None
    publish_at: str | None = None

    def validate(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 100:
            raise ValueError("Title is required and must contain at most 100 characters.")
        if not isinstance(self.description, str) or len(self.description.encode("utf-8")) > 5000:
            raise ValueError("Description must contain at most 5,000 UTF-8 bytes.")
        if any(char in self.title + self.description for char in "<>"):
            raise ValueError("Title and description cannot contain < or >.")
        if not isinstance(self.tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise ValueError("Tags must be a list of non-empty text values.")
        tag_length = sum(len(tag) + (2 if " " in tag else 0) for tag in self.tags) + max(0, len(self.tags) - 1)
        if tag_length > 500 or any("<" in tag or ">" in tag for tag in self.tags):
            raise ValueError("Tags exceed YouTube's 500-character limit or contain invalid characters.")
        if not isinstance(self.category_id, str) or not self.category_id.isascii() or not self.category_id.isdigit():
            raise ValueError("Select a valid YouTube category.")
        if self.privacy not in {"private", "unlisted", "public"}:
            raise ValueError("Visibility must be private, unlisted or public.")
        if not isinstance(self.made_for_kids, bool):
            raise ValueError("Made for kids must be explicitly true or false.")
        if self.playlist_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]+", self.playlist_id):
            raise ValueError("Select a valid playlist.")
        if self.publish_at:
            if self.privacy != "private":
                raise ValueError("Scheduled publication requires Private visibility.")
            try:
                when = datetime.fromisoformat(self.publish_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                raise ValueError("The publishing schedule must be an ISO date with a time zone.") from None
            if when.tzinfo is None or when <= datetime.now(timezone.utc):
                raise ValueError("Choose a future publishing time with a time zone.")

    def payload(self) -> dict:
        self.validate()
        status = {"privacyStatus": self.privacy, "selfDeclaredMadeForKids": self.made_for_kids}
        if self.publish_at:
            status["publishAt"] = datetime.fromisoformat(self.publish_at.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return {"snippet": {"title": self.title, "description": self.description,
                            "tags": self.tags, "categoryId": self.category_id}, "status": status}


def load_upload_state(job_dir: str | Path) -> dict:
    path = Path(job_dir) / STATE_NAME
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError
        if value.get("video_id") and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(value["video_id"])):
            raise ValueError
        return value
    except (OSError, ValueError):
        raise YouTubeUploadError("Cannot read youtube_upload.json. Recover the job state before uploading to avoid duplicates.") from None


def _save_state(job_dir: Path, state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    descriptor, temporary = tempfile.mkstemp(prefix=".youtube-upload-", suffix=".tmp", dir=job_dir)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, job_dir / STATE_NAME)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _job_lock(job_dir: Path):
    """OS locks release on process exit; a crash never leaves a stale lock."""
    job_dir.mkdir(parents=True, exist_ok=True)
    with (job_dir / ".youtube_upload.lock").open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt
                handle.write(b"\0")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise YouTubeUploadError("Another upload operation is already running for this job.") from None
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _safe_api_error(response) -> YouTubeUploadError:
    code = int(response.status_code)
    reasons = set()
    try:
        reasons = {entry.get("reason") for entry in response.json().get("error", {}).get("errors", [])}
    except (ValueError, AttributeError, TypeError):
        pass
    if code == 401 or reasons & {"authError", "invalidCredentials", "youtubeSignupRequired"}:
        return YouTubeUploadError("YouTube authentication expired or the channel is unavailable. Reconnect your YouTube account.")
    if reasons & {"quotaExceeded", "dailyLimitExceeded", "uploadLimitExceeded"}:
        return YouTubeUploadError("YouTube quota or upload limit reached. Try again after the limit resets.")
    if code == 403:
        return YouTubeUploadError("YouTube denied permission. Check the connected channel, API permissions and channel verification.")
    if code in TRANSIENT:
        return YouTubeUploadError(f"Temporary YouTube service/network error (HTTP {code}); the upload can be resumed.")
    return YouTubeUploadError(f"YouTube rejected the operation (HTTP {code}). Check upload metadata and account permissions.")


def _session_url(value: str) -> str:
    parsed = urlparse(value)
    if (parsed.scheme != "https" or parsed.hostname not in {"www.googleapis.com", "youtube.googleapis.com"}
            or parsed.username or parsed.password or parsed.port not in {None, 443}
            or parsed.path != "/upload/youtube/v3/videos" or parsed.fragment):
        raise ResumeUncertainError("YouTube returned an invalid resumable session address; upload stopped safely.")
    return value


class YouTubeUploader:
    def __init__(self, session, secret_store, cancel_event: Event | None = None,
                 progress: Callable[[dict], None] | None = None,
                 log: Callable[[str], None] | None = None, chunk_size: int = 8 * 1024 * 1024,
                 *, retry_count: int = 5, retry_delay: float = 1.0):
        if chunk_size <= 0 or chunk_size % (256 * 1024):
            raise ValueError("YouTube chunk size must be a positive multiple of 256 KiB.")
        self.session = session
        self.secret_store = secret_store
        self.cancel_event = cancel_event or Event()
        self.progress = progress or (lambda _value: None)
        self.log = log or (lambda _message: None)
        self.chunk_size = chunk_size
        self.retry_count = max(0, min(int(retry_count), 10))
        self.retry_delay = max(0.0, float(retry_delay))
        self._started = 0.0
        self._initial_bytes = 0

    def _cancel(self):
        if self.cancel_event.is_set():
            raise UploadCancelled("Upload cancelled. Saved progress can be resumed.")

    def _request(self, method: str, url: str, **kwargs):
        self._cancel()
        try:
            return self.session.request(method, url, timeout=(15, 120), allow_redirects=False, **kwargs)
        except Exception as error:
            # AuthorizedSession refresh exceptions are also sanitized: never
            # render a requests exception, which can contain the secret URL.
            if getattr(error, "code", "") == "network":
                raise _NetworkError("Network request interrupted. Saved upload progress is retained.") from None
            if "Refresh" in type(error).__name__ or "Auth" in type(error).__name__:
                raise YouTubeUploadError("YouTube authentication failed. Reconnect your YouTube account.") from None
            raise _NetworkError("Network request interrupted. Saved upload progress is retained.") from None

    def _backoff(self, attempt: int):
        delay = min(30.0, self.retry_delay * 2 ** attempt)
        if delay:
            delay += random.uniform(0.0, min(1.0, delay / 4))
        if self.cancel_event.wait(delay):
            self._cancel()

    def _request_retry(self, method: str, url: str, **kwargs):
        """Only used for read/status or idempotent thumbnail operations."""
        for attempt in range(self.retry_count + 1):
            try:
                response = self._request(method, url, **kwargs)
                if int(response.status_code) not in TRANSIENT or attempt == self.retry_count:
                    return response
            except _NetworkError:
                if attempt == self.retry_count:
                    raise
            self._backoff(attempt)
        raise AssertionError("unreachable")

    def _fingerprint(self, video: Path) -> dict:
        stat = video.stat()
        if not video.is_file() or stat.st_size <= 0:
            raise YouTubeUploadError("The Step 5 MP4 is missing or empty.")
        digest = sha256()
        with video.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                self._cancel()
                digest.update(block)
        if video.stat().st_mtime_ns != stat.st_mtime_ns or video.stat().st_size != stat.st_size:
            raise YouTubeUploadError("The video changed while preparing the upload.")
        return {"path": str(video.resolve()), "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns, "sha256": digest.hexdigest()}

    def _emit_progress(self, state: dict):
        done, total = state.get("bytes_sent", 0), state["total_bytes"]
        elapsed = max(0.001, time.monotonic() - self._started)
        self.progress({"bytes_sent": done, "total_bytes": total,
                       "percent": 100.0 * done / total,
                       "speed_bps": max(0, done - self._initial_bytes) / elapsed})

    def _finish_response(self, response, state: dict, job: Path) -> bool:
        code = int(response.status_code)
        if code in {200, 201}:
            try:
                resource = response.json()
                video_id = resource.get("id", "")
                if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", video_id):
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                raise ResumeUncertainError("YouTube accepted the upload but returned no valid video ID. Resume to check its status; do not start another upload.") from None
            state.update(video_id=video_id, video_url=f"https://www.youtube.com/watch?v={video_id}",
                         status="partial", bytes_sent=state["total_bytes"], uploaded_at=datetime.now(timezone.utc).isoformat(), error="")
            actual_privacy = resource.get("status", {}).get("privacyStatus")
            if actual_privacy in {"private", "unlisted", "public"}:
                state["privacy"] = actual_privacy
            _save_state(job, state)  # Commit ID before any follow-up operation.
            key = state.pop("session_key", None)
            if key:
                try:
                    self.secret_store.delete(key)
                except Exception:
                    pass  # Video ID is authoritative even if keyring cleanup fails.
            _save_state(job, state)
            self._emit_progress(state)
            return True
        if code == 308:
            raw = response.headers.get("Range", "")
            match = re.fullmatch(r"(?:bytes=)?0-(\d+)", raw)
            if raw and not match:
                raise ResumeUncertainError("YouTube returned an invalid resume position. Resume the existing session later.")
            position = int(match.group(1)) + 1 if match else 0
            if position > state["total_bytes"]:
                raise ResumeUncertainError("YouTube returned an out-of-range resume position.")
            state.update(bytes_sent=position, status="uploading", error="")
            _save_state(job, state)
            self._emit_progress(state)
            return False
        if code in {404, 410}:
            raise ResumeUncertainError("The resumable session expired. Its completion cannot be confirmed. Check YouTube Studio before explicitly choosing Upload Again.")
        raise _safe_api_error(response)

    def _query_session(self, url: str, state: dict, job: Path) -> bool:
        response = self._request_retry("PUT", url, headers={"Content-Length": "0", "Content-Range": f"bytes */{state['total_bytes']}"}, data=b"")
        return self._finish_response(response, state, job)

    def _create_session(self, metadata: UploadMetadata, state: dict, job: Path) -> str:
        state["status"] = "initiating"
        _save_state(job, state)
        try:
            response = self._request("POST", f"{UPLOAD_API}/videos", params={"uploadType": "resumable", "part": "snippet,status"},
                                     headers={"X-Upload-Content-Length": str(state["total_bytes"]), "X-Upload-Content-Type": "video/mp4"}, json=metadata.payload())
        except _NetworkError:
            raise ResumeUncertainError("The upload session request was interrupted. Check YouTube Studio before explicitly choosing Upload Again.") from None
        if response.status_code not in {200, 201}:
            if response.status_code in TRANSIENT:
                raise ResumeUncertainError("YouTube did not confirm the new upload session. Check YouTube Studio before explicitly choosing Upload Again.")
            state["status"] = "rejected"
            _save_state(job, state)
            raise _safe_api_error(response)
        location = _session_url(response.headers.get("Location", ""))
        key = f"youtube-session:{uuid.uuid4().hex}"
        try:
            self.secret_store.set(key, location)
        except Exception:
            raise YouTubeUploadError("Cannot securely store the resumable session. Unlock the system credential store before retrying.") from None
        state.update(session_key=key, status="uploading")
        _save_state(job, state)
        return location

    def upload(self, video_path, thumbnail_path, job_dir, metadata: UploadMetadata,
               channel_id: str, allow_duplicate: bool = False) -> dict:
        job, video = Path(job_dir), Path(video_path)
        metadata.validate()
        if video.resolve().parent != job.resolve() or Path(thumbnail_path).resolve().parent != job.resolve():
            raise YouTubeUploadError("Upload inputs must belong to the current job folder.")
        if not channel_id:
            raise YouTubeUploadError("Connect a YouTube channel before uploading.")
        with _job_lock(job):
            old = load_upload_state(job)
            if old.get("video_id") and not allow_duplicate:
                raise DuplicateUploadError("This job has already been uploaded. Use Retry Thumbnail/Playlist or explicitly choose Upload Again.")
            if old and old.get("channel_id") != channel_id and not allow_duplicate:
                raise YouTubeUploadError("This job belongs to a different YouTube channel. Reconnect its channel to resume.")
            fingerprint = self._fingerprint(video)
            if old and not allow_duplicate and old.get("status") != "rejected":
                if old.get("video_fingerprint") != fingerprint:
                    raise ResumeUncertainError("The video differs from this job's pending upload. Recover its previous upload or explicitly choose Upload Again.")
                if old.get("metadata") != asdict(metadata):
                    raise YouTubeUploadError("A pending upload uses the saved metadata. Restore those values to resume; metadata cannot change during an upload.")
                if not old.get("session_key"):
                    raise ResumeUncertainError("The previous upload session is unavailable. Check YouTube Studio before explicitly choosing Upload Again.")
                state = old
            else:
                previous = list(old.get("prior_uploads", []))
                if old:
                    previous.append({key: value for key, value in old.items() if key not in {"prior_uploads", "session_key"}})
                state = {"schema_version": 1, "status": "ready", "channel_id": channel_id,
                         "title": metadata.title, "privacy": metadata.privacy, "playlist_id": metadata.playlist_id,
                         "metadata": asdict(metadata), "video_fingerprint": fingerprint,
                         "total_bytes": fingerprint["size"], "bytes_sent": 0, "video_id": None,
                         "video_url": "", "thumbnail_uploaded": False, "thumbnail_error": "",
                         "playlist_added": False, "playlist_error": "", "error": "", "prior_uploads": previous}
            self._started, self._initial_bytes = time.monotonic(), state.get("bytes_sent", 0)
            try:
                if state.get("session_key"):
                    try:
                        stored = self.secret_store.get(state["session_key"])
                    except Exception:
                        raise YouTubeUploadError("Cannot access the saved session. Unlock the system credential store.") from None
                    if not stored:
                        raise ResumeUncertainError("The saved resumable session is unavailable. Check YouTube Studio before choosing Upload Again.")
                    url = _session_url(stored)
                    self.log("Checking the existing YouTube upload session…")
                    self._query_session(url, state, job)
                else:
                    self.log("Starting YouTube resumable upload…")
                    url = self._create_session(metadata, state, job)
                self._emit_progress(state)
                failures = 0
                with video.open("rb") as handle:
                    while not state.get("video_id"):
                        self._cancel()
                        if video.stat().st_size != fingerprint["size"] or video.stat().st_mtime_ns != fingerprint["mtime_ns"]:
                            raise YouTubeUploadError("The MP4 changed during upload; the session was stopped.")
                        offset = state["bytes_sent"]
                        if offset >= state["total_bytes"]:
                            if failures >= self.retry_count:
                                raise ResumeUncertainError("All bytes were received but YouTube has not confirmed completion. Resume this session later.")
                            self._backoff(failures)
                            failures += 1
                            self._query_session(url, state, job)
                            continue
                        handle.seek(offset)
                        data = handle.read(self.chunk_size)
                        try:
                            response = self._request("PUT", url, headers={"Content-Type": "video/mp4", "Content-Length": str(len(data)),
                                "Content-Range": f"bytes {offset}-{offset + len(data) - 1}/{state['total_bytes']}"}, data=data)
                            if response.status_code in TRANSIENT:
                                raise _NetworkError("Temporary upload failure; checking the server's received position.")
                            self._finish_response(response, state, job)
                            if state["bytes_sent"] <= offset and not state.get("video_id"):
                                raise _NetworkError("YouTube has not advanced the upload position.")
                            failures = 0
                        except _NetworkError:
                            if failures >= self.retry_count:
                                raise YouTubeUploadError("Temporary network/server failures exhausted retries. Resume the saved upload later.") from None
                            self.log("Upload interrupted; checking received bytes before retrying…")
                            self._backoff(failures)
                            failures += 1
                            self._query_session(url, state, job)
                self._thumbnail(state, job, Path(thumbnail_path))
                self._playlist(state, job)
                self._finish_stages(state, job)
                return state
            except (YouTubeUploadError, OSError) as error:
                if isinstance(error, UploadCancelled):
                    state["status"] = "cancelled"
                elif isinstance(error, ResumeUncertainError):
                    state["status"] = "uncertain"
                elif state.get("status") != "rejected":
                    state["status"] = "partial" if state.get("video_id") else "error"
                state["error"] = str(error) if isinstance(error, YouTubeUploadError) else "Local file or upload-state write failed. Check free space and permissions."
                _save_state(job, state)
                if isinstance(error, OSError):
                    raise YouTubeUploadError(state["error"]) from None
                raise

    def _thumbnail(self, state: dict, job: Path, thumbnail: Path):
        if state.get("thumbnail_uploaded"):
            return
        self._cancel()
        try:
            if not thumbnail.is_file() or not 0 < thumbnail.stat().st_size <= 2 * 1024 * 1024:
                raise YouTubeUploadError("Thumbnail must be a non-empty JPEG/PNG of at most 2 MB.")
            mime = "image/png" if thumbnail.suffix.lower() == ".png" else "image/jpeg"
            self.log("Uploading the Step 4 thumbnail…")
            response = self._request_retry("POST", f"{UPLOAD_API}/thumbnails/set", params={"videoId": state["video_id"], "uploadType": "media"},
                                           headers={"Content-Type": mime}, data=thumbnail.read_bytes())
            if response.status_code not in {200, 201}:
                raise _safe_api_error(response)
            state.update(thumbnail_uploaded=True, thumbnail_error="")
        except UploadCancelled:
            raise
        except (YouTubeUploadError, OSError) as error:
            state["thumbnail_error"] = str(error) if isinstance(error, YouTubeUploadError) else "The thumbnail cannot be read."
            self.log("Video uploaded; thumbnail failed. Retry Thumbnail preserves the existing video.")
        _save_state(job, state)

    def _membership(self, state: dict) -> bool:
        response = self._request_retry("GET", f"{API}/playlistItems", params={"part": "id", "playlistId": state["playlist_id"], "videoId": state["video_id"], "maxResults": 50})
        if response.status_code != 200:
            raise _safe_api_error(response)
        try:
            payload = response.json()
            if not isinstance(payload.get("items"), list):
                raise ValueError
            return bool(payload["items"])
        except (ValueError, TypeError, AttributeError):
            raise YouTubeUploadError("YouTube could not confirm playlist membership. Retry Playlist later.") from None

    def _playlist(self, state: dict, job: Path, *, explicit_retry: bool = False):
        if not state.get("playlist_id") or state.get("playlist_added"):
            return
        self._cancel()
        try:
            if self._membership(state):
                state.update(playlist_added=True, playlist_error="", playlist_uncertain=False)
            elif state.get("playlist_uncertain") and not explicit_retry:
                # A just-completed insert may not yet be visible in a list.
                # Retrying an uncertain write could insert the same video twice.
                raise YouTubeUploadError("Playlist insertion is still unconfirmed. Check the playlist in YouTube; Retry Playlist rechecks membership without adding a duplicate.")
            else:
                if state.get("playlist_uncertain"):
                    # Only a separate user retry can repeat an uncertain
                    # insertion. Recheck after bounded delays for propagation;
                    # if found, finish without another write.
                    for attempt in range(2):
                        self._backoff(attempt)
                        if self._membership(state):
                            state.update(playlist_added=True, playlist_error="", playlist_uncertain=False)
                            _save_state(job, state)
                            return
                    self.log("Playlist membership is absent after rechecks; retrying only the requested playlist insertion.")
                state["playlist_uncertain"] = True
                _save_state(job, state)
                response = self._request("POST", f"{API}/playlistItems", params={"part": "snippet"}, json={"snippet": {
                    "playlistId": state["playlist_id"], "resourceId": {"kind": "youtube#video", "videoId": state["video_id"]}}})
                if response.status_code not in {200, 201}:
                    if response.status_code not in TRANSIENT:
                        state["playlist_uncertain"] = False
                    raise _safe_api_error(response)
                state.update(playlist_added=True, playlist_error="", playlist_uncertain=False)
        except UploadCancelled:
            raise
        except YouTubeUploadError as error:
            state["playlist_error"] = str(error)
            self.log("Video uploaded; playlist insertion needs attention. Retry Playlist preserves the existing video.")
        _save_state(job, state)

    @staticmethod
    def _finish_stages(state: dict, job: Path):
        complete = state.get("thumbnail_uploaded") and (not state.get("playlist_id") or state.get("playlist_added"))
        state.update(status="completed" if complete else "partial", error="")
        _save_state(job, state)

    def _retry(self, job_dir, channel_id, thumbnail_path=None) -> dict:
        job = Path(job_dir)
        with _job_lock(job):
            state = load_upload_state(job)
            if not state.get("video_id"):
                raise YouTubeUploadError("No completed video upload exists for this job.")
            if state.get("channel_id") != channel_id:
                raise YouTubeUploadError("Reconnect the channel used for this job before retrying.")
            if thumbnail_path is not None and Path(thumbnail_path).resolve().parent != job.resolve():
                raise YouTubeUploadError("Thumbnail must belong to the current job folder.")
            try:
                if thumbnail_path is not None:
                    self._thumbnail(state, job, Path(thumbnail_path))
                else:
                    self._playlist(state, job, explicit_retry=True)
                self._finish_stages(state, job)
            except UploadCancelled as error:
                state.update(status="cancelled", error=str(error))
                _save_state(job, state)
                raise
            return state

    def retry_thumbnail(self, job_dir, thumbnail_path, channel_id) -> dict:
        return self._retry(job_dir, channel_id, thumbnail_path)

    def retry_playlist(self, job_dir, channel_id) -> dict:
        return self._retry(job_dir, channel_id)
