import struct
import unittest
import base64
from datetime import datetime, timezone
from hashlib import sha1
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telethon.crypto import AuthKey
from telethon.tl import types

from backend.telegram_media import (
    TelegramMediaService,
    _MediaTicket,
    build_bind_temp_auth_key_proof,
    encrypt_bind_auth_key_inner,
)


class TelegramMediaCryptoTests(unittest.TestCase):
    def test_bind_payload_uses_permanent_key_mtproto_v1(self):
        perm_auth_key = AuthKey(bytes(range(256)))
        temp_auth_key = AuthKey(bytes(reversed(range(256))))
        payload = encrypt_bind_auth_key_inner(
            perm_auth_key=perm_auth_key,
            temp_auth_key_id=temp_auth_key.key_id,
            session_id=-(1 << 62),
            expires_at=2_000_000_000,
            nonce=11,
            msg_id=13,
        )

        self.assertEqual(struct.unpack("<Q", payload[:8])[0], perm_auth_key.key_id)
        self.assertEqual(len(payload[8:]) % 16, 0)
        self.assertGreaterEqual(len(payload), 24 + 16)

        msg_key = payload[8:24]
        from telethon.crypto import AES
        from telethon.extensions import BinaryReader

        key = perm_auth_key.key
        sha_a = sha1(msg_key + key[:32]).digest()
        sha_b = sha1(key[32:48] + msg_key + key[48:64]).digest()
        sha_c = sha1(key[64:96] + msg_key).digest()
        sha_d = sha1(msg_key + key[96:128]).digest()
        aes_key = sha_a[:8] + sha_b[8:20] + sha_c[4:16]
        aes_iv = sha_a[8:20] + sha_b[:8] + sha_c[16:20] + sha_d[:8]
        plain = AES.decrypt_ige(payload[24:], aes_key, aes_iv)
        with BinaryReader(plain) as reader:
            reader.read(16)
            self.assertEqual(reader.read_long(), 12)
            reader.read_int()
            length = reader.read_int()
            body = reader.read(length)
        self.assertEqual(msg_key, sha1(plain[: 32 + length]).digest()[4:20])
        self.assertEqual(body[:4], struct.pack("<i", types.BindAuthKeyInner.CONSTRUCTOR_ID))
        parsed = types.BindAuthKeyInner.from_reader(BinaryReader(body[4:]))
        self.assertEqual(parsed.nonce, 11)
        self.assertEqual(parsed.temp_auth_key_id, temp_auth_key.key_id)
        self.assertEqual(parsed.perm_auth_key_id, perm_auth_key.key_id - (1 << 64))
        self.assertEqual(parsed.temp_session_id, -(1 << 62))
        self.assertEqual(parsed.expires_at, datetime.fromtimestamp(2_000_000_000, timezone.utc))

    def test_bind_proof_reuses_nonce_and_message_id(self):
        perm_auth_key = AuthKey(bytes(range(256)))
        temp_auth_key = AuthKey(bytes(reversed(range(256))))
        proof = build_bind_temp_auth_key_proof(
            temp_auth_key=temp_auth_key,
            perm_auth_key=perm_auth_key,
            session_id=17,
            expires_at=2_000_000_000,
            nonce=31,
            msg_id=37,
        )

        self.assertEqual(proof["nonce"], "31")
        self.assertEqual(proof["message_id"], "36")
        signed_perm_key_id = perm_auth_key.key_id - (1 << 64)
        self.assertEqual(proof["perm_auth_key_id"], str(signed_perm_key_id))
        encrypted = base64.urlsafe_b64decode(proof["encrypted_message"] + "==")
        msg_key = encrypted[8:24]
        from telethon.crypto import AES
        from telethon.extensions import BinaryReader

        key = perm_auth_key.key
        sha_a = sha1(msg_key + key[:32]).digest()
        sha_b = sha1(key[32:48] + msg_key + key[48:64]).digest()
        sha_c = sha1(key[64:96] + msg_key).digest()
        sha_d = sha1(msg_key + key[96:128]).digest()
        aes_key = sha_a[:8] + sha_b[8:20] + sha_c[4:16]
        aes_iv = sha_a[8:20] + sha_b[:8] + sha_c[16:20] + sha_d[:8]
        plain = AES.decrypt_ige(encrypted[24:], aes_key, aes_iv)
        with BinaryReader(plain) as reader:
            reader.read(16)
            self.assertEqual(reader.read_long(), 36)
            reader.read_int()
            length = reader.read_int()
            body = reader.read(length)
        parsed = types.BindAuthKeyInner.from_reader(BinaryReader(body[4:]))
        self.assertEqual(parsed.nonce, 31)


class TelegramMediaSenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_prune_uses_short_bind_deadline_not_auth_key_deadline(self):
        service = TelegramMediaService(None, None, None)
        service._tickets["expired"] = _MediaTicket(
            ticket_id="expired",
            account_id="123",
            dc_id=5,
            auth_key=b"key",
            server_salt=1,
            perm_auth_key_id=2,
            file={},
            mime_type="video/mp4",
            file_name="video.mp4",
            size=100,
            bind_expires_at=0,
            auth_expires_at=2_000_000_000,
            created_at=0,
        )

        await service._prune()

        self.assertNotIn("expired", service._tickets)
        self.assertEqual(service.BIND_TICKET_TTL_SECONDS, 90)
        self.assertEqual(service.AUTH_KEY_TTL_SECONDS, 30 * 60)

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


if __name__ == "__main__":
    unittest.main()
