import unittest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

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
        self.service = TelegramPreviewService(bot, store)

    async def test_first_cache_key_creation_discards_plaintext_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "telegram_preview_cache" / "account" / "avatar.jpg"
            cache_file.parent.mkdir(parents=True)
            cache_file.write_bytes(b"plaintext")
            manager = SimpleNamespace(get_client=lambda: self.client)
            bot = SimpleNamespace(is_connected=True, client_manager=manager)
            store = SimpleNamespace(active_account_id="work", data_dir=temp_dir)

            service = TelegramPreviewService(bot, store)

            self.assertFalse(service.cache_root.exists())
            self.assertEqual(len(service.cache_key_path.read_bytes()), service.CACHE_KEY_BYTES)
            self.assertEqual(service.cache_key_path.stat().st_mode & 0o777, 0o600)

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

    async def test_inline_thumbnail_uses_embedded_telegram_bytes(self):
        media_message = self.client.messages[101][-1]
        media_message.media = object()
        media_message.photo = SimpleNamespace(
            sizes=[types.PhotoCachedSize("m", 20, 20, b"cached-jpeg")]
        )

        data = await self.service._message_data(media_message, 101)

        self.assertTrue(data["media"]["inline_thumbnail"].startswith("data:image/jpeg;base64,"))

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
            self.service._message_summary(media_message, 101)["preview"],
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

    async def test_gif_and_sticker_thumbnails_use_encrypted_cache(self):
        for kind in ("gif", "sticker"):
            with self.subTest(kind=kind):
                media_message = self.client.messages[101][-1]
                media_message.media = object()
                media_message.photo = None
                media_message.document = SimpleNamespace(
                    thumbs=[types.PhotoSize("m", 320, 320, 1_000)]
                )
                media_message.file = SimpleNamespace(
                    name=f"media-{kind}",
                    mime_type="video/mp4" if kind == "gif" else "application/x-tgsticker",
                    size=1024,
                    duration=None,
                )
                media_message.gif = kind == "gif"
                media_message.sticker = kind == "sticker"
                downloads = 0

                async def download_media(message, *, file, thumb=None, **options):
                    nonlocal downloads
                    downloads += 1
                    self.assertIs(file, bytes)
                    self.assertIsNotNone(thumb)
                    return f"{kind}-thumbnail".encode()

                self.client.download_media = download_media
                cache_path = self.service._cache_path(
                    "work", "thumbnails", "101-3.jpg"
                )
                cache_path.unlink(missing_ok=True)

                data = await self.service._message_data(media_message, 101)
                first, _ = await self.service.media_thumbnail(
                    account_id="work", chat_id=101, message_id=3
                )
                second, _ = await self.service.media_thumbnail(
                    account_id="work", chat_id=101, message_id=3
                )

                self.assertEqual(data["media"]["type"], "animation" if kind == "gif" else "sticker")
                self.assertTrue(data["media"]["is_visual_media"])
                self.assertTrue(data["media"]["has_thumbnail"])
                self.assertEqual(first, f"{kind}-thumbnail".encode())
                self.assertEqual(second, first)
                self.assertEqual(downloads, 1)
                stored = cache_path.read_bytes()
                self.assertTrue(stored.startswith(self.service.CACHE_MAGIC))
                self.assertNotIn(first, stored)

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
        cache_path = self.service._cache_path("work", "avatars", "101.jpg")
        stored = cache_path.read_bytes()
        self.assertTrue(stored.startswith(self.service.CACHE_MAGIC))
        self.assertNotIn(b"avatar", stored)

    async def test_plaintext_cache_is_rejected_and_reloaded(self):
        cache_path = self.service._cache_path("work", "avatars", "101.jpg")
        cache_path.parent.mkdir(parents=True)
        cache_path.write_bytes(b"legacy-avatar")

        async def download_profile_photo(entity, **options):
            return b"fresh-avatar"

        self.client.download_profile_photo = download_profile_photo

        content = await self.service.avatar(account_id="work", peer_id=101)

        self.assertEqual(content, b"fresh-avatar")
        self.assertTrue(cache_path.read_bytes().startswith(self.service.CACHE_MAGIC))
        self.assertNotIn(b"legacy-avatar", cache_path.read_bytes())

    async def test_image_download_uses_temporary_file_without_cache(self):
        media_message = self.client.messages[101][-1]
        media_message.media = object()
        media_message.photo = SimpleNamespace(sizes=[])
        media_message.file = SimpleNamespace(
            name="photo.jpg",
            mime_type="image/jpeg",
            size=50 * 1024 * 1024,
            duration=None,
        )

        async def download_media(message, *, file, **options):
            Path(file).write_bytes(b"full-image")
            return file

        self.client.download_media = download_media

        path, media_type, filename = await self.service.download_visual_media(
            account_id="work",
            chat_id=101,
            message_id=3,
        )
        self.addCleanup(path.unlink, missing_ok=True)

        self.assertEqual(path.read_bytes(), b"full-image")
        self.assertEqual(media_type, "image/jpeg")
        self.assertEqual(filename, "photo.jpg")
        self.assertFalse(self.service.cache_root.exists())

    async def test_gif_and_sticker_files_can_be_downloaded_without_persistent_cache(self):
        for kind in ("gif", "sticker"):
            with self.subTest(kind=kind):
                media_message = self.client.messages[101][-1]
                media_message.media = object()
                media_message.photo = None
                media_message.document = SimpleNamespace(thumbs=[])
                media_message.file = SimpleNamespace(
                    name=f"media-{kind}",
                    mime_type="video/mp4" if kind == "gif" else "application/x-tgsticker",
                    size=1024,
                    duration=None,
                )
                media_message.gif = kind == "gif"
                media_message.sticker = kind == "sticker"

                async def download_media(message, *, file, **options):
                    Path(file).write_bytes(f"full-{kind}".encode())
                    return file

                self.client.download_media = download_media

                path, _, filename = await self.service.download_visual_media(
                    account_id="work", chat_id=101, message_id=3
                )
                self.addCleanup(path.unlink, missing_ok=True)

                self.assertEqual(path.read_bytes(), f"full-{kind}".encode())
                self.assertTrue(filename.startswith(f"media-{kind}"))
                self.assertFalse(self.service.cache_root.exists())

    async def test_non_visual_media_is_not_downloaded(self):
        media_message = self.client.messages[101][-1]
        media_message.media = object()
        media_message.document = object()
        media_message.file = SimpleNamespace(
            name="video.mp4",
            mime_type="video/mp4",
            size=500 * 1024 * 1024,
            duration=120,
        )
        downloads = 0

        async def download_media(message, *, file, **options):
            nonlocal downloads
            downloads += 1
            return file

        self.client.download_media = download_media

        with self.assertRaises(TelegramPreviewError) as raised:
            await self.service.download_visual_media(
                account_id="work",
                chat_id=101,
                message_id=3,
            )

        self.assertEqual(raised.exception.code, "visual_media_not_found")
        self.assertEqual(downloads, 0)
        self.assertFalse(self.service.cache_root.exists())


if __name__ == "__main__":
    unittest.main()
