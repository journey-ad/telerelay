import unittest
from datetime import datetime

from telethon.tl import types

from backend.telegram_chats import _chat_record


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


if __name__ == "__main__":
    unittest.main()
