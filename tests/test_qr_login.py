"""QR code login: AuthManager login-mode selection and client QR flow."""

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.auth_manager import AuthManager
from backend.client import TelegramClientManager
from telethon.errors import SessionPasswordNeededError


class AuthManagerLoginModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_wait_for_login_mode_defaults_to_phone(self):
        auth = AuthManager(input_timeout=0.1)
        self.assertEqual(await auth.wait_for_login_mode(), "phone")
        self.assertEqual(auth.get_state()["state"], "waiting_phone")

    async def test_qr_mode_selected(self):
        auth = AuthManager()
        self.assertTrue(auth.submit_login_mode("qr"))
        self.assertEqual(await auth.wait_for_login_mode(), "qr")

    async def test_invalid_mode_rejected(self):
        auth = AuthManager()
        self.assertFalse(auth.submit_login_mode("email"))
        self.assertEqual(auth.get_state()["state"], "error")

    async def test_mode_switch_rejected_after_code_challenge(self):
        auth = AuthManager()
        auth.submit_login_mode("phone")
        auth._pending_kind = "code"  # send_code_request already in flight
        self.assertFalse(auth.submit_login_mode("qr"))
        self.assertEqual(auth.get_state()["state"], "idle")

    async def test_phone_submission_selects_phone_and_buffers_value(self):
        auth = AuthManager()
        self.assertTrue(auth.submit_phone("+8613800138000"))
        self.assertEqual(await auth.wait_for_login_mode(), "phone")
        self.assertEqual(await auth.phone_callback(), "+8613800138000")

    async def test_qr_state_published_and_cleared(self):
        auth = AuthManager()
        auth.set_qr("tg://login?token=abc", "2025-01-01T00:00:00+00:00")
        state = auth.get_state()
        self.assertEqual(state["state"], "waiting_qr")
        self.assertEqual(state["qr"]["url"], "tg://login?token=abc")
        auth.clear_qr()
        self.assertNotIn("qr", auth.get_state())

    async def test_mode_change_resolves_waiter(self):
        auth = AuthManager()
        change = asyncio.create_task(auth.wait_for_mode_change())
        await asyncio.sleep(0)
        self.assertTrue(auth.submit_login_mode("phone"))
        self.assertEqual(await change, "phone")

    async def test_reset_clears_qr_and_mode(self):
        auth = AuthManager(input_timeout=0.1)
        auth.set_qr("tg://login?token=abc", "2025-01-01T00:00:00+00:00")
        auth.submit_login_mode("qr")
        auth.reset()
        state = auth.get_state()
        self.assertNotIn("qr", state)
        self.assertEqual(state["state"], "idle")
        self.assertEqual(await auth.wait_for_login_mode(), "phone")


def _qr_mock(url="tg://login?token=abc"):
    qr = MagicMock()
    qr.url = url
    qr.expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    qr.recreate = AsyncMock()
    return qr


class QrLoginFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config = SimpleNamespace(
            api_id=12345,
            api_hash="test-hash",
            proxy_url=None,
        )
        self.session_name = str(Path(self.temp_dir.name) / "session")

    def _manager(self, auth):
        return TelegramClientManager(
            self.config,
            auth_manager=auth,
            session_name=self.session_name,
        )

    async def test_qr_login_success(self):
        auth = AuthManager()
        manager = self._manager(auth)
        me = SimpleNamespace(first_name="QR", last_name="User", username="qr_user", id=12345)
        qr = _qr_mock()
        qr.wait = AsyncMock(return_value=me)
        client = MagicMock()
        client.connect = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        client.qr_login = AsyncMock(return_value=qr)
        client.get_me = AsyncMock(return_value=me)
        auth.submit_login_mode("qr")
        with patch("backend.client.TelegramClient", return_value=client):
            self.assertTrue(await manager.connect())

        self.assertEqual(auth.get_state()["state"], "success")
        qr.wait.assert_awaited()

    async def test_qr_login_requires_2fa_password(self):
        auth = AuthManager()
        manager = self._manager(auth)
        me = SimpleNamespace(first_name="QR", last_name="User", username="qr_user", id=12345)
        qr = _qr_mock()
        qr.wait = AsyncMock(side_effect=SessionPasswordNeededError(request=None))
        client = MagicMock()
        client.connect = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        client.qr_login = AsyncMock(return_value=qr)
        client.sign_in = AsyncMock(return_value=me)
        client.get_me = AsyncMock(return_value=me)
        auth.submit_login_mode("qr")
        with patch("backend.client.TelegramClient", return_value=client):
            connect_task = asyncio.create_task(manager.connect())
            for _ in range(100):
                if auth.get_state()["state"] == "waiting_password":
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(auth.get_state()["state"], "waiting_password")
            self.assertTrue(auth.submit_password("secret"))
            self.assertTrue(await connect_task)

        client.sign_in.assert_awaited_with(password="secret")
        self.assertEqual(auth.get_state()["state"], "success")

    async def test_qr_expiry_refreshes_token(self):
        auth = AuthManager()
        manager = self._manager(auth)
        me = SimpleNamespace(first_name="QR", last_name="User", username="qr_user", id=12345)
        qr = _qr_mock()
        calls = {"n": 0}

        async def waits():
            calls["n"] += 1
            if calls["n"] == 1:
                raise asyncio.TimeoutError
            return me

        qr.wait = AsyncMock(side_effect=waits)
        client = MagicMock()
        client.connect = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        client.qr_login = AsyncMock(return_value=qr)
        client.get_me = AsyncMock(return_value=me)
        auth.submit_login_mode("qr")
        with patch("backend.client.TelegramClient", return_value=client):
            self.assertTrue(await manager.connect())

        qr.recreate.assert_awaited()
        self.assertEqual(calls["n"], 2)
        self.assertEqual(auth.get_state()["state"], "success")

    async def test_qr_login_switches_back_to_phone(self):
        auth = AuthManager()
        manager = self._manager(auth)
        me = SimpleNamespace(first_name="QR", last_name="User", username="qr_user", id=12345)
        qr = _qr_mock()
        hold_event = asyncio.Event()

        async def hold():
            await hold_event.wait()

        qr.wait = AsyncMock(side_effect=hold)
        client = MagicMock()
        client.connect = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        client.qr_login = AsyncMock(return_value=qr)
        client.start = AsyncMock()
        client.get_me = AsyncMock(return_value=me)
        with patch("backend.client.TelegramClient", return_value=client):
            connect_task = asyncio.create_task(manager.connect())
            await asyncio.sleep(0.05)
            self.assertTrue(auth.submit_login_mode("qr"))
            # Wait until the QR loop is actually waiting for a mode change.
            for _ in range(100):
                if auth._mode_change_future is not None:
                    break
                await asyncio.sleep(0.01)
            self.assertIsNotNone(auth._mode_change_future)
            # Switch back to the phone flow while the QR is displayed.
            self.assertTrue(auth.submit_login_mode("phone"))
            self.assertTrue(await connect_task)

        client.start.assert_awaited()
        self.assertEqual(auth.get_state()["state"], "success")

    async def test_qr_login_cancel_cleans_up_tasks(self):
        auth = AuthManager()
        manager = self._manager(auth)
        qr = _qr_mock()
        hold_event = asyncio.Event()

        async def hold():
            await hold_event.wait()

        qr.wait = AsyncMock(side_effect=hold)
        client = MagicMock()
        client.connect = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        client.qr_login = AsyncMock(return_value=qr)
        auth.submit_login_mode("qr")
        with patch("backend.client.TelegramClient", return_value=client):
            task = asyncio.create_task(manager.connect())
            for _ in range(100):
                if auth._mode_change_future is not None:
                    break
                await asyncio.sleep(0.01)
            self.assertIsNotNone(auth._mode_change_future)
            task.cancel()
            result = await asyncio.gather(task, return_exceptions=True)
            self.assertIsInstance(result[0], asyncio.CancelledError)
        # No orphaned waiter remains armed after cancellation.
        self.assertIsNone(auth._mode_change_future)


if __name__ == "__main__":
    unittest.main()
