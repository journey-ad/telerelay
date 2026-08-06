import base64
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon.crypto import AuthKey
from telethon.tl import alltlobjects, types

from backend.telegram_resource import TelegramResourceService
from backend.telegram_preview import TelegramPreviewError


class TelegramResourceServiceTests(unittest.IsolatedAsyncioTestCase):
    def _service(self):
        return TelegramResourceService(
            None,
            None,
            SimpleNamespace(api_id=12345, api_hash="hash"),
        )

    def _auth_client(self):
        auth_key = AuthKey(bytes(range(256)))
        sender = SimpleNamespace(
            auth_key=auth_key,
            _state=SimpleNamespace(salt=-17, time_offset=9),
        )
        return (
            SimpleNamespace(
                session=SimpleNamespace(dc_id=4),
                _sender=sender,
                _borrow_exported_sender=AsyncMock(),
            ),
            auth_key,
        )

    async def test_uses_main_sender_when_media_is_on_current_dc(self):
        main_sender = SimpleNamespace(auth_key=AuthKey(bytes(range(256))))
        client = SimpleNamespace(
            session=SimpleNamespace(dc_id=5),
            _sender=main_sender,
            _borrow_exported_sender=AsyncMock(),
        )

        sender, borrowed = await TelegramResourceService._permanent_sender(client, 5)

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

        sender, borrowed = await TelegramResourceService._permanent_sender(client, 5)

        self.assertIs(sender, exported_sender)
        self.assertTrue(borrowed)
        client._borrow_exported_sender.assert_awaited_once_with(5)

    async def test_resource_info_contains_file_reference_only(self):
        client, _ = self._auth_client()
        location = {
            "location_type": "document",
            "id": "101",
            "access_hash": "-202",
            "file_reference": "cmVmZXJlbmNl",
            "dc_id": 4,
            "size": 4096,
            "thumb_size": "",
        }
        service = self._service()

        with (
            patch.object(service, "_client", return_value=client),
            patch.object(service, "_message", AsyncMock(return_value=object())),
            patch.object(
                service,
                "_media_location",
                return_value=(location, "video/mp4", "clip.mp4"),
            ),
        ):
            info = await service.issue_resource_info(
                account_id="123",
                chat_id=456,
                message_id=789,
            )

        self.assertEqual(info["location_type"], "document")
        self.assertEqual(info["file"]["id"], "101")
        self.assertEqual(info["file"]["thumb_size"], "")
        self.assertEqual(info["mime_type"], "video/mp4")
        self.assertEqual(info["size"], 4096)
        self.assertTrue(info["ticket"])
        # File info must never carry the account's DC credentials.
        self.assertNotIn("api_id", info)
        self.assertNotIn("auth_key", info)
        self.assertNotIn("auth_key_id", info)
        self.assertNotIn("server_salt", info)
        self.assertNotIn("time_offset", info)
        self.assertNotIn("dc_address", info)

    async def test_dc_credentials_contain_target_dc_auth_state(self):
        client, auth_key = self._auth_client()
        service = self._service()

        with patch.object(service, "_client", return_value=client):
            credentials = await service.issue_dc_credentials(account_id="123", dc_id=4)

        self.assertEqual(credentials["api_id"], 12345)
        self.assertEqual(credentials["api_layer"], alltlobjects.LAYER)
        self.assertEqual(credentials["dc_id"], 4)
        self.assertEqual(credentials["dc_address"], "kws4-1.web.telegram.org")
        self.assertEqual(credentials["dc_port"], 443)
        self.assertEqual(
            credentials["auth_key"],
            base64.urlsafe_b64encode(bytes(auth_key.key)).decode("ascii").rstrip("="),
        )
        self.assertEqual(credentials["auth_key_id"], str(auth_key.key_id))
        self.assertEqual(credentials["server_salt"], "-17")
        self.assertEqual(credentials["time_offset"], 9)
        # Credentials must not include file-scoped ticket data.
        self.assertNotIn("ticket", credentials)
        self.assertNotIn("file", credentials)

    async def test_dc_credentials_reject_unsupported_dc(self):
        client, _ = self._auth_client()
        service = self._service()

        with patch.object(service, "_client", return_value=client):
            with self.assertRaises(TelegramPreviewError) as context:
                await service.issue_dc_credentials(account_id="123", dc_id=9)

        self.assertEqual(context.exception.code, "resource_dc_unsupported")

    async def test_avatar_info_issues_peer_photo_reference(self):
        client, _ = self._auth_client()
        client.get_entity = AsyncMock(
            return_value=types.User(
                id=303,
                access_hash=404,
                first_name="Release",
                last_name=None,
                username="release_bot",
                bot=True,
                photo=types.UserProfilePhoto(
                    photo_id=505,
                    dc_id=4,
                    has_video=False,
                    personal=False,
                    stripped_thumb=None,
                ),
            )
        )
        service = self._service()

        with patch.object(service, "_client", return_value=client):
            ticket = await service.issue_avatar_info(account_id="123", peer_id=303)

        self.assertEqual(ticket["location_type"], "peer_photo")
        self.assertEqual(ticket["file"]["photo_id"], "505")
        self.assertEqual(
            ticket["file"]["peer"],
            {"type": "user", "id": "303", "access_hash": "404"},
        )
        self.assertEqual(ticket["cache_key"], "avatar-303-505")
        self.assertEqual(ticket["mime_type"], "image/jpeg")
        self.assertEqual(ticket["file_name"], "avatar-303.jpg")

    async def test_avatar_ticket_rejects_peer_without_photo(self):
        client, _ = self._auth_client()
        client.get_entity = AsyncMock(return_value=SimpleNamespace(photo=None))
        service = self._service()

        with patch.object(service, "_client", return_value=client):
            with self.assertRaises(TelegramPreviewError) as context:
                await service.issue_avatar_info(account_id="123", peer_id=303)

        self.assertEqual(context.exception.code, "avatar_not_found")

    async def test_avatar_ticket_uses_plain_chat_peer(self):
        client, _ = self._auth_client()
        client.get_entity = AsyncMock(
            return_value=types.Chat(
                id=404,
                title="Project Group",
                photo=types.ChatPhoto(
                    photo_id=606,
                    dc_id=5,
                    has_video=False,
                ),
                participants_count=3,
                date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                version=1,
            )
        )
        service = self._service()

        with patch.object(service, "_client", return_value=client):
            ticket = await service.issue_avatar_info(account_id="123", peer_id=404)

        self.assertEqual(ticket["location_type"], "peer_photo")
        self.assertEqual(
            ticket["file"]["peer"],
            {"type": "chat", "id": "404", "access_hash": None},
        )
        self.assertEqual(ticket["file"]["photo_id"], "606")
        self.assertEqual(ticket["cache_key"], "avatar-404-606")


class MediaLocationTests(unittest.TestCase):
    def _document(self, *, mime_type="video/mp4", file_reference=b"reference", thumbs=None):
        return types.Document(
            id=1,
            access_hash=2,
            file_reference=file_reference,
            date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            mime_type=mime_type,
            size=100,
            dc_id=2,
            attributes=[],
            thumbs=thumbs or [],
        )

    def _photo(self, *, sizes, file_reference=b"reference"):
        return types.Photo(
            id=7,
            access_hash=8,
            file_reference=file_reference,
            date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            sizes=sizes,
            dc_id=2,
        )

    def _message(self, *, document=None, photo=None, mime_type="video/mp4", name="clip.mp4"):
        return SimpleNamespace(
            id=99,
            document=document,
            photo=photo,
            file=SimpleNamespace(mime_type=mime_type, name=name),
        )

    def test_document_full_file_location(self):
        message = self._message(document=self._document())

        location, mime_type, file_name = TelegramResourceService._media_location(message, thumb=False)

        self.assertEqual(location["location_type"], "document")
        self.assertEqual(location["thumb_size"], "")
        self.assertEqual(mime_type, "video/mp4")
        self.assertEqual(file_name, "clip.mp4")

    def test_document_thumbnail_location(self):
        thumbs = [types.PhotoSize("s", 90, 90, 512), types.PhotoSize("m", 320, 240, 2048)]
        message = self._message(document=self._document(thumbs=thumbs))

        location, mime_type, file_name = TelegramResourceService._media_location(message, thumb=True)

        self.assertEqual(location["thumb_size"], "m")
        self.assertEqual(mime_type, "image/jpeg")
        self.assertEqual(file_name, "telegram-99.jpg")

    def test_document_thumbnail_missing_is_rejected(self):
        message = self._message(document=self._document(thumbs=[]))

        with self.assertRaises(TelegramPreviewError) as context:
            TelegramResourceService._media_location(message, thumb=True)

        self.assertEqual(context.exception.code, "thumbnail_not_found")

    def test_photo_full_size_location(self):
        sizes = [types.PhotoSize("m", 320, 240, 2048), types.PhotoSize("y", 1280, 960, 50_000)]
        message = self._message(photo=self._photo(sizes=sizes))

        location, mime_type, file_name = TelegramResourceService._media_location(message, thumb=False)

        self.assertEqual(location["location_type"], "photo")
        self.assertEqual(location["thumb_size"], "y")
        self.assertEqual(mime_type, "image/jpeg")

    def test_photo_thumbnail_location(self):
        sizes = [types.PhotoSize("m", 320, 240, 2048), types.PhotoSize("y", 1280, 960, 50_000)]
        message = self._message(photo=self._photo(sizes=sizes))

        location, _, _ = TelegramResourceService._media_location(message, thumb=True)

        self.assertEqual(location["thumb_size"], "m")

    def test_accepts_audio_document(self):
        message = self._message(
            document=self._document(mime_type="audio/mpeg"),
            mime_type="audio/mpeg",
            name="song.mp3",
        )

        location, mime_type, file_name = TelegramResourceService._media_location(message, thumb=False)

        self.assertEqual(mime_type, "audio/mpeg")
        self.assertEqual(file_name, "song.mp3")

    def test_rejects_message_without_media(self):
        message = self._message()

        with self.assertRaises(TelegramPreviewError) as context:
            TelegramResourceService._media_location(message, thumb=False)

        self.assertEqual(context.exception.code, "media_not_supported")

    def test_rejects_missing_file_reference(self):
        message = self._message(document=self._document(file_reference=b""))

        with self.assertRaises(TelegramPreviewError) as context:
            TelegramResourceService._media_location(message, thumb=False)

        self.assertEqual(context.exception.code, "resource_reference_missing")


if __name__ == "__main__":
    unittest.main()
