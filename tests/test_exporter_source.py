import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.telegram_chats import TelegramChatService
from telethon import errors
from telethon.tl import types


class FakeClient:
    def __init__(self, entities):
        self.entities = entities

    async def iter_dialogs(self):
        for entity in self.entities:
            yield SimpleNamespace(entity=entity)


class MissingChatClient:
    async def get_entity(self, _chat_id):
        raise errors.PeerIdInvalidError(None)


class BotStore:
    def __init__(self, root):
        self.root = Path(root)

    def get_public(self, account_id):
        return {"id": account_id, "kind": "bot"}

    def session_name(self, account_id):
        return self.root / str(account_id) / "telegram"


class TelegramChatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_chats_returns_structured_supported_chats(self):
        bot = types.User(
            id=11,
            bot=True,
            access_hash=111,
            first_name="Alert Bot",
            username="alert_bot",
        )
        user = types.User(id=12, access_hash=112, first_name="Alice")
        channel = types.Channel(
            id=13,
            title="News",
            photo=types.ChatPhotoEmpty(),
            date=None,
            broadcast=True,
        )

        result = await TelegramChatService(None, None)._list_chats(FakeClient([user, bot, channel]))

        self.assertEqual([item.title for item in result], ["Alert Bot", "News"])
        self.assertEqual([item.id for item in result], [11, -1000000000013])
        self.assertEqual(result[0].kind, "bot")
        self.assertEqual(result[0].username, "alert_bot")
        self.assertEqual(result[1].kind, "channel")
        self.assertIsNone(result[1].username)

    async def test_get_chat_maps_telegram_lookup_errors_to_missing(self):
        result = await TelegramChatService(None, None)._get_chat(MissingChatClient(), -1001)

        self.assertIsNone(result)

    async def test_bot_accounts_list_recorded_known_chats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = TelegramChatService(None, BotStore(Path(temp_dir)))
            group = types.Chat(
                id=21,
                title="转发群",
                photo=types.ChatPhotoEmpty(),
                participants_count=0,
                date=None,
                version=0,
            )
            channel = types.Channel(
                id=22,
                title="通知频道",
                photo=types.ChatPhotoEmpty(),
                date=None,
                broadcast=True,
            )

            self.assertEqual(service.list_chats("123"), [])
            service.record_chat("123", group)
            service.record_chat("123", channel)

            result = service.list_chats("123")

            self.assertEqual([item.title for item in result], ["转发群", "通知频道"])
            self.assertEqual([item.kind for item in result], ["group", "channel"])

    async def test_bot_known_chats_include_private_users(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = TelegramChatService(None, BotStore(Path(temp_dir)))
            user = types.User(
                id=12,
                access_hash=112,
                first_name="Alice",
                username="alice",
            )

            service.record_chat("123", user)

            result = service.list_chats("123")
            self.assertEqual([item.title for item in result], ["Alice"])
            self.assertEqual(result[0].kind, "private")
            self.assertEqual(result[0].username, "alice")

    async def test_known_chats_are_deduplicated_and_capped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = TelegramChatService(None, BotStore(Path(temp_dir)))
            service.MAX_KNOWN_CHATS = 5
            group = types.Chat(
                id=21,
                title="转发群",
                photo=types.ChatPhotoEmpty(),
                participants_count=0,
                date=None,
                version=0,
            )
            service.record_chat("123", group)
            service.record_chat("123", group)

            self.assertEqual(len(service.list_chats("123")), 1)

            for chat_id in range(100, 110):
                service.record_chat(
                    "123",
                    types.Chat(
                        id=chat_id,
                        title=f"群 {chat_id}",
                        photo=types.ChatPhotoEmpty(),
                        participants_count=0,
                        date=None,
                        version=0,
                    ),
                )

            result = service.list_chats("123")
            self.assertEqual(len(result), 5)
            self.assertEqual(
                [chat.id for chat in result],
                [-105, -106, -107, -108, -109],
            )


if __name__ == "__main__":
    unittest.main()
