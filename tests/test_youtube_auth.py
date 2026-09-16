"""Secure credential storage, refresh, loopback authorization, and API status."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

from media.youtube_auth import (
    CREDENTIAL_KEY, SCOPES, TOKEN_URI, KeyringSecretStore,
    YouTubeAuth, YouTubeAuthError, _authorize_loopback, validate_client_config,
)
from tests.test_youtube import MemorySecrets, Response, ScriptedSession


CONFIG = {"installed": {
    "client_id": "test.apps.googleusercontent.com", "client_secret": "CLIENT_SECRET",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": TOKEN_URI,
}}


class Credentials:
    refresh_token = "REFRESH_SECRET"

    def __init__(self):
        self.token = "ACCESS_SECRET"

    def has_scopes(self, scopes):
        return set(scopes) == set(SCOPES)

    def to_json(self):
        return json.dumps({
            "token": self.token, "refresh_token": self.refresh_token,
            "client_id": CONFIG["installed"]["client_id"], "client_secret": "CLIENT_SECRET",
            "token_uri": TOKEN_URI, "scopes": list(SCOPES),
        })


class Session(ScriptedSession):
    def close(self):
        self.closed = True


class AuthTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "client.json"
        self.config.write_text(json.dumps(CONFIG), encoding="utf-8")
        self.secrets = MemorySecrets()
        self.credentials = Credentials()

    def account_responses(self):
        return [Response(data={"email": "user@example.com"}),
                Response(data={"items": [{"id": "channel1", "snippet": {"title": "Audiobooks"}}]}),
                Response(data={"items": [{"id": "playlist1", "snippet": {"title": "Bắc Tống"}}]}),
                Response(data={"items": [{"id": "22", "snippet": {"title": "People & Blogs", "assignable": True}},
                                         {"id": "1", "snippet": {"title": "Ignored", "assignable": False}}]})]

    def auth(self, session, **kwargs):
        return YouTubeAuth(
            self.config, self.secrets, credentials_factory=lambda info, scopes: self.credentials,
            session_factory=lambda credentials: session, **kwargs,
        )

    def test_config_accepts_desktop_bom_and_rejects_non_google_or_web_schema(self):
        self.config.write_text("\ufeff" + json.dumps(CONFIG), encoding="utf-8")
        self.assertEqual(validate_client_config(self.config), CONFIG)
        for config in ({"web": CONFIG["installed"]}, {"installed": {**CONFIG["installed"], "token_uri": "https://evil.test/token"}}, {}, []):
            self.config.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(YouTubeAuthError) as raised:
                validate_client_config(self.config)
            self.assertNotIn("CLIENT_SECRET", str(raised.exception))

    def test_restore_account_refresh_and_disconnect_use_secret_store_only(self):
        self.secrets.set(CREDENTIAL_KEY, self.credentials.to_json())
        session = Session(*self.account_responses(), Response())
        auth = self.auth(session)
        account = auth.restore()
        self.assertEqual(account["email"], "user@example.com")
        self.assertEqual(account["channel_id"], "channel1")
        self.assertEqual(account["playlists"][0]["id"], "playlist1")
        self.assertEqual(len(account["categories"]), 1)
        self.credentials.token = "REFRESHED_ACCESS_SECRET"
        auth.session().request("GET", "https://www.googleapis.com/youtube/v3/channels")
        self.assertIn("REFRESHED_ACCESS_SECRET", self.secrets.get(CREDENTIAL_KEY))
        self.assertNotIn("REFRESH_SECRET", self.config.read_text())
        self.assertEqual(list(self.root.iterdir()), [self.config])
        auth.disconnect()
        self.assertIsNone(self.secrets.get(CREDENTIAL_KEY))
        self.assertIsNone(auth.account)
        self.assertTrue(session.closed)

    def test_invalid_saved_scopes_or_refresh_revoke_require_reconnect(self):
        info = json.loads(self.credentials.to_json())
        info["scopes"] = []
        self.secrets.set(CREDENTIAL_KEY, json.dumps(info))
        with self.assertRaises(YouTubeAuthError) as raised:
            self.auth(Session()).restore()
        self.assertEqual(raised.exception.code, "reconnect")
        self.assertFalse(self.secrets.values)
        self.secrets.set(CREDENTIAL_KEY, self.credentials.to_json())
        with self.assertRaises(YouTubeAuthError) as raised:
            self.auth(Session(Response(401))).restore()
        self.assertEqual(raised.exception.code, "reconnect")
        self.assertFalse(self.secrets.values)

    def test_permission_quota_and_network_errors_are_safe(self):
        for failure, code in ((Response(403, data={"error": {"errors": [{"reason": "quotaExceeded", "message": "TOKEN_SECRET"}]}}), "quota"),
                              (Response(403), "permission"), (TimeoutError("TOKEN_SECRET"), "network")):
            self.secrets.set(CREDENTIAL_KEY, self.credentials.to_json())
            with self.assertRaises(YouTubeAuthError) as raised:
                self.auth(Session(failure)).restore()
            self.assertEqual(raised.exception.code, code)
            self.assertNotIn("TOKEN_SECRET", str(raised.exception))

    def test_insecure_keyring_backend_is_rejected_and_known_os_store_is_accepted(self):
        with self.assertRaises(YouTubeAuthError):
            KeyringSecretStore(MemorySecrets())
        backend_type = type("FakeSecretService", (), {
            "__module__": "keyring.backends.SecretService", "priority": 1,
            "get_password": lambda self, service, key: self.values.get(key),
            "set_password": lambda self, service, key, value: self.values.__setitem__(key, value),
            "delete_password": lambda self, service, key: self.values.pop(key),
        })
        backend = backend_type()
        backend.values = {}
        store = KeyringSecretStore(backend)
        store.set("secret", "value")
        self.assertEqual(store.get("secret"), "value")
        store.delete("secret")
        self.assertIsNone(store.get("secret"))

    def test_endpoint_redirect_guard_does_not_send_token_to_other_hosts(self):
        self.secrets.set(CREDENTIAL_KEY, self.credentials.to_json())
        session = Session(*self.account_responses())
        auth = self.auth(session)
        auth.restore()
        calls = len(session.calls)
        with self.assertRaises(YouTubeAuthError):
            auth.session().request("GET", "https://evil.test/steal")
        self.assertEqual(len(session.calls), calls)
        self.assertTrue(all(call[2]["allow_redirects"] is False for call in session.calls))

    def test_loopback_browser_state_check_and_token_exchange(self):
        class Flow:
            credentials = self.credentials

            def authorization_url(flow, **kwargs):
                return "https://accounts.google.com/auth?state=EXPECTED", "EXPECTED"

            def fetch_token(flow, **kwargs):
                flow.token_args = kwargs

        flow = Flow()
        results = []
        browser_threads = []

        def browser(url, **kwargs):
            self.assertEqual(parse_qs(urlsplit(url).query)["state"], ["EXPECTED"])

            def callback():
                from urllib.error import HTTPError
                try:
                    urlopen(flow.redirect_uri + "?state=WRONG&code=AUTH_SECRET", timeout=2)
                except HTTPError as error:
                    results.append(error.code)
                    error.close()
                with urlopen(flow.redirect_uri + "?state=EXPECTED&code=AUTH_SECRET", timeout=2) as response:
                    results.append(response.status)
            thread = threading.Thread(target=callback)
            browser_threads.append(thread)
            thread.start()
            return True

        credentials = _authorize_loopback(flow, threading.Event(), browser, timeout=5)
        for thread in browser_threads:
            thread.join(2)
        self.assertIs(credentials, self.credentials)
        self.assertEqual(results, [400, 200])
        self.assertTrue(flow.redirect_uri.startswith("http://127.0.0.1:"))
        self.assertEqual(flow.token_args["timeout"], (15, 30))
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(YouTubeAuthError) as raised:
            _authorize_loopback(flow, cancel, browser, timeout=5)
        self.assertEqual(raised.exception.code, "cancelled")

    def test_connect_persists_refresh_token_and_cancel_does_not_replace_credentials(self):
        auth = self.auth(Session(*self.account_responses()), flow_factory=lambda *args, **kwargs: object())
        with patch("media.youtube_auth._authorize_loopback", return_value=self.credentials):
            self.assertEqual(auth.connect()["channel_id"], "channel1")
        self.assertIn("REFRESH_SECRET", self.secrets.get(CREDENTIAL_KEY))
        with patch("media.youtube_auth._authorize_loopback", side_effect=YouTubeAuthError("cancelled", "cancelled")):
            with self.assertRaises(YouTubeAuthError):
                auth.connect()
        self.assertIn("REFRESH_SECRET", self.secrets.get(CREDENTIAL_KEY))

    def test_installed_oauth_library_generates_loopback_state_and_pkce(self):
        from media.youtube_auth import _flow_factory

        flow = _flow_factory(CONFIG, SCOPES)
        flow.redirect_uri = "http://127.0.0.1:50000/"
        url, state = flow.authorization_url(access_type="offline", prompt="consent")
        query = parse_qs(urlsplit(url).query)
        self.assertTrue(state)
        self.assertEqual(query["redirect_uri"], [flow.redirect_uri])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertTrue(flow.code_verifier)


if __name__ == "__main__":
    unittest.main()
