import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from telethon.errors import ChatWriteForbiddenError, FloodWaitError
from telethon.tl import functions, types

from backend.telegram_preview import TelegramPreviewError, TelegramPreviewService


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


def fake_message(message_id, chat_id, text, author, *, reply_to=None, grouped_id=None):
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
        self.current_user = sender(99, "Current User", "current")
        self.chat = entity(101, "项目群", megagroup=True, broadcast=False, username="project")
        self.archive = entity(202, "通知频道", megagroup=False, broadcast=True, username=None)
        self.remote_bot = entity(
            303,
            "发布助手",
            bot=True,
            username="release_helper_bot",
        )
        self.messages = {
            101: [
                fake_message(1, 101, "原始消息", alice),
                fake_message(2, 101, "needle reply", alice, reply_to=1),
                fake_message(3, 101, "最近消息", alice),
            ],
            202: [fake_message(4, 202, "归档消息", alice)],
        }
        self.dialogs = [
            FakeDialog(self.chat, self.messages[101][-1], pinned=True),
            FakeDialog(self.archive, self.messages[202][-1], archived=True),
        ]
        self.calls = []
        self.event_handlers = []
        self.connected = True
        self.connect_calls = 0
        self.disconnect_during_next_dialog_load = False

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connect_calls += 1
        self.connected = True

    async def get_input_entity(self, peer_id):
        self.calls.append(("get_input_entity", peer_id))
        if peer_id == self.remote_bot.id:
            return types.InputPeerUser(user_id=peer_id, access_hash=1)
        return peer_id

    async def get_entity(self, peer_id):
        self.calls.append(("get_entity", peer_id))
        for candidate in (self.chat, self.archive, self.remote_bot):
            if candidate.id == peer_id:
                return candidate
        raise ValueError("missing")

    async def get_entities(self, peer_ids):
        self.calls.append(("get_entities", peer_ids))
        return [sender(peer_id, f"用户{peer_id}") for peer_id in peer_ids]

    async def iter_dialogs(self, **options):
        self.calls.append(("iter_dialogs", options))
        if self.disconnect_during_next_dialog_load:
            self.disconnect_during_next_dialog_load = False
            self.connected = False
            raise ConnectionError("Cannot send requests while disconnected")
        archived = options.get("archived", False)
        values = [item for item in self.dialogs if (item.folder_id == 1) == archived]
        if archived and not options.get("ignore_pinned"):
            values = [
                item for item in self.dialogs if item.pinned and item.folder_id != 1
            ] + values
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

    async def send_message(self, peer, message, **options):
        self.calls.append(
            (
                "send_message",
                {"peer_id": peer.id, "message": message, **options},
            )
        )
        sent = fake_message(5, peer.id, message, self.current_user)
        sent.out = True
        self.messages[peer.id].append(sent)
        return sent

    async def __call__(self, request):
        self.calls.append(("request", request))
        if isinstance(request, functions.bots.GetBotInfoRequest):
            return types.BotInfo(
                commands=[
                    types.BotCommand("start", "开始使用"),
                    types.BotCommand("status", "查看状态"),
                ]
            )
        raise AssertionError(f"unexpected request: {request!r}")

    def add_event_handler(self, callback, event):
        self.event_handlers.append((callback, event))

    def remove_event_handler(self, callback, event):
        self.event_handlers.remove((callback, event))


def preview_dependencies(client, data_dir):
    manager = SimpleNamespace(get_client=lambda: client)
    runtime = SimpleNamespace(is_connected=True, client_manager=manager)
    registry = SimpleNamespace(get_runtime=lambda account_id: runtime)
    store = SimpleNamespace(
        active_account_id="work",
        data_dir=data_dir,
        get_public=lambda account_id: {"id": account_id},
    )
    return registry, store


class TelegramPreviewServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.client = FakeClient()
        registry, store = preview_dependencies(self.client, self.temp_dir.name)
        self.service = TelegramPreviewService(registry, store)

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

    async def test_dialog_list_reconnects_a_stale_client(self):
        self.client.connected = False

        result = await self.service.list_dialogs(
            account_id="work", folder="main", limit=40, cursor=None
        )

        self.assertEqual([item["title"] for item in result["items"]], ["项目群"])
        self.assertEqual(self.client.connect_calls, 1)

    async def test_dialog_list_recovers_when_transport_drops_during_request(self):
        self.client.disconnect_during_next_dialog_load = True

        result = await self.service.list_dialogs(
            account_id="work", folder="main", limit=40, cursor=None
        )

        self.assertEqual([item["title"] for item in result["items"]], ["项目群"])
        self.assertEqual(self.client.connect_calls, 1)

    async def test_dialog_list_reports_unavailable_when_reconnect_fails(self):
        self.client.connected = False

        async def fail_connect():
            self.client.connect_calls += 1
            raise ConnectionError("offline")

        self.client.connect = fail_connect

        with self.assertRaisesRegex(TelegramPreviewError, "not connected") as raised:
            await self.service.list_dialogs(
                account_id="work", folder="main", limit=40, cursor=None
            )

        self.assertEqual(raised.exception.code, "telegram_not_connected")
        self.assertEqual(self.client.connect_calls, 1)

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

    async def test_send_text_message_disables_formatting_and_link_previews(self):
        result = await self.service.send_text_message(
            account_id="work",
            chat_id=101,
            text="literal **text** https://example.com",
        )

        self.assertEqual(result["text"], "literal **text** https://example.com")
        self.assertTrue(result["outgoing"])
        self.assertIn(
            (
                "send_message",
                {
                    "peer_id": 101,
                    "message": "literal **text** https://example.com",
                    "parse_mode": None,
                    "link_preview": False,
                },
            ),
            self.client.calls,
        )

    async def test_send_text_message_wraps_telegram_failures(self):
        async def fail_send(*args, **kwargs):
            raise RuntimeError("write forbidden")

        self.client.send_message = fail_send

        with self.assertRaises(TelegramPreviewError) as raised:
            await self.service.send_text_message(
                account_id="work",
                chat_id=101,
                text="hello",
            )

        self.assertEqual(raised.exception.code, "message_send_failed")

    async def test_send_text_message_classifies_flood_wait(self):
        async def fail_send(*args, **kwargs):
            raise FloodWaitError(None, 5)

        self.client.send_message = fail_send

        with self.assertRaises(TelegramPreviewError) as raised:
            await self.service.send_text_message(
                account_id="work",
                chat_id=101,
                text="hello",
            )

        self.assertEqual(raised.exception.code, "flood_wait")
        self.assertIn("5", str(raised.exception))

    async def test_send_text_message_classifies_write_forbidden(self):
        async def fail_send(*args, **kwargs):
            raise ChatWriteForbiddenError(None)

        self.client.send_message = fail_send

        with self.assertRaises(TelegramPreviewError) as raised:
            await self.service.send_text_message(
                account_id="work",
                chat_id=101,
                text="hello",
            )

        self.assertEqual(raised.exception.code, "chat_write_forbidden")

    async def test_lists_commands_from_the_remote_bot_dialog(self):
        result = await self.service.list_bot_commands(
            account_id="work",
            chat_id=303,
        )

        self.assertEqual(
            result,
            {
                "account_id": "work",
                "chat_id": 303,
                "items": [
                    {"command": "start", "description": "开始使用"},
                    {"command": "status", "description": "查看状态"},
                ],
            },
        )
        request = next(
            value for name, value in self.client.calls if name == "request"
        )
        self.assertIsInstance(request, functions.bots.GetBotInfoRequest)
        self.assertEqual(request.bot.user_id, 303)

    async def test_non_bot_dialog_has_no_bot_commands(self):
        result = await self.service.list_bot_commands(
            account_id="work",
            chat_id=101,
        )

        self.assertEqual(result["items"], [])
        self.assertNotIn("request", [name for name, _ in self.client.calls])

    async def test_preview_update_stream_registers_and_removes_handler(self):
        stream = await self.service.stream_updates(account_id="work")

        self.assertIn("event: ready", await anext(stream))
        callback, event_builder = self.client.event_handlers[0]
        await callback(SimpleNamespace(chat_id=303, message=SimpleNamespace(id=17)))
        update = await anext(stream)

        self.assertIn('"chat_id": 303', update)
        self.assertIn('"message_id": 17', update)
        await stream.aclose()
        self.assertEqual(self.client.event_handlers, [])
        self.assertIsNotNone(event_builder)

    async def test_preview_update_stream_ends_when_account_disconnects(self):
        self.service.PREVIEW_STREAM_KEEPALIVE = 0.05
        runtime = self.service.bot_manager.get_runtime("work")
        stream = await self.service.stream_updates(account_id="work")

        self.assertIn("event: ready", await anext(stream))
        runtime.is_connected = False

        with self.assertRaises(StopAsyncIteration):
            await anext(stream)
        self.assertEqual(self.client.event_handlers, [])

    async def test_preview_update_stream_ends_when_client_is_replaced(self):
        self.service.PREVIEW_STREAM_KEEPALIVE = 0.05
        runtime = self.service.bot_manager.get_runtime("work")
        stream = await self.service.stream_updates(account_id="work")

        self.assertIn("event: ready", await anext(stream))
        runtime.client_manager.get_client = lambda: object()

        with self.assertRaises(StopAsyncIteration):
            await anext(stream)
        self.assertEqual(self.client.event_handlers, [])

    async def test_explicit_account_id_is_not_limited_to_active_selection(self):
        result = await self.service.list_dialogs(
            account_id="personal", folder="main", limit=40, cursor=None
        )

        self.assertEqual(result["account_id"], "personal")
        self.assertEqual([item["title"] for item in result["items"]], ["项目群"])

    async def test_inline_thumbnail_uses_embedded_telegram_bytes(self):
        media_message = self.client.messages[101][-1]
        media_message.media = object()
        media_message.photo = SimpleNamespace(
            sizes=[types.PhotoCachedSize("m", 20, 20, b"cached-jpeg")]
        )

        data = await self.service._message_data(media_message, 101)

        self.assertTrue(data["media"]["inline_thumbnail"].startswith("data:image/jpeg;base64,"))

    async def test_url_entities_are_serialized(self):
        media_message = self.client.messages[101][-1]
        media_message.entities = [
            types.MessageEntityUrl(offset=0, length=13),
            types.MessageEntityTextUrl(offset=14, length=6, url="https://example.com"),
        ]

        data = await self.service._message_data(media_message, 101)

        self.assertEqual(
            data["entities"],
            [
                {"type": "url", "offset": 0, "length": 13, "url": None},
                {"type": "url", "offset": 14, "length": 6, "url": "https://example.com"},
            ],
        )

        media_message.entities = None
        data = await self.service._message_data(media_message, 101)
        self.assertIsNone(data["entities"])

    async def test_service_message_serializes_action_details(self):
        service_message = self.client.messages[101][-1]

        service_message.action = SimpleNamespace(
            users=[sender(11, "Alice"), sender(12, "Bob")],
            title=None,
        )
        data = await self.service._message_data(service_message, 101)
        self.assertEqual(data["service_action"], "SimpleNamespace")
        self.assertEqual(data["service_details"]["user_names"], ["Alice", "Bob"])

        service_message.action = SimpleNamespace(users=None, user_ids=[11], title="新群名")
        service_message.client = self.client
        data = await self.service._message_data(service_message, 101)
        self.assertEqual(data["service_details"]["user_names"], ["用户11"])
        self.assertEqual(data["service_details"]["title"], "新群名")

        service_message.action = SimpleNamespace(users=None, user_ids=[13])
        service_message.client = None
        data = await self.service._message_data(service_message, 101)
        self.assertEqual(data["service_details"]["user_names"], ["13"])

        service_message.action = SimpleNamespace(users=None, user_ids=None, user_id=None)
        data = await self.service._message_data(service_message, 101)
        self.assertEqual(data["service_details"]["user_names"], ["Alice"])

        service_message.action = None
        data = await self.service._message_data(service_message, 101)
        self.assertIsNone(data["service_action"])
        self.assertIsNone(data["service_details"])

    async def test_poll_serializes_question_options_and_results(self):
        media_message = self.client.messages[101][-1]
        media_message.media = types.MessageMediaPoll(
            poll=types.Poll(
                id=42,
                question=types.TextWithEntities("选择发布窗口", []),
                answers=[
                    types.PollAnswer(types.TextWithEntities("上午", []), b"morning"),
                    types.PollAnswer(types.TextWithEntities("晚上", []), b"evening"),
                ],
                multiple_choice=True,
                quiz=True,
                closed=True,
            ),
            results=types.PollResults(
                results=[
                    types.PollAnswerVoters(b"evening", 3, chosen=True, correct=True),
                    types.PollAnswerVoters(b"morning", 1),
                ],
                total_voters=4,
                solution="晚间活跃度更高",
            ),
        )

        data = await self.service._message_data(media_message, 101)

        poll = data["media"]["poll"]
        self.assertEqual(data["media"]["type"], "poll")
        self.assertEqual(poll["question"], "选择发布窗口")
        self.assertEqual([item["text"] for item in poll["options"]], ["上午", "晚上"])
        self.assertEqual([item["voters"] for item in poll["options"]], [1, 3])
        self.assertTrue(poll["options"][1]["chosen"])
        self.assertTrue(poll["options"][1]["correct"])
        self.assertEqual(poll["total_voters"], 4)
        self.assertTrue(poll["multiple_choice"])
        self.assertTrue(poll["quiz"])
        self.assertTrue(poll["closed"])
        self.assertEqual(poll["solution"], "晚间活跃度更高")
        self.assertEqual(
            (await self.service._message_summary(media_message, 101))["preview"],
            "选择发布窗口",
        )

    async def test_poll_without_public_results_keeps_options_visible(self):
        media_message = self.client.messages[101][-1]
        media_message.media = types.MessageMediaPoll(
            poll=types.Poll(
                id=43,
                question=types.TextWithEntities("今天吃什么？", []),
                answers=[types.PollAnswer(types.TextWithEntities("面", []), b"noodle")],
            ),
            results=types.PollResults(total_voters=12),
        )

        data = await self.service._message_data(media_message, 101)

        poll = data["media"]["poll"]
        self.assertEqual(poll["options"][0]["text"], "面")
        self.assertFalse(poll["results_visible"])
        self.assertEqual(poll["total_voters"], 12)

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
        self.assertTrue(data["media"]["is_visual_media"])

    async def test_image_without_thumbnail_is_downloadable_but_not_previewed(self):
        media_message = self.client.messages[101][-1]
        media_message.media = object()
        media_message.document = SimpleNamespace(thumbs=[])
        media_message.file = SimpleNamespace(
            name="scan.png",
            mime_type="image/png",
            size=10 * 1024 * 1024,
            duration=None,
        )

        data = await self.service._message_data(media_message, 101)

        self.assertTrue(data["media"]["is_visual_media"])
        self.assertFalse(data["media"]["has_thumbnail"])

    async def test_audio_with_cover_has_thumbnail(self):
        media_message = self.client.messages[101][-1]
        media_message.media = object()
        media_message.audio = object()
        media_message.voice = None
        media_message.video = None
        media_message.document = SimpleNamespace(
            thumbs=[types.PhotoSize("m", 300, 300, 2048)]
        )
        media_message.file = SimpleNamespace(
            name="song.mp3",
            mime_type="audio/mpeg",
            size=3 * 1024 * 1024,
            duration=185,
        )

        data = await self.service._message_data(media_message, 101)

        self.assertEqual(data["media"]["type"], "audio")
        self.assertTrue(data["media"]["has_thumbnail"])
        self.assertEqual(data["media"]["duration"], 185)

    async def test_webpage_media_takes_priority_over_exposed_photo(self):
        media_message = self.client.messages[101][-1]
        media_message.media = types.MessageMediaWebPage(
            webpage=types.WebPage(
                id=1,
                url="https://example.com/articles/preview",
                display_url="example.com/articles/preview",
                hash=0,
                type="article",
                site_name="Example News",
                title="Telegram link previews",
                description="Metadata supplied by Telegram.",
                author="Example Author",
            )
        )
        # Telethon exposes a webpage cover as message.photo.
        media_message.photo = SimpleNamespace(
            sizes=[types.PhotoSize("m", 640, 360, 10_000)]
        )

        data = await self.service._message_data(media_message, 101)

        self.assertEqual(data["media"]["type"], "webpage")
        self.assertFalse(data["media"]["is_visual_media"])
        self.assertTrue(data["media"]["has_thumbnail"])
        self.assertEqual(
            data["media"]["webpage"],
            {
                "url": "https://example.com/articles/preview",
                "display_url": "example.com/articles/preview",
                "site_name": "Example News",
                "title": "Telegram link previews",
                "description": "Metadata supplied by Telegram.",
                "author": "Example Author",
                "type": "article",
            },
        )

    async def test_pending_and_empty_webpages_have_safe_metadata(self):
        media_message = self.client.messages[101][-1]
        for webpage in (
            types.WebPagePending(
                id=2,
                date=datetime(2026, 7, 30, tzinfo=timezone.utc),
                url="https://pending.example/",
            ),
            types.WebPageEmpty(id=3, url="https://empty.example/"),
        ):
            with self.subTest(webpage=type(webpage).__name__):
                media_message.media = types.MessageMediaWebPage(webpage=webpage)
                media_message.photo = None

                data = await self.service._message_data(media_message, 101)

                self.assertEqual(data["media"]["type"], "webpage")
                self.assertEqual(data["media"]["webpage"]["url"], webpage.url)
                self.assertIsNone(data["media"]["webpage"]["title"])
                self.assertFalse(data["media"]["has_thumbnail"])


if __name__ == "__main__":
    unittest.main()
