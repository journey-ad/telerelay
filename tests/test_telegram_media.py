import base64
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon.crypto import AuthKey
from telethon.tl import alltlobjects

from backend.telegram_media import TelegramMediaService


class TelegramMediaServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_main_sender_when_media_is_on_current_dc(self):
        main_sender = SimpleNamespace(auth_key=AuthKey(bytes(range(256))))
        client = SimpleNamespace(
            session=SimpleNamespace(dc_id=5),
            _sender=main_sender,
            _borrow_exported_sender=AsyncMock(),
        )

        sender, borrowed = await TelegramMediaService._permanent_sender(client, 5)

        self.assertIs(sender, main_sender)
        self.assertFalse(borrowed)
        client._borrow_exported_sender.assert_not_awaited()

    async def test_borrows_sender_when_media_is_on_another_dc(self):
        exported_sender = SimpleNamespace(auth_key=AuthKey(bytes(reversed(range(256)))))
        client = SimpleNamespace(
            session=SimpleNamespace(dc_id=2),
            _sender=SimpleNamespace(auth_key=AuthKey(bytes(range(256)))),
            _borrow_exported_sender=AsyncMock(return_value=exported_sender),
        )

        sender, borrowed = await TelegramMediaService._permanent_sender(client, 5)

        self.assertIs(sender, exported_sender)
        self.assertTrue(borrowed)
        client._borrow_exported_sender.assert_awaited_once_with(5)

    async def test_ticket_contains_target_dc_auth_state_for_in_memory_worker(self):
        auth_key = AuthKey(bytes(range(256)))
        sender = SimpleNamespace(
            auth_key=auth_key,
            _state=SimpleNamespace(salt=-17, time_offset=9),
        )
        client = SimpleNamespace(
            session=SimpleNamespace(dc_id=4),
            _sender=sender,
            _borrow_exported_sender=AsyncMock(),
        )
        document = SimpleNamespace(
            dc_id=4,
            id=101,
            access_hash=-202,
            file_reference=b"reference",
            size=4096,
        )
        media_file = SimpleNamespace(
            mime_type="video/mp4",
            name="clip.mp4",
            size=4096,
        )
        service = TelegramMediaService(
            None,
            None,
            SimpleNamespace(api_id=12345, api_hash="hash"),
        )

        with (
            patch.object(service, "_client", return_value=client),
            patch.object(service, "_message", AsyncMock(return_value=object())),
            patch.object(service, "_video_file", return_value=(document, media_file)),
        ):
            ticket = await service.issue_video_ticket(
                account_id="123",
                chat_id=456,
                message_id=789,
            )

        self.assertEqual(ticket["api_id"], 12345)
        self.assertEqual(ticket["api_layer"], alltlobjects.LAYER)
        self.assertEqual(ticket["dc_id"], 4)
        self.assertEqual(ticket["dc_address"], "kws4-1.web.telegram.org")
        self.assertEqual(
            ticket["auth_key"],
            base64.urlsafe_b64encode(bytes(auth_key.key)).decode("ascii").rstrip("="),
        )
        self.assertEqual(ticket["auth_key_id"], str(auth_key.key_id))
        self.assertEqual(ticket["server_salt"], "-17")
        self.assertEqual(ticket["time_offset"], 9)
        self.assertEqual(ticket["file"]["id"], "101")
        self.assertEqual(ticket["mime_type"], "video/mp4")
        self.assertEqual(ticket["size"], 4096)


if __name__ == "__main__":
    unittest.main()
