"""Desktop Google OAuth and OS-keychain storage, independent of Qt.

No access token, refresh token, OAuth callback, or resumable URL is written to
project files or included in error messages. Network work belongs in a worker.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, urlsplit


SCOPES = (
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
)
AUTH_URIS = {
    "https://accounts.google.com/o/oauth2/auth",
    "https://accounts.google.com/o/oauth2/v2/auth",
}
TOKEN_URI = "https://oauth2.googleapis.com/token"
CREDENTIAL_KEY = "youtube-oauth-credentials-v1"
KEYRING_SERVICE = "novel-pipeline.youtube"
NETWORK_TIMEOUT = (15, 60)


class YouTubeAuthError(RuntimeError):
    """A safe, user-facing error; ``code`` supports UI/retry decisions."""

    def __init__(self, message: str, code: str = "authentication"):
        super().__init__(message)
        self.code = code


class SecretStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class KeyringSecretStore:
    """Use only known OS-backed keyrings, never keyrings.alt or file stores."""

    _SECURE_MODULES = {
        "keyring.backends.SecretService", "keyring.backends.libsecret",
        "keyring.backends.kwallet", "keyring.backends.Windows",
        "keyring.backends.macOS",
    }

    def __init__(self, backend: Any = None):
        try:
            if backend is None:
                import keyring
                backend = keyring.get_keyring()
            candidates = (
                backend.backends
                if type(backend).__module__ == "keyring.backends.chainer"
                else [backend]
            )
            self._backend = next(
                candidate for candidate in candidates
                if type(candidate).__module__ in self._SECURE_MODULES
                and candidate.priority > 0
            )
        except Exception:
            raise YouTubeAuthError(
                "Không có kho khóa hệ điều hành an toàn. Bật Secret Service/KWallet "
                "(Linux), Keychain (macOS), hoặc Credential Manager (Windows). "
                "Ứng dụng không lưu token vào tệp văn bản.", "keyring",
            ) from None

    def get(self, key: str) -> str | None:
        try:
            return self._backend.get_password(KEYRING_SERVICE, key)
        except Exception:
            raise YouTubeAuthError("Không đọc được kho khóa hệ điều hành; hãy mở khóa kho khóa.", "keyring") from None

    def set(self, key: str, value: str) -> None:
        try:
            self._backend.set_password(KEYRING_SERVICE, key, value)
        except Exception:
            raise YouTubeAuthError("Không lưu được thông tin vào kho khóa hệ điều hành.", "keyring") from None

    def delete(self, key: str) -> None:
        try:
            if self._backend.get_password(KEYRING_SERVICE, key) is not None:
                self._backend.delete_password(KEYRING_SERVICE, key)
        except Exception:
            raise YouTubeAuthError("Không xóa được thông tin khỏi kho khóa hệ điều hành.", "keyring") from None


def validate_client_config(path: str | Path) -> dict:
    """Accept Google's downloaded Desktop client format with fixed endpoints."""
    if not str(path or "").strip():
        raise YouTubeAuthError("Chọn OAuth Desktop client JSON trong Settings trước khi kết nối YouTube.", "configuration")
    try:
        with Path(path).expanduser().open(encoding="utf-8-sig") as handle:
            config = json.load(handle)
        installed = config["installed"]
        if not isinstance(installed, dict) or "web" in config:
            raise ValueError
        if not all(isinstance(installed.get(key), str) and installed[key].strip()
                   for key in ("client_id", "client_secret", "auth_uri", "token_uri")):
            raise ValueError
        if not installed["client_id"].endswith(".apps.googleusercontent.com"):
            raise ValueError
        if installed["auth_uri"] not in AUTH_URIS or installed["token_uri"] != TOKEN_URI:
            raise ValueError
        # Ignore additional downloaded metadata and redirect URIs. The callback
        # is exclusively a random port on 127.0.0.1, constructed below.
        return {"installed": {key: installed[key] for key in (
            "client_id", "client_secret", "auth_uri", "token_uri",
        )}}
    except (OSError, ValueError, KeyError, TypeError):
        raise YouTubeAuthError(
            "OAuth JSON không hợp lệ. Dùng client loại Desktop app tải từ Google Cloud, với endpoint Google chính thức.",
            "configuration",
        ) from None


def _credentials_factory(info: dict, scopes: tuple[str, ...]):
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        raise YouTubeAuthError("Thiếu thư viện Google OAuth. Chạy pip install -r requirements.txt.", "dependency") from None
    return Credentials.from_authorized_user_info(info, scopes=scopes)


def _session_factory(credentials):
    try:
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        raise YouTubeAuthError("Thiếu thư viện Google OAuth. Chạy pip install -r requirements.txt.", "dependency") from None
    return AuthorizedSession(credentials, refresh_timeout=30, max_refresh_attempts=1)


def _flow_factory(config, scopes):
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise YouTubeAuthError("Thiếu google-auth-oauthlib. Chạy pip install -r requirements.txt.", "dependency") from None
    return InstalledAppFlow.from_client_config(config, scopes=scopes, autogenerate_code_verifier=True)


class _LoopbackServer(HTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(1)
        return connection, address


def _authorize_loopback(flow, cancel_event: Event, browser_opener: Callable, timeout: float):
    callback: dict[str, str] = {}
    expected_state = ""

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Authorization codes and state occur in the request URL.

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            valid = (len(self.path) < 16384 and parsed.path == "/"
                     and query.get("state") == [expected_state]
                     and (len(query.get("code", [])) == 1 or "error" in query))
            if valid:
                callback["path"] = self.path
            body = ("Authorization received. You may close this window."
                    if valid else "Invalid authorization callback.").encode()
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    if cancel_event.is_set():
        raise YouTubeAuthError("Đã hủy kết nối YouTube.", "cancelled")
    with _LoopbackServer(("127.0.0.1", 0), CallbackHandler) as server:
        server.timeout = 0.2
        flow.redirect_uri = f"http://127.0.0.1:{server.server_port}/"
        url, expected_state = flow.authorization_url(
            access_type="offline", prompt="consent", include_granted_scopes="true",
        )
        if not browser_opener(url, new=1, autoraise=True):
            raise YouTubeAuthError("Không mở được trình duyệt hệ thống để đăng nhập Google.", "browser")
        deadline = time.monotonic() + timeout
        while not callback:
            if cancel_event.is_set():
                raise YouTubeAuthError("Đã hủy kết nối YouTube.", "cancelled")
            if time.monotonic() >= deadline:
                raise YouTubeAuthError("Hết thời gian chờ Google xác thực; hãy kết nối lại.", "timeout")
            server.handle_request()
        if cancel_event.is_set():
            raise YouTubeAuthError("Đã hủy kết nối YouTube.", "cancelled")
        if "error" in parse_qs(urlsplit(callback["path"]).query):
            raise YouTubeAuthError("Quyền truy cập Google chưa được cấp. Hãy kết nối lại và cấp quyền YouTube.", "permission")
        # Match InstalledAppFlow's HTTPS normalization for oauthlib validation;
        # the browser callback itself is permitted HTTP on loopback only.
        response_url = f"https://127.0.0.1:{server.server_port}{callback['path']}"
        flow.fetch_token(authorization_response=response_url, timeout=(15, 30))
        return flow.credentials


class _PersistingSession:
    """Persist any automatic token refresh without exposing request secrets."""

    def __init__(self, owner: "YouTubeAuth", session):
        self._owner = owner
        self._session = session

    def request(self, method, url, **kwargs):
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in {
            "www.googleapis.com", "youtube.googleapis.com", "openidconnect.googleapis.com",
        } or parts.username or parts.password or parts.port not in (None, 443):
            raise YouTubeAuthError("Endpoint YouTube không hợp lệ.", "configuration")
        kwargs.setdefault("timeout", NETWORK_TIMEOUT)
        kwargs["allow_redirects"] = False
        try:
            response = self._session.request(method, url, **kwargs)
        except Exception as error:
            if type(error).__name__ == "RefreshError" and not getattr(error, "retryable", False):
                self._owner._invalidate_credentials()
                raise YouTubeAuthError("Phiên Google đã hết hạn hoặc bị thu hồi. Hãy kết nối lại YouTube.", "reconnect") from None
            raise YouTubeAuthError("Lỗi mạng khi liên lạc Google; hãy kiểm tra kết nối và thử lại.", "network") from None
        self._owner._persist_credentials()
        if response.status_code == 401:
            self._owner._invalidate_credentials()
            raise YouTubeAuthError("Google từ chối phiên xác thực. Hãy kết nối lại YouTube.", "reconnect")
        return response

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def close(self):
        self._session.close()


class YouTubeAuth:
    """One desktop account, whose token material lives exclusively in a keyring."""

    def __init__(
        self, client_secrets_path: str | Path = "", secret_store: SecretStore | None = None,
        *, credentials_factory: Callable = _credentials_factory,
        session_factory: Callable = _session_factory, flow_factory: Callable = _flow_factory,
        browser_opener: Callable = webbrowser.open, authorization_timeout: float = 300,
    ):
        self.client_secrets_path = str(client_secrets_path or "")
        self._secret_store = secret_store
        self._credentials_factory = credentials_factory
        self._session_factory = session_factory
        self._flow_factory = flow_factory
        self._browser_opener = browser_opener
        self._authorization_timeout = authorization_timeout
        self._credentials = None
        self._session = None
        self._saved_digest = ""
        self.account: dict | None = None

    @property
    def secret_store(self) -> SecretStore:
        if self._secret_store is None:
            self._secret_store = KeyringSecretStore()
        return self._secret_store

    def _persist_credentials(self):
        if self._credentials is None:
            return
        try:
            raw = self._credentials.to_json()
        except Exception:
            raise YouTubeAuthError("Không thể lưu phiên Google; hãy kết nối lại.", "authentication") from None
        digest = hashlib.sha256(raw.encode()).hexdigest()
        if digest != self._saved_digest:
            self.secret_store.set(CREDENTIAL_KEY, raw)
            self._saved_digest = digest

    def _invalidate_credentials(self):
        self._credentials = None
        self._saved_digest = ""
        self.account = None
        if self._session is not None:
            self._session.close()
            self._session = None
        self.secret_store.delete(CREDENTIAL_KEY)

    def restore(self) -> dict | None:
        raw = self.secret_store.get(CREDENTIAL_KEY)
        if not raw:
            return None
        try:
            info = json.loads(raw)
            if (not isinstance(info, dict) or not info.get("refresh_token")
                    or info.get("token_uri", TOKEN_URI) != TOKEN_URI
                    or not set(SCOPES).issubset(info.get("scopes", []))):
                raise ValueError
            if self.client_secrets_path:
                config = validate_client_config(self.client_secrets_path)
                if info.get("client_id") != config["installed"]["client_id"]:
                    raise ValueError
            self._credentials = self._credentials_factory(info, SCOPES)
            self._saved_digest = hashlib.sha256(raw.encode()).hexdigest()
        except YouTubeAuthError:
            raise
        except Exception:
            self._invalidate_credentials()
            raise YouTubeAuthError("Phiên Google đã lưu không hợp lệ. Hãy kết nối lại YouTube.", "reconnect") from None
        return self.fetch_account()

    def connect(self, cancel_event: Event | None = None) -> dict:
        cancel = cancel_event or Event()
        config = validate_client_config(self.client_secrets_path)
        # Ensure secure storage is usable before opening an authorization page.
        self.secret_store.get(CREDENTIAL_KEY)
        try:
            flow = self._flow_factory(config, SCOPES)
            credentials = _authorize_loopback(flow, cancel, self._browser_opener, self._authorization_timeout)
            if cancel.is_set():
                raise YouTubeAuthError("Đã hủy kết nối YouTube.", "cancelled")
            if not credentials.refresh_token or not credentials.has_scopes(SCOPES):
                raise YouTubeAuthError("Google chưa cấp đủ quyền hoặc refresh token. Hãy kết nối lại và cấp quyền.", "permission")
            if self._session is not None:
                self._session.close()
            self._credentials = credentials
            self._session = None
            self._saved_digest = ""
            self._persist_credentials()
            return self.fetch_account()
        except YouTubeAuthError:
            raise
        except Exception:
            raise YouTubeAuthError("Không thể xác thực Google. Kiểm tra OAuth Desktop client và kết nối lại.", "authentication") from None

    def disconnect(self):
        """Forget local authorization; revoke remotely in Google account if desired."""
        self._invalidate_credentials()

    def session(self):
        if self._credentials is None:
            raise YouTubeAuthError("Chưa kết nối YouTube. Hãy kết nối tài khoản Google.", "reconnect")
        if self._session is None:
            self._session = _PersistingSession(self, self._session_factory(self._credentials))
        return self._session

    def _get_json(self, url: str, params: dict | None = None) -> dict:
        response = self.session().get(url, params=params or {}, timeout=NETWORK_TIMEOUT)
        if response.status_code == 403:
            # Parse only machine-readable reason codes, never remote messages.
            try:
                reasons = {item.get("reason") for item in response.json().get("error", {}).get("errors", [])}
            except Exception:
                reasons = set()
            if reasons & {"quotaExceeded", "dailyLimitExceeded"}:
                raise YouTubeAuthError("Đã hết hạn mức YouTube API; thử lại khi hạn mức được đặt lại.", "quota")
            raise YouTubeAuthError("YouTube từ chối quyền truy cập. Bật YouTube Data API v3 và kiểm tra quyền OAuth.", "permission")
        if response.status_code != 200:
            raise YouTubeAuthError("Không lấy được thông tin tài khoản từ Google/YouTube. Hãy thử lại.", "network")
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError
            return payload
        except Exception:
            raise YouTubeAuthError("Google trả về dữ liệu tài khoản không hợp lệ.", "response") from None

    def fetch_account(self) -> dict:
        identity = self._get_json("https://openidconnect.googleapis.com/v1/userinfo")
        channels = self._get_json("https://www.googleapis.com/youtube/v3/channels", {
            "part": "snippet", "mine": "true", "maxResults": 50,
        }).get("items", [])
        if not channels:
            raise YouTubeAuthError("Tài khoản này chưa có kênh YouTube. Tạo kênh rồi kết nối lại.", "channel")
        channel = channels[0]
        self.account = {
            "email": str(identity.get("email", "")),
            "channel_id": str(channel.get("id", "")),
            "channel_title": str(channel.get("snippet", {}).get("title", "")),
            "playlists": self.fetch_playlists(), "categories": self.fetch_categories(),
        }
        return self.account

    def fetch_playlists(self) -> list[dict]:
        result = []
        page_token = ""
        seen = set()
        while True:
            params = {"part": "snippet", "mine": "true", "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token
            payload = self._get_json("https://www.googleapis.com/youtube/v3/playlists", params)
            result.extend({"id": str(item["id"]), "title": str(item["snippet"]["title"])}
                          for item in payload.get("items", [])
                          if item.get("id") and item.get("snippet", {}).get("title"))
            page_token = payload.get("nextPageToken", "")
            if not page_token or page_token in seen:
                break
            seen.add(page_token)
        return result

    def fetch_categories(self, region_code: str = "VN") -> list[dict]:
        payload = self._get_json("https://www.googleapis.com/youtube/v3/videoCategories", {
            "part": "snippet", "regionCode": region_code,
        })
        return [{"id": str(item["id"]), "title": str(item["snippet"]["title"])}
                for item in payload.get("items", [])
                if item.get("id") and item.get("snippet", {}).get("assignable")
                and item.get("snippet", {}).get("title")]
