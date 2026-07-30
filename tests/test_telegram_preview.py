import unittest
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.events import EventBus
from backend.telegram_preview import TelegramPreviewError, TelegramPreviewService
from telethon.tl import types


def entity(peer_id, name, **values):
    return SimpleNamespace(id=peer_id, title=name, first_name=None, **values)


def sender(peer_id, name, username=None):
    return SimpleNamespace(
        id=peer_id,
        title=None,
        first_name=name,
        last_name=None,
        username=username,
        bot=False,
    )


def message(message_id, chat_id, text, author, *, reply_to=None, grouped_id=None):
    created = datetime(2026, 7, 30, 8, tzinfo=timezone.utc) + timedelta(
        minutes=message_id
    )
    return SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        date=created,
        raw_text=text,
        text=text,
        sender=author,
        sender_id=author.id,
        reply_to_msg_id=reply_to,
        grouped_id=grouped_id,
        out=False,
        media=None,
        action=None,
        photo=None,
        document=None,
        file=None,
        forward=None,
        fwd_from=None,
        edit_date=None,
        post_author=None,
        views=None,
        reactions=None,
    )


class FakeDialog:
    def __init__(self, peer, last_message, *, archived=False, pinned=False):
        self.entity = peer
        self.message = last_message
        self.folder_id = 1 if archived else None
        self.pinned = pinned
        self.unread_count = 2
        self.unread_mentions_count = 1


class FakeClient:
    def __init__(self):
        alice = sender(11, "Alice", "alice")
        self.chat = entity(101, "项目群", megagroup=True, broadcast=False, username="project")
        self.archive = entity(202, "通知频道", megagroup=False, broadcast=True, username=None)
        self.messages = {
            101: [
                message(1, 101, "原始消息", alice),
                message(2, 101, "needle reply", alice, reply_to=1),
                message(3, 101, "最近消息", alice),
            ],
            202: [message(4, 202, "归档消息", alice)],
        }
        self.dialogs = [
            FakeDialog(self.chat, self.messages[101][-1], pinned=True),
            FakeDialog(self.archive, self.messages[202][-1], archived=True),
        ]
        self.calls = []

    async def get_input_entity(self, peer_id):
        self.calls.append(("get_input_entity", peer_id))
        return peer_id

    async def get_entity(self, peer_id):
        self.calls.append(("get_entity", peer_id))
        for candidate in (self.chat, self.archive):
            if candidate.id == peer_id:
                return candidate
        raise ValueError("missing")

    async def iter_dialogs(self, **options):
        self.calls.append(("iter_dialogs", options))
        archived = options.get("archived", False)
        values = [item for item in self.dialogs if (item.folder_id == 1) == archived]
        for item in values[: options["limit"]]:
            yield item

    async def iter_messages(self, peer, **options):
        self.calls.append(("iter_messages", options))
        values = sorted(self.messages[peer.id], key=lambda item: item.id, reverse=True)
        if options.get("max_id"):
            values = [item for item in values if item.id < options["max_id"]]
        if options.get("search"):
            needle = options["search"].casefold()
            values = [item for item in values if needle in item.text.casefold()]
        for item in values[: options["limit"]]:
            yield item

    async def get_messages(self, peer, ids):
        self.calls.append(("get_messages", ids))
        values = self.messages[peer.id if hasattr(peer, "id") else peer]
        if isinstance(ids, (list, tuple)):
            by_id = {item.id: item for item in values}
            return [by_id.get(item_id) for item_id in ids]
        return next((item for item in values if item.id == ids), None)


class TelegramPreviewServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.client = FakeClient()
        manager = SimpleNamespace(get_client=lambda: self.client)
        bot = SimpleNamespace(is_connected=True, client_manager=manager)
        store = SimpleNamespace(active_account_id="work", data_dir=self.temp_dir.name)
        self.events = EventBus()
        self.service = TelegramPreviewService(bot, store, self.events)

    async def test_lists_main_and_archived_dialogs(self):
        main = await self.service.list_dialogs(
            account_id="work", folder="main", limit=40, cursor=None
        )
        archived = await self.service.list_dialogs(
            account_id="work", folder="archived", limit=40, cursor=None
        )

        self.assertEqual([item["title"] for item in main["items"]], ["项目群"])
        self.assertEqual(main["items"][0]["kind"], "supergroup")
        self.assertTrue(main["items"][0]["pinned"])
        self.assertEqual([item["title"] for item in archived["items"]], ["通知频道"])

    async def test_message_history_search_and_reply_are_read_only(self):
        result = await self.service.list_messages(
            account_id="work",
            chat_id=101,
            limit=20,
            before_id=None,
            query="needle",
        )

        self.assertEqual([item["id"] for item in result["items"]], [2])
        self.assertEqual(result["items"][0]["reply_to"]["text"], "原始消息")
        self.assertEqual(result["items"][0]["sender"]["name"], "Alice")
        self.assertNotIn(
            "send_read_acknowledge",
            [name for name, _ in self.client.calls],
        )
        self.assertNotIn("send_message", [name for name, _ in self.client.calls])

    async def test_history_page_is_returned_in_chronological_order(self):
        result = await self.service.list_messages(
            account_id="work",
            chat_id=101,
            limit=2,
            before_id=None,
            query=None,
        )

        self.assertEqual([item["id"] for item in result["items"]], [2, 3])
        self.assertEqual(result["next_before_id"], 2)

    async def test_get_message_loads_an_exact_message_without_read_ack(self):
        result = await self.service.get_message(
            account_id="work",
            chat_id=101,
            message_id=1,
        )

        self.assertEqual(result["id"], 1)
        self.assertEqual(result["text"], "原始消息")
        self.assertIn(("get_messages", 1), self.client.calls)
        self.assertNotIn(
            "send_read_acknowledge",
            [name for name, _ in self.client.calls],
        )

    async def test_rejects_requests_for_an_inactive_account(self):
        with self.assertRaises(TelegramPreviewError) as raised:
            await self.service.list_dialogs(
                account_id="personal", folder="main", limit=40, cursor=None
            )

        self.assertEqual(raised.exception.code, "inactive_account")

    async def test_live_event_contains_account_and_message_without_read_ack(self):
        current = self.client.messages[101][-1]
        event = SimpleNamespace(
            message=current,
            chat_id=101,
            sender=current.sender,
        )
        queue = __import__("asyncio").Queue()
        self.events._subscribers.add(queue)
        self.addCleanup(self.events._subscribers.discard, queue)

        await self.service.handle_new_message(event)

        emitted = queue.get_nowait()
        self.assertEqual(emitted["type"], "telegram-preview-message")
        self.assertEqual(emitted["payload"]["account_id"], "work")
        self.assertEqual(emitted["payload"]["message"]["id"], 3)
        self.assertNotIn(
            "send_read_acknowledge",
            [name for name, _ in self.client.calls],
        )

    async def test_inline_thumbnail_uses_embedded_telegram_bytes(self):
        media_message = self.client.messages[101][-1]
        media_message.media = object()
        media_message.photo = SimpleNamespace(
            sizes=[types.PhotoCachedSize("m", 20, 20, b"cached-jpeg")]
        )

        data = await self.service._message_data(media_message, 101)

        self.assertTrue(data["media"]["inline_thumbnail"].startswith("data:image/jpeg;base64,"))

    async def test_photo_media_uses_largest_dimensions(self):
        media_message = self.client.messages[101][-1]
        media_message.media = object()
        media_message.photo = SimpleNamespace(
            sizes=[
                types.PhotoSize("m", 320, 180, 1_000),
                types.PhotoSize("x", 1920, 1080, 20_000),
            ]
        )

        data = await self.service._message_data(media_message, 101)

        self.assertEqual(data["media"]["width"], 1920)
        self.assertEqual(data["media"]["height"], 1080)

    async def test_avatar_cache_avoids_repeated_telegram_download(self):
        self.client.downloads = 0

        async def download_profile_photo(entity, **options):
            self.client.downloads += 1
            return b"avatar"

        self.client.download_profile_photo = download_profile_photo

        first = await self.service.avatar(account_id="work", peer_id=101)
        second = await self.service.avatar(account_id="work", peer_id=101)

        self.assertEqual(first, b"avatar")
        self.assertEqual(second, b"avatar")
        self.assertEqual(self.client.downloads, 1)


if __name__ == "__main__":
    unittest.main()
