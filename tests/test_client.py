import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.auth_manager import AuthManager
from backend.client import TelegramClientManager


class TelegramClientManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config = SimpleNamespace(
            session_type="user",
            api_id=12345,
            api_hash="test-hash",
            bot_token=None,
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
