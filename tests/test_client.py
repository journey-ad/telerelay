import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.auth_manager import AuthManager
from backend.client import TelegramClientManager


class TelegramClientManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config = SimpleNamespace(
            api_id=12345,
            api_hash="test-hash",
            proxy_url=None,
        )
        self.session_name = str(Path(self.temp_dir.name) / "session")

    async def test_connect_failure_sets_auth_error(self):
        auth = AuthManager()
        manager = TelegramClientManager(
            self.config,
            auth_manager=auth,
            session_name=self.session_name,
        )
        client = MagicMock()
        client.start.side_effect = RuntimeError("phone number banned")
        with patch("backend.client.TelegramClient", return_value=client):
            self.assertFalse(await manager.connect())

        state = auth.get_state()
        self.assertEqual(state["state"], "error")
        self.assertIn("banned", state["error"])

    async def test_refresh_identity_reloads_profile_and_avatar(self):
        identities = []
        manager = TelegramClientManager(
            self.config,
            session_name=self.session_name,
            on_user_authenticated=identities.append,
        )
        me = SimpleNamespace(
            first_name="Updated",
            last_name="User",
            username="updated_user",
            id=12345,
        )
        manager.client = SimpleNamespace(
            get_me=AsyncMock(return_value=me),
            download_profile_photo=AsyncMock(return_value=b"updated-avatar"),
        )

        identity = await manager.refresh_identity()

        self.assertEqual(identity["display_name"], "Updated User")
        self.assertEqual(identity["username"], "updated_user")
        self.assertEqual(identity["avatar_bytes"], b"updated-avatar")
        self.assertEqual(identities, [identity])
