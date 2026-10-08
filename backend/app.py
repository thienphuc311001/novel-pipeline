"""Local HTTP/SSE transport; all workspace writes go through JobManager."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.jobs import BusyError, JobManager, MissingJobError
from backend.validation import ValidationError
from config.settings import config_dir
from pipeline.sessions import SessionError

_LOCAL_HOST = re.compile(r"^(localhost|127\.0\.0\.1)(?::([0-9]{1,5}))?$", re.IGNORECASE)
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_INPUT_EXTENSIONS = {".txt", ".zip"}
_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".json"}


def _local_authority(authority):
    match = _LOCAL_HOST.fullmatch(authority)
    if match is None or (match[2] is not None and not 1 <= int(match[2]) <= 65535):
        return None
    return match[1].lower(), int(match[2]) if match[2] else 80


def _allowed_origin(origin, host):
    if origin in _DEV_ORIGINS:
        return True
    try:
        parsed = urlsplit(origin)
        return (
            parsed.scheme == "http" and not parsed.path and not parsed.query and not parsed.fragment
            and parsed.username is None and parsed.password is None
            and _local_authority(parsed.netloc) == _local_authority(host)
            and _local_authority(parsed.netloc) is not None
        )
    except ValueError:
        return False


class LocalBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        hosts = request.headers.getlist("host")
        origins = request.headers.getlist("origin")
        if len(hosts) != 1 or _local_authority(hosts[0]) is None:
            return JSONResponse({"detail": "Chỉ cho phép truy cập từ máy cục bộ."}, status_code=403)
        if len(origins) > 1 or (origins and not _allowed_origin(origins[0], hosts[0])):
            return JSONResponse({"detail": "Nguồn truy cập không được phép."}, status_code=403)
        return await call_next(request)


def _persist_uploads(files, folder, extensions):
    if not files:
        raise HTTPException(422, "Chưa chọn tệp tải lên.")
    directory = None
    try:
        root = config_dir() / folder
        root.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="upload-", dir=root))
        paths = []
        used = set()
        for upload in files:
            # Both browser and Windows multipart paths can contain directory components.
            name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
            if not name or name in {".", ".."} or any(ord(char) < 32 for char in name) or ":" in name:
                raise HTTPException(422, "Tên tệp không hợp lệ.")
            if Path(name).suffix.lower() not in extensions:
                raise HTTPException(422, f"Loại tệp không được hỗ trợ: {name}")
            if name.casefold() in used:
                raise HTTPException(422, f"Tên tệp bị trùng: {name}")
            used.add(name.casefold())
            destination = directory / name
            with destination.open("xb") as handle:
                shutil.copyfileobj(upload.file, handle, length=1024 * 1024)
            paths.append(str(destination.resolve()))
        return {"paths": paths}
    except Exception:
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        for upload in files:
            upload.file.close()


def _download_path(manager, requested):
    try:
        candidate = Path(requested).expanduser().resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(404, "Không tìm thấy tệp đầu ra.") from None
    for row in manager.outputs():
        try:
            allowed = Path(row["path"]).expanduser()
            if not allowed.is_absolute() or allowed.resolve(strict=True) != allowed:
                continue
        except (OSError, ValueError, RuntimeError, KeyError):
            continue
        if candidate == allowed and candidate.is_file():
            return candidate
    raise HTTPException(404, "Tệp không thuộc danh sách đầu ra được phép.")


def create_app(service=None, *, dist_dir=None):
    @asynccontextmanager
    async def lifespan(application):
        if service is None:
            from pipeline.service import PipelineService
            workspace = PipelineService()
        else:
            workspace = service
        application.state.manager = JobManager(workspace)
        try:
            yield
        finally:
            await asyncio.to_thread(application.state.manager.close)

    application = FastAPI(title="Novel Pipeline", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware, allow_origins=_DEV_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_headers=["Content-Type"],
    )
    application.add_middleware(LocalBoundaryMiddleware)

    @application.exception_handler(BusyError)
    async def busy_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @application.exception_handler(MissingJobError)
    async def missing_job(request, error):
        return JSONResponse({"detail": "Không tìm thấy tác vụ."}, status_code=404)

    @application.exception_handler(ValidationError)
    async def invalid_input(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @application.exception_handler(SessionError)
    async def session_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @application.exception_handler(OSError)
    async def storage_error(request, error):
        return JSONResponse({"detail": f"Không truy cập được tệp: {error}"}, status_code=500)

    @application.exception_handler(ValueError)
    async def value_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    def manager(request):
        return request.app.state.manager

    @application.get("/api/health")
    def health():
        return {"status": "ok"}

    @application.get("/api/state")
    def state(request: Request):
        return manager(request).state()

    @application.get("/api/grouping")
    def grouping(request: Request, size: int = Query(default=20, ge=1)):
        return manager(request).preview_grouping(size)

    @application.get("/api/settings")
    def settings(request: Request):
        return manager(request).settings()

    @application.put("/api/settings")
    def update_settings(request: Request, data: dict = Body(...)):
        return manager(request).update_settings(data)

    @application.get("/api/jobs")
    def jobs(request: Request):
        return manager(request).jobs()

    @application.post("/api/jobs", status_code=202)
    def submit_job(request: Request, data: dict = Body(...)):
        if set(data) - {"action", "options"}:
            raise ValidationError("Trường tác vụ không được hỗ trợ.")
        return manager(request).submit(data.get("action"), data.get("options", {}))

    @application.get("/api/jobs/{job_id}")
    def job(request: Request, job_id: str):
        return manager(request).job(job_id)

    @application.post("/api/jobs/{job_id}/stop")
    def stop_job(request: Request, job_id: str):
        return manager(request).stop(job_id)

    @application.get("/api/jobs/{job_id}/logs")
    def logs(request: Request, job_id: str, after: int = Query(default=0, ge=0)):
        return manager(request).logs(job_id, after)

    @application.get("/api/events")
    async def events(request: Request):
        workspace = manager(request)

        async def stream():
            last_version = None
            last_state_revision = None
            last_emit = 0.0
            loop = asyncio.get_running_loop()
            while not await request.is_disconnected():
                version, live, view = workspace.event_view(last_state_revision)
                now = loop.time()
                if version != last_version or (live and now - last_emit >= 10):
                    payload = json.dumps(view, ensure_ascii=False, allow_nan=False)
                    yield f"event: update\ndata: {payload}\n\n"
                    last_version = version
                    last_state_revision = view["state_revision"]
                    last_emit = now
                await asyncio.sleep(0.25)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
        })

    @application.post("/api/inputs")
    def inputs(files: list[UploadFile] = File(...)):
        return _persist_uploads(files, "imports", _INPUT_EXTENSIONS)

    @application.post("/api/assets")
    def assets(files: list[UploadFile] = File(...)):
        return _persist_uploads(files, "assets", _ASSET_EXTENSIONS)

    @application.get("/api/outputs")
    def outputs(request: Request):
        return manager(request).outputs()

    @application.get("/api/outputs/download")
    def download(request: Request, path: str = Query(...)):
        resolved = _download_path(manager(request), path)
        return FileResponse(resolved, filename=resolved.name)

    @application.get("/api/sessions")
    def sessions(request: Request):
        return manager(request).service.sessions.list_sessions()

    @application.post("/api/sessions")
    def save_session(request: Request, data: dict = Body(...)):
        if set(data) - {"ui"}:
            raise ValidationError("Trường phiên làm việc không được hỗ trợ.")
        return {"id": manager(request).save_session(data.get("ui", {}))}

    # Literal new must be registered ahead of the parameterized session route.
    @application.post("/api/sessions/new")
    def new_session(request: Request):
        return manager(request).new_session()

    @application.post("/api/sessions/{session_id}/open")
    def open_session(request: Request, session_id: str):
        return manager(request).open_session(session_id)

    dist = Path(dist_dir) if dist_dir is not None else Path(__file__).resolve().parent.parent / "frontend" / "dist"

    @application.get("/{asset_path:path}")
    def frontend(asset_path: str):
        if asset_path == "api" or asset_path.startswith("api/"):
            raise HTTPException(404, "API không tồn tại.")
        root = dist.resolve()
        candidate = (root / asset_path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(404, "Không tìm thấy tài nguyên.")
        if candidate.is_file():
            return FileResponse(candidate)
        index = root / "index.html"
        if not Path(asset_path).suffix and index.is_file():
            return FileResponse(index)
        raise HTTPException(404, "Giao diện chưa được dựng hoặc tài nguyên không tồn tại.")

    return application


app = create_app()
