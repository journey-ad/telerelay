"""Browser-direct Telegram media authorization.

This module is deliberately separate from the existing preview download code. It
returns a short-lived, one-time control-plane ticket; Telegram file bytes never
enter this process.
"""

from __future__ import annotations

import asyncio
import base64
import os
import secrets
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

from telethon import helpers
from telethon.crypto import AES, AuthKey, Factorization, rsa
from telethon.errors import SecurityError
from telethon.extensions import BinaryReader
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged
from telethon.network.mtprotoplainsender import MTProtoPlainSender
from telethon.tl import types
from telethon.tl.functions import ReqDHParamsRequest, ReqPqMultiRequest, SetClientDHParamsRequest

from backend.logger import get_logger
from backend.telegram_accounts import TelegramAccountError
from backend.telegram_preview import TelegramPreviewError


logger = get_logger()


DC_WEB_HOSTS = {
    1: "pluto-1.web.telegram.org",
    2: "venus-1.web.telegram.org",
    3: "aurora-1.web.telegram.org",
    4: "vesta-1.web.telegram.org",
    5: "flora-1.web.telegram.org",
}


def _signed_long(value: int) -> int:
    """Normalize a Telegram long while accepting JavaScript signed values."""
    value &= (1 << 64) - 1
    return value - (1 << 64) if value >= (1 << 63) else value


def _base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _auth_key_id(auth_key: AuthKey) -> int:
    if auth_key.key_id is None:
        raise ValueError("Auth key is not initialized")
    return int(auth_key.key_id)


def encrypt_bind_auth_key_inner(
    *,
    perm_auth_key: AuthKey,
    temp_auth_key_id: int,
    session_id: int,
    expires_at: int,
    nonce: int | None = None,
    msg_id: int | None = None,
) -> bytes:
    """Encrypt ``bind_auth_key_inner`` with the permanent key using MTProto 1.0."""
    if not perm_auth_key:
        raise ValueError("Permanent auth key is empty")
    nonce = _signed_long(nonce if nonce is not None else secrets.randbits(64))
    session_id = _signed_long(session_id)
    expires = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    inner = types.BindAuthKeyInner(
        nonce=nonce,
        temp_auth_key_id=_signed_long(temp_auth_key_id),
        perm_auth_key_id=_signed_long(_auth_key_id(perm_auth_key)),
        temp_session_id=session_id,
        expires_at=expires,
    )
    body = bytes(inner)
    message_id = int(msg_id if msg_id is not None else (time.time() * (1 << 32))) & ~3
    plaintext = os.urandom(16) + struct.pack("<qii", message_id, 0, len(body)) + body
    msg_key = sha1(plaintext).digest()[4:20]

    key = bytes(perm_auth_key.key)
    sha_a = sha1(msg_key + key[0:32]).digest()
    sha_b = sha1(key[32:48] + msg_key + key[48:64]).digest()
    sha_c = sha1(key[64:96] + msg_key).digest()
    sha_d = sha1(msg_key + key[96:128]).digest()
    aes_key = sha_a[:8] + sha_b[8:20] + sha_c[4:16]
    aes_iv = sha_a[8:20] + sha_b[:8] + sha_c[16:20] + sha_d[:8]
    padding = os.urandom((-len(plaintext)) % 16)
    encrypted = AES.encrypt_ige(plaintext + padding, aes_key, aes_iv)
    return struct.pack("<Q", _auth_key_id(perm_auth_key)) + msg_key + encrypted


def build_bind_temp_auth_key_proof(
    *,
    temp_auth_key: AuthKey,
    perm_auth_key: AuthKey,
    session_id: int,
    expires_at: int,
    nonce: int | None = None,
    msg_id: int | None = None,
) -> dict[str, Any]:
    """Build the values the temporary-key client sends in ``auth.bindTempAuthKey``."""
    bind_nonce = _signed_long(nonce if nonce is not None else secrets.randbits(64))
    message_id = int(msg_id if msg_id is not None else (time.time() * (1 << 32))) & ~3
    encrypted = encrypt_bind_auth_key_inner(
        perm_auth_key=perm_auth_key,
        temp_auth_key_id=_auth_key_id(temp_auth_key),
        session_id=session_id,
        expires_at=expires_at,
        nonce=bind_nonce,
        msg_id=message_id,
    )
    return {
        "perm_auth_key_id": str(_signed_long(_auth_key_id(perm_auth_key))),
        "nonce": str(bind_nonce),
        "expires_at": expires_at,
        "message_id": str(message_id),
        "encrypted_message": _base64(encrypted),
    }


async def _do_temp_authentication(sender: Any, *, dc_id: int, expires_in: int) -> tuple[AuthKey, int, int]:
    """Run MTProto DH auth with ``p_q_inner_data_temp_dc``.

    Telethon exposes the normal permanent-key handshake only. This is the same
    algorithm with Telegram's temporary constructor and the DC id included.
    """
    nonce = int.from_bytes(os.urandom(16), "big", signed=True)
    logger.debug("Telegram temporary auth requesting PQ (dc_id=%s)", dc_id)
    res_pq = await sender.send(ReqPqMultiRequest(nonce))
    if not isinstance(res_pq, types.ResPQ) or res_pq.nonce != nonce:
        raise SecurityError("Temporary auth step 1 failed")

    pq = int.from_bytes(res_pq.pq, "big", signed=True)
    logger.debug("Telegram temporary auth factorizing PQ (dc_id=%s)", dc_id)
    p, q = await asyncio.to_thread(Factorization.factorize, pq)
    p_bytes, q_bytes = rsa.get_byte_array(p), rsa.get_byte_array(q)
    new_nonce = int.from_bytes(os.urandom(32), "little", signed=True)
    inner = bytes(
        types.PQInnerDataTempDc(
            pq=rsa.get_byte_array(pq),
            p=p_bytes,
            q=q_bytes,
            nonce=res_pq.nonce,
            server_nonce=res_pq.server_nonce,
            new_nonce=new_nonce,
            dc=dc_id,
            expires_in=expires_in,
        )
    )

    encrypted = None
    fingerprint = None
    for candidate in res_pq.server_public_key_fingerprints:
        encrypted = rsa.encrypt(candidate, inner)
        if encrypted is not None:
            fingerprint = candidate
            break
    if encrypted is None or fingerprint is None:
        for candidate in res_pq.server_public_key_fingerprints:
            encrypted = rsa.encrypt(candidate, inner, use_old=True)
            if encrypted is not None:
                fingerprint = candidate
                break
    if encrypted is None or fingerprint is None:
        raise SecurityError("Temporary auth has no usable Telegram RSA key")

    logger.debug("Telegram temporary auth requesting DH params (dc_id=%s)", dc_id)
    dh_params = await sender.send(
        ReqDHParamsRequest(
            nonce=res_pq.nonce,
            server_nonce=res_pq.server_nonce,
            p=p_bytes,
            q=q_bytes,
            public_key_fingerprint=fingerprint,
            encrypted_data=encrypted,
        )
    )
    if not isinstance(dh_params, types.ServerDHParamsOk):
        raise SecurityError("Temporary auth step 2 failed")
    if dh_params.nonce != res_pq.nonce or dh_params.server_nonce != res_pq.server_nonce:
        raise SecurityError("Temporary auth nonce mismatch")

    key, iv = helpers.generate_key_data_from_nonce(res_pq.server_nonce, new_nonce)
    if len(dh_params.encrypted_answer) % 16:
        raise SecurityError("Temporary auth DH answer is not block aligned")
    plaintext = AES.decrypt_ige(dh_params.encrypted_answer, key, iv)
    with BinaryReader(plaintext) as reader:
        reader.read(20)
        dh_inner = reader.tgread_object()
    if not isinstance(dh_inner, types.ServerDHInnerData):
        raise SecurityError("Temporary auth DH inner data is invalid")
    if dh_inner.nonce != res_pq.nonce or dh_inner.server_nonce != res_pq.server_nonce:
        raise SecurityError("Temporary auth DH inner nonce mismatch")

    dh_prime = int.from_bytes(dh_inner.dh_prime, "big", signed=False)
    g = dh_inner.g
    g_a = int.from_bytes(dh_inner.g_a, "big", signed=False)
    if not (1 < g < dh_prime - 1 and 1 < g_a < dh_prime - 1):
        raise SecurityError("Temporary auth DH parameters are invalid")
    b = int.from_bytes(os.urandom(256), "big", signed=False)
    g_b = pow(g, b, dh_prime)
    if not (1 < g_b < dh_prime - 1):
        raise SecurityError("Temporary auth DH public value is invalid")
    client_inner = bytes(
        types.ClientDHInnerData(
            nonce=res_pq.nonce,
            server_nonce=res_pq.server_nonce,
            retry_id=0,
            g_b=rsa.get_byte_array(g_b),
        )
    )
    logger.debug("Telegram temporary auth setting client DH params (dc_id=%s)", dc_id)
    dh_gen = await sender.send(
        SetClientDHParamsRequest(
            nonce=res_pq.nonce,
            server_nonce=res_pq.server_nonce,
            encrypted_data=AES.encrypt_ige(sha1(client_inner).digest() + client_inner, key, iv),
        )
    )
    nonce_types = (types.DhGenOk, types.DhGenRetry, types.DhGenFail)
    if not isinstance(dh_gen, nonce_types):
        raise SecurityError("Temporary auth step 3 failed")
    auth_key = AuthKey(rsa.get_byte_array(pow(g_a, b, dh_prime)))
    nonce_number = 1 + nonce_types.index(type(dh_gen))
    expected_hash = auth_key.calc_new_nonce_hash(new_nonce, nonce_number)
    if getattr(dh_gen, f"new_nonce_hash{nonce_number}") != expected_hash:
        raise SecurityError("Temporary auth new nonce hash mismatch")
    if not isinstance(dh_gen, types.DhGenOk):
        raise SecurityError("Temporary auth key generation was retried")

    new_nonce_bytes = new_nonce.to_bytes(32, "little", signed=True)
    server_nonce_bytes = res_pq.server_nonce.to_bytes(16, "little", signed=True)
    server_salt_bytes = bytes(a ^ b for a, b in zip(new_nonce_bytes[:8], server_nonce_bytes[:8]))
    server_salt = int.from_bytes(server_salt_bytes, "little", signed=True)
    logger.debug("Telegram temporary auth key created (dc_id=%s)", dc_id)
    return auth_key, server_salt, dh_inner.server_time - int(time.time())


@dataclass
class _MediaTicket:
    ticket_id: str
    account_id: str
    dc_id: int
    auth_key: bytes
    server_salt: int
    perm_auth_key_id: int
    file: dict[str, Any]
    mime_type: str
    file_name: str
    size: int | None
    bind_expires_at: int
    auth_expires_at: int
    created_at: float
    bound: bool = False


class TelegramMediaService:
    """Issue and bind one-time browser-direct video tickets in memory."""

    BIND_TICKET_TTL_SECONDS = 90
    AUTH_KEY_TTL_SECONDS = 30 * 60
    MAX_TICKET_COUNT = 128

    def __init__(self, bot_manager: Any, account_store: Any, config: Any):
        self.bot_manager = bot_manager
        self.account_store = account_store
        self.config = config
        self._tickets: dict[str, _MediaTicket] = {}
        self._lock = asyncio.Lock()

    def _active_account(self, account_id: str | None) -> str:
        target = account_id or self.account_store.active_account_id
        try:
            self.account_store.get_public(target)
        except TelegramAccountError as exc:
            raise TelegramPreviewError("account_not_found", "Telegram account does not exist") from exc
        return target

    def _client(self, account_id: str):
        target = self._active_account(account_id)
        try:
            runtime = self.bot_manager.get_runtime(target)
        except TelegramAccountError as exc:
            raise TelegramPreviewError(exc.code, str(exc)) from exc
        manager = runtime.client_manager
        client = manager.get_client() if manager else None
        if not runtime.is_connected or client is None:
            raise TelegramPreviewError("telegram_not_connected", "The requested Telegram account is not connected")
        return client

    async def _prune(self) -> None:
        now = time.time()
        async with self._lock:
            for key, ticket in list(self._tickets.items()):
                if ticket.bind_expires_at <= now or ticket.bound:
                    self._tickets.pop(key, None)
            if len(self._tickets) > self.MAX_TICKET_COUNT:
                oldest = sorted(self._tickets, key=lambda key: self._tickets[key].created_at)
                for key in oldest[: len(self._tickets) - self.MAX_TICKET_COUNT]:
                    self._tickets.pop(key, None)

    async def _message(self, client: Any, chat_id: int, message_id: int):
        try:
            message = await client.get_messages(chat_id, ids=message_id)
        except Exception as exc:
            raise TelegramPreviewError("message_not_found", "Telegram message was not found") from exc
        if message is None:
            raise TelegramPreviewError("message_not_found", "Telegram message was not found")
        return message

    @staticmethod
    def _video_file(message: Any) -> tuple[types.Document, Any]:
        document = getattr(message, "document", None)
        media_file = getattr(message, "file", None)
        mime_type = str(getattr(media_file, "mime_type", "") or "")
        if not isinstance(document, types.Document) or not mime_type.startswith("video/"):
            raise TelegramPreviewError("video_not_supported", "Message does not contain a playable video")
        if not document.file_reference:
            raise TelegramPreviewError("video_reference_missing", "Telegram video reference is unavailable")
        return document, media_file

    async def _new_temp_key(self, client: Any, dc_id: int) -> tuple[bytes, int, int]:
        """Generate an unbound auth key and learn the server salt for its DC."""
        dc = await client._get_dc(dc_id)
        connection = ConnectionTcpAbridged(
            dc.ip_address,
            dc.port,
            dc.id,
            loggers=client._log,
            proxy=client._proxy,
            local_addr=client._local_addr,
        )
        try:
            async with asyncio.timeout(15):
                await connection.connect()
                plain = MTProtoPlainSender(connection, loggers=client._log)
                auth_key, server_salt, _ = await _do_temp_authentication(
                    plain,
                    dc_id=dc_id,
                    expires_in=self.AUTH_KEY_TTL_SECONDS,
                )
            return bytes(auth_key.key), server_salt, _auth_key_id(auth_key)
        finally:
            await connection.disconnect()

    @staticmethod
    async def _permanent_sender(client: Any, dc_id: int) -> tuple[Any, bool]:
        """Return an authorized sender for the target DC and whether it was borrowed."""
        if int(client.session.dc_id) == dc_id:
            sender = client._sender
            if sender is None or not sender.auth_key:
                raise RuntimeError("Telegram client has no active permanent auth key")
            return sender, False
        return await client._borrow_exported_sender(dc_id), True

    @staticmethod
    async def _return_permanent_sender(client: Any, sender: Any, borrowed: bool) -> None:
        if not borrowed:
            return
        return_sender = getattr(client, "_return_exported_sender", None)
        if return_sender is not None:
            await return_sender(sender)

    async def issue_video_ticket(
        self,
        *,
        account_id: str,
        chat_id: int,
        message_id: int,
    ) -> dict[str, Any]:
        await self._prune()
        client = self._client(account_id)
        message = await self._message(client, chat_id, message_id)
        document, media_file = self._video_file(message)
        dc_id = int(document.dc_id)
        if dc_id not in DC_WEB_HOSTS:
            raise TelegramPreviewError("video_dc_unsupported", "Telegram video DC is not supported")
        api_id = self.config.api_id
        if not api_id or not self.config.api_hash:
            raise TelegramPreviewError("telegram_api_credentials_missing", "Telegram API credentials are not configured")

        # Borrowing an exported sender creates the permanent authorization key
        # on a media DC without copying the account's main session to the page.
        permanent_sender = None
        permanent_sender_borrowed = False
        stage = "select_permanent_sender"
        try:
            permanent_sender, permanent_sender_borrowed = await self._permanent_sender(client, dc_id)
            perm_auth_key_id = _auth_key_id(permanent_sender.auth_key)
            stage = "create_temporary_auth_key"
            temp_key, server_salt, temp_key_id = await self._new_temp_key(client, dc_id)
        except TelegramPreviewError:
            raise
        except Exception as exc:
            logger.exception(
                "Telegram video ticket preparation failed "
                "(account_id=%s, chat_id=%s, message_id=%s, dc_id=%s, stage=%s, error_type=%s)",
                account_id,
                chat_id,
                message_id,
                dc_id,
                stage,
                type(exc).__name__,
            )
            raise TelegramPreviewError("video_ticket_failed", "Telegram could not prepare video access") from exc
        finally:
            if permanent_sender is not None:
                await self._return_permanent_sender(client, permanent_sender, permanent_sender_borrowed)

        now = int(time.time())
        bind_expires_at = now + self.BIND_TICKET_TTL_SECONDS
        auth_expires_at = now + self.AUTH_KEY_TTL_SECONDS
        document_location = {
            "id": str(document.id),
            "access_hash": str(document.access_hash),
            "file_reference": _base64(bytes(document.file_reference)),
            "dc_id": dc_id,
            "size": int(getattr(document, "size", 0) or getattr(media_file, "size", 0) or 0),
        }
        ticket = _MediaTicket(
            ticket_id=secrets.token_urlsafe(32),
            account_id=account_id,
            dc_id=dc_id,
            auth_key=temp_key,
            server_salt=server_salt,
            perm_auth_key_id=perm_auth_key_id,
            file=document_location,
            mime_type=str(getattr(media_file, "mime_type", "video/mp4") or "video/mp4"),
            file_name=str(getattr(media_file, "name", None) or f"telegram-{chat_id}-{message_id}.mp4"),
            size=document_location["size"] or None,
            bind_expires_at=bind_expires_at,
            auth_expires_at=auth_expires_at,
            created_at=time.time(),
        )
        async with self._lock:
            self._tickets[ticket.ticket_id] = ticket
        return {
            "ticket": ticket.ticket_id,
            "api_id": api_id,
            "dc_id": dc_id,
            "dc_address": DC_WEB_HOSTS[dc_id],
            "dc_port": 443,
            "auth_key": _base64(temp_key),
            "auth_key_id": str(temp_key_id),
            "server_salt": str(server_salt),
            "expires_at": auth_expires_at,
            "file": document_location,
            "mime_type": ticket.mime_type,
            "file_name": ticket.file_name,
            "size": ticket.size,
        }

    async def bind_video_ticket(self, *, account_id: str, ticket_id: str, session_id: int) -> dict[str, Any]:
        await self._prune()
        async with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None:
                raise TelegramPreviewError("video_ticket_expired", "Video authorization has expired")
            if ticket.account_id != account_id:
                raise TelegramPreviewError("video_ticket_invalid", "Video authorization does not belong to this account")
            if ticket.bound:
                raise TelegramPreviewError("video_ticket_used", "Video authorization was already used")
            if ticket.bind_expires_at <= time.time():
                self._tickets.pop(ticket_id, None)
                raise TelegramPreviewError("video_ticket_expired", "Video authorization has expired")
            ticket.bound = True

        client = self._client(account_id)
        permanent_sender = None
        permanent_sender_borrowed = False
        logger.debug(
            "Binding Telegram temporary video auth key (account_id=%s, dc_id=%s)",
            account_id,
            ticket.dc_id,
        )
        try:
            permanent_sender, permanent_sender_borrowed = await self._permanent_sender(client, ticket.dc_id)
            perm_auth_key = permanent_sender.auth_key
            if _auth_key_id(perm_auth_key) != ticket.perm_auth_key_id:
                raise RuntimeError("Telegram permanent auth key changed")
            proof = build_bind_temp_auth_key_proof(
                temp_auth_key=AuthKey(ticket.auth_key),
                perm_auth_key=perm_auth_key,
                session_id=session_id,
                expires_at=ticket.auth_expires_at,
            )
        except Exception as exc:
            logger.exception(
                "Telegram temporary video auth key binding failed "
                "(account_id=%s, dc_id=%s, error_type=%s)",
                account_id,
                ticket.dc_id,
                type(exc).__name__,
            )
            async with self._lock:
                self._tickets.pop(ticket_id, None)
            raise TelegramPreviewError("video_bind_failed", "Telegram could not bind video authorization") from exc
        finally:
            if permanent_sender is not None:
                await self._return_permanent_sender(client, permanent_sender, permanent_sender_borrowed)

        async with self._lock:
            self._tickets.pop(ticket_id, None)
        logger.debug(
            "Telegram temporary video auth key proof issued (account_id=%s, dc_id=%s)",
            account_id,
            ticket.dc_id,
        )
        return proof

    async def clear_account(self, account_id: str) -> None:
        async with self._lock:
            for key, ticket in list(self._tickets.items()):
                if ticket.account_id == account_id:
                    self._tickets.pop(key, None)
