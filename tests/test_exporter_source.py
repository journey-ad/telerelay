import unittest
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


if __name__ == "__main__":
    unittest.main()
