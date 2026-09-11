import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from telethon import errors
from telethon.tl import types

from backend.chat_names import ChatPeer
from backend.telegram_chats import TelegramChat, TelegramChatService, _chat_record


def _chat_ban(**flags):
    return types.ChatBannedRights(until_date=datetime(2038, 1, 1), **flags)


class ChatValidityTests(unittest.TestCase):
    def test_usable_chats_are_not_flagged(self):
        entities = [
            types.Channel(id=1, title="Channel", photo=None, date=None, access_hash=1),
            types.Channel(
                id=2,
                title="Supergroup",
                photo=None,
                date=None,
                access_hash=2,
                megagroup=True,
            ),
            types.Chat(id=3, title="Basic group", photo=None, participants_count=1, date=None, version=0),
            types.User(id=4, bot=True, username="helper_bot"),
        ]

        for entity in entities:
            with self.subTest(title=entity.title if hasattr(entity, "title") else entity.username):
                record = _chat_record(entity)
                self.assertIsNotNone(record)
                self.assertIsNone(record.invalid_reason)

    def test_deleted_user_is_flagged(self):
        record = _chat_record(types.User(id=5, bot=True, deleted=True))

        self.assertEqual(record.invalid_reason, "deleted")

    def test_deactivated_and_left_chats_are_flagged(self):
        deactivated = types.Chat(
            id=6,
            title="Gone",
            photo=None,
            participants_count=0,
            date=None,
            version=0,
            deactivated=True,
        )
        left = types.Channel(id=7, title="Left", photo=None, date=None, left=True)

        self.assertEqual(_chat_record(deactivated).invalid_reason, "deactivated")
        self.assertEqual(_chat_record(left).invalid_reason, "left")

    def test_restricted_chats_report_the_reason(self):
        blocked = types.Channel(
            id=8,
            title="Blocked",
            photo=None,
            date=None,
            banned_rights=_chat_ban(view_messages=True),
        )
        readonly = types.Channel(
            id=9,
            title="Announcements",
            photo=None,
            date=None,
            default_banned_rights=_chat_ban(send_messages=True),
        )
        admin = types.Channel(
            id=10,
            title="Announcements (admin)",
            photo=None,
            date=None,
            admin_rights=types.ChatAdminRights(other=True),
            default_banned_rights=_chat_ban(send_messages=True),
        )

        self.assertEqual(_chat_record(blocked).invalid_reason, "blocked")
        self.assertEqual(_chat_record(readonly).invalid_reason, "readonly")
        # Administrators post in announcement channels despite the member default.
        self.assertIsNone(_chat_record(admin).invalid_reason)

    def test_per_user_ban_applies_even_to_administrators(self):
        entity = types.Channel(
            id=11,
            title="Muted admin",
            photo=None,
            date=None,
            admin_rights=types.ChatAdminRights(other=True),
            banned_rights=_chat_ban(send_messages=True),
        )

        self.assertEqual(_chat_record(entity).invalid_reason, "readonly")


class ChatDirectoryTests(unittest.IsolatedAsyncioTestCase):
    def _service(self, temp_dir: str) -> TelegramChatService:
        session = Path(temp_dir) / "101" / "telegram.session"
        session.parent.mkdir(parents=True, exist_ok=True)
        session.touch()
        store = SimpleNamespace(session_name=lambda account_id: session)
        return TelegramChatService(bot_manager=None, account_store=store)

    def test_forbidden_entities_are_listed_as_blocked(self):
        channel = _chat_record(
            types.ChannelForbidden(id=9, access_hash=1, title="Banned channel", broadcast=True)
        )
        group = _chat_record(
            types.ChannelForbidden(id=10, access_hash=1, title="Banned group", megagroup=True)
        )
        basic = _chat_record(types.ChatForbidden(id=11, title="Banned chat"))

        self.assertEqual(channel.invalid_reason, "blocked")
        self.assertEqual(channel.kind, "channel")
        self.assertEqual(group.invalid_reason, "blocked")
        self.assertEqual(group.kind, "supergroup")
        self.assertEqual(basic.invalid_reason, "blocked")
        self.assertEqual(basic.kind, "group")

    def test_record_chat_refreshes_a_stored_chat(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            service.record_chat("101", types.Channel(id=9, title="Old name", photo=None, date=None))

            # A later sighting with new flags must replace the stored entry.
            service.record_chat(
                "101",
                types.Channel(id=9, title="New name", photo=None, date=None, left=True),
            )
            stored = service._known_chats("101")

            self.assertEqual([chat.title for chat in stored], ["New name"])
            self.assertEqual(stored[0].invalid_reason, "left")

    def test_record_chat_updates_flags_of_a_known_chat(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            service.record_chat("101", types.Channel(id=9, title="Stored", photo=None, date=None))
            service.record_chat(
                "101",
                types.ChannelForbidden(id=9, access_hash=1, title="Stored", broadcast=True),
            )

            stored = service._known_chats("101")

            self.assertEqual(stored[0].title, "Stored")
            self.assertEqual(stored[0].invalid_reason, "blocked")

    def test_scrubbed_accounts_are_marked_deleted(self):
        record = _chat_record(types.UserEmpty(id=4242))

        self.assertEqual(record.invalid_reason, "deleted")
        # Telegram scrubs the peer to its id, which is not a name.
        self.assertEqual(record.title, "")
        self.assertEqual(record.kind, "private")

    def test_scrubbed_peers_keep_the_cached_name_and_kind(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            service.names.merge("101", [(4242, "Helper bot", "bot")])

            record = _chat_record(
                types.UserEmpty(id=4242), known=service.names.load("101").get(4242)
            )

            self.assertEqual(record.title, "Helper bot")
            self.assertEqual(record.kind, "bot")
            self.assertEqual(record.invalid_reason, "deleted")

    def test_listing_restores_the_name_telegram_no_longer_reports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            service.names.merge("101", [(12, "Alice", "private")])

            restored = service._named("101", [_chat_record(types.UserEmpty(id=12))])

            self.assertEqual(restored[0].title, "Alice")
            self.assertEqual(restored[0].invalid_reason, "deleted")

    def test_listing_refreshes_a_cached_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            service.names.merge("101", [(9, "Old name", "channel")])

            restored = service._named(
                "101", [TelegramChat(id=9, title="New name", kind="channel")]
            )

            self.assertEqual(restored[0].title, "New name")
            self.assertEqual(
                service.names.load("101"), {9: ChatPeer(name="New name", kind="channel")}
            )

    def test_a_peer_reported_without_a_name_keeps_the_cached_one(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            service.names.merge("101", [(12, "Alice", "private")])

            service.names.merge("101", [(12, "", "bot")])

            self.assertEqual(service.names.load("101"), {12: ChatPeer(name="Alice", kind="bot")})

    async def test_referenced_chats_missing_from_telegram_are_marked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)

            async def get_entity(chat_id):
                raise errors.PeerIdInvalidError(request=None)

            listed = await service._with_referenced_chats(
                SimpleNamespace(get_entity=get_entity), [], (-100123,), {}
            )

            self.assertEqual([chat.id for chat in listed], [-100123])
            self.assertEqual(listed[0].invalid_reason, "blocked")
            self.assertEqual(listed[0].title, "")

    async def test_unresolved_references_are_not_listed_as_users(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)

            async def get_entity(chat_id):
                raise ValueError("Cannot find any entity corresponding to")

            listed = await service._with_referenced_chats(
                SimpleNamespace(get_entity=get_entity),
                [],
                (-1001234567890, -195785875, 123456789),
                {},
            )

            kinds = {chat.id: chat.kind for chat in listed}

            self.assertEqual(kinds[-1001234567890], "channel")
            self.assertEqual(kinds[-195785875], "group")
            self.assertEqual(kinds[123456789], "private")

    async def test_unresolved_references_keep_the_cached_kind(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            known = service.names.merge("101", [(-1001234567890, "Old supergroup", "supergroup")])

            async def get_entity(chat_id):
                raise errors.ChannelPrivateError(request=None)

            listed = await service._with_referenced_chats(
                SimpleNamespace(get_entity=get_entity), [], (-1001234567890,), known
            )

            self.assertEqual(listed[0].title, "Old supergroup")
            self.assertEqual(listed[0].kind, "supergroup")

    async def test_referenced_chats_are_resolved_and_kept(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)

            async def get_entity(chat_id):
                return types.ChannelForbidden(
                    id=abs(chat_id), access_hash=1, title="Banned", broadcast=True
                )

            listed = await service._with_referenced_chats(
                SimpleNamespace(get_entity=get_entity), [], (-100123,), {}
            )

            self.assertEqual(listed[0].title, "Banned")
            self.assertEqual(listed[0].invalid_reason, "blocked")

    async def test_already_listed_chats_are_not_resolved_again(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            calls = []

            async def get_entity(chat_id):
                calls.append(chat_id)
                return types.Channel(id=chat_id, title="Listed", photo=None, date=None)

            listed = await service._with_referenced_chats(
                SimpleNamespace(get_entity=get_entity),
                [TelegramChat(id=-100123, title="Listed", kind="channel")],
                (-100123,),
                {},
            )

            self.assertEqual(calls, [])
            self.assertEqual(len(listed), 1)

    def test_recording_a_scrubbed_account_keeps_the_stored_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            service.record_chat(
                "101", types.User(id=12, access_hash=1, first_name="Alice", username="alice")
            )
            service.record_chat("101", types.UserEmpty(id=12))

            stored = service._known_chats("101")

            self.assertEqual(stored[0].title, "Alice")
            self.assertEqual(stored[0].invalid_reason, "deleted")


if __name__ == "__main__":
    unittest.main()
