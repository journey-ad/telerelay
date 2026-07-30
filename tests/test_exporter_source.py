import unittest
from types import SimpleNamespace

from backend.exporter.source import TelegramExportSource
from telethon.tl import types


class FakeClient:
    def __init__(self, entities):
        self.entities = entities

    async def iter_dialogs(self):
        for entity in self.entities:
            yield SimpleNamespace(entity=entity)


class TelegramExportSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_summaries_include_bots_but_not_private_users(self):
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

        result = await TelegramExportSource(None)._list_chat_summaries(
            FakeClient([user, bot, channel])
        )

        self.assertEqual([item.title for item in result], ["Alert Bot", "News"])
        self.assertEqual(result[0].kind, "bot")
        self.assertEqual(result[0].username, "alert_bot")


if __name__ == "__main__":
    unittest.main()
