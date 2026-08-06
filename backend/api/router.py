"""Versioned REST and SSE API."""

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask

from backend.api.dependencies import bind_account_scope, get_context, require_auth
from backend.application import ApplicationContext
from backend.client import TelegramClientManager
from backend.exporter.service import ExportError
from backend.meta import REPOSITORY_URL, check_update, current_commit, current_version
from backend.schemas import (
    ApiMessage,
    AuthValue,
    BotTokenPayload,
    ButtonActionRulePayload,
    ConfigPayload,
    ExportTaskPayload,
    ForwardingRulePayload,
    GroupExportRequest,
    MessageExportRequest,
    RegexValidateRequest,
    TelegramAccountCreate,
    TelegramAccountUpdate,
    TelegramChatResponse,
    TelegramTextMessageRequest,
    TogglePayload,
    config_json_schema,
    config_validation_message,
    validate_config,
)
from backend.services import ServiceError, validate_regex_patterns
from backend.telegram_accounts import TelegramAccountError
from backend.telegram_chats import TelegramChatError
from backend.telegram_preview import TelegramPreviewError

router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_auth), Depends(bind_account_scope)],
)

StatsDateLimit = Literal["7day", "14day", "30day", "all"]
STATS_DATE_LIMIT_DAYS: dict[StatsDateLimit, int | None] = {
    "7day": 7,
    "14day": 14,
    "30day": 30,
    "all": None,
}


def _error(code: str, message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _dataclass(value: Any) -> dict[str, Any]:
    return asdict(value)


@router.get("/session")
async def session(context: ApplicationContext = Depends(get_context)) -> dict:
    return {
        "authenticated": True,
        "auth_required": bool(
            context.config.web_auth_username and context.config.web_auth_password
        ),
        "language": context.config.language,
        "active_account_id": (
            context.accounts.store.active_account_id if context.accounts else None
        ),
    }


def _accounts(context: ApplicationContext):
    if not context.accounts:
        raise _error("not_user_mode", "Telegram accounts are only available in user mode", 409)
    return context.accounts


def _telegram_preview(context: ApplicationContext):
    if not context.telegram_preview:
        raise _error(
            "not_user_mode",
            "Telegram preview is only available in user mode",
            409,
        )
    return context.telegram_preview


def _telegram_chats(context: ApplicationContext):
    if not context.telegram_chats:
        raise _error(
            "not_user_mode",
            "Telegram chats are only available in user mode",
            409,
        )
    return context.telegram_chats


def _telegram_media(context: ApplicationContext):
    if not context.telegram_media:
        raise _error(
            "not_user_mode",
            "Direct Telegram media preview is only available in user mode",
            409,
        )
    return context.telegram_media


def _account_scope(context: ApplicationContext):
    try:
        return context.scope_for()
    except ValueError as exc:
        raise _error("account_not_authenticated", str(exc), 409) from exc


def _active_rules(context: ApplicationContext):
    scope = _account_scope(context)
    return scope.rules if scope else context.rules


def _active_stats(context: ApplicationContext):
    scope = _account_scope(context)
    if scope:
        return scope.stats
    from backend.stats_db import get_stats_db

    return get_stats_db()


def _active_exports(context: ApplicationContext):
    scope = _account_scope(context)
    return scope.exports if scope else context.exports


def _active_scheduler(context: ApplicationContext):
    scope = _account_scope(context)
    return scope.scheduler if scope else context.scheduler


def _active_config(context: ApplicationContext):
    scope = _account_scope(context)
    return scope.config if scope else context.config


def _selected_account_id(context: ApplicationContext) -> str:
    try:
        account_id = context.selected_account_id()
    except ValueError as exc:
        raise _error("account_not_found", str(exc), 404) from exc
    if account_id is None:
        raise _error("not_user_mode", "Telegram accounts are only available in user mode", 409)
    return account_id


def _event_visible_to_account(event: dict, account_id: str | None) -> bool:
    """Keep account-tagged runtime events inside one request-bound account."""
    if account_id is None:
        return True
    payload = event.get("payload") or {}
    event_account_ids = {
        str(value)
        for value in (
            payload.get("account_id"),
            payload.get("id"),
            payload.get("previous_account_id"),
        )
        if value is not None
    }
    if not event_account_ids:
        return True
    return account_id in event_account_ids


def _telegram_chat_error(exc: TelegramChatError) -> HTTPException:
    status = {
        "account_not_found": 404,
        "account_unavailable": 409,
        "chat_not_found": 404,
        "telegram_not_connected": 409,
        "telegram_timeout": 504,
    }.get(exc.code, 409)
    return _error(exc.code, str(exc), status)


def _preview_error(exc: TelegramPreviewError) -> HTTPException:
    status = {
        "avatar_not_found": 404,
        "account_not_found": 404,
        "account_unavailable": 409,
        "chat_not_found": 404,
        "visual_media_not_found": 404,
        "message_not_found": 404,
        "thumbnail_not_found": 404,
        "invalid_cursor": 422,
        "flood_wait": 429,
        "chat_write_forbidden": 403,
        "bot_commands_unavailable": 502,
        "message_send_failed": 502,
        "visual_media_download_failed": 502,
        "video_not_supported": 415,
        "video_reference_missing": 409,
        "video_dc_unsupported": 409,
        "telegram_api_credentials_missing": 503,
        "video_ticket_failed": 502,
    }.get(exc.code, 409)
    return _error(exc.code, str(exc), status)


def _image_response(
    content: bytes,
    media_type: str,
    request: Request,
) -> Response:
    import hashlib

    etag = f'"{hashlib.blake2s(content, digest_size=12).hexdigest()}"'
    headers = {
        "Cache-Control": "private, max-age=3600, stale-while-revalidate=86400",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/telegram-accounts")
async def list_telegram_accounts(
    context: ApplicationContext = Depends(get_context),
) -> list[dict]:
    return _accounts(context).list_accounts()


@router.get("/telegram-accounts/{account_id}/avatar")
async def telegram_account_avatar(
    account_id: str,
    context: ApplicationContext = Depends(get_context),
) -> FileResponse:
    try:
        avatar_path = _accounts(context).store.get_avatar_path(account_id)
    except TelegramAccountError as exc:
        raise _error(exc.code, str(exc), 404) from exc
    if avatar_path is None:
        raise _error("avatar_not_found", "Telegram account avatar does not exist", 404)
    return FileResponse(
        avatar_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/telegram-accounts/{account_id}/refresh")
async def refresh_telegram_account(
    account_id: str,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _accounts(context).refresh_identity(account_id)
    except TelegramAccountError as exc:
        status_code = 404 if exc.code == "account_not_found" else 409
        raise _error(exc.code, str(exc), status_code) from exc


@router.get(
    "/telegram-accounts/{account_id}/chats",
    response_model=list[TelegramChatResponse],
)
async def telegram_account_chats(
    account_id: str,
    context: ApplicationContext = Depends(get_context),
) -> list[dict]:
    try:
        chats = await asyncio.to_thread(_telegram_chats(context).list_chats, account_id)
        return [chat.to_dict() for chat in chats]
    except TelegramChatError as exc:
        raise _telegram_chat_error(exc) from exc


@router.get("/telegram-preview/dialogs")
async def telegram_preview_dialogs(
    folder: str = Query("main", pattern="^(main|archived)$"),
    limit: int = Query(40, ge=1, le=100),
    cursor: str | None = None,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _telegram_preview(context).list_dialogs(
            account_id=_selected_account_id(context),
            folder=folder,
            limit=limit,
            cursor=cursor,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.get("/telegram-preview/chats/{chat_id}/messages")
async def telegram_preview_messages(
    chat_id: int,
    limit: int = Query(40, ge=1, le=100),
    before_id: int | None = Query(None, ge=1),
    query: str | None = Query(None, max_length=200),
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _telegram_preview(context).list_messages(
            account_id=_selected_account_id(context),
            chat_id=chat_id,
            limit=limit,
            before_id=before_id,
            query=(query or "").strip() or None,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.post("/telegram-preview/chats/{chat_id}/messages", status_code=201)
async def telegram_preview_send_message(
    chat_id: int,
    payload: TelegramTextMessageRequest,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _telegram_preview(context).send_text_message(
            account_id=_selected_account_id(context),
            chat_id=chat_id,
            text=payload.text,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.get("/telegram-preview/chats/{chat_id}/bot-commands")
async def telegram_preview_bot_commands(
    chat_id: int,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _telegram_preview(context).list_bot_commands(
            account_id=_selected_account_id(context),
            chat_id=chat_id,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.get("/telegram-preview/updates")
async def telegram_preview_updates(
    context: ApplicationContext = Depends(get_context),
) -> StreamingResponse:
    try:
        updates = await _telegram_preview(context).stream_updates(
            account_id=_selected_account_id(context),
        )
        return StreamingResponse(
            updates,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.get("/telegram-preview/chats/{chat_id}/messages/{message_id}")
async def telegram_preview_message(
    chat_id: int,
    message_id: int,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _telegram_preview(context).get_message(
            account_id=_selected_account_id(context),
            chat_id=chat_id,
            message_id=message_id,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.post("/telegram-preview/chats/{chat_id}/messages/{message_id}/video-ticket")
async def telegram_preview_video_ticket(
    chat_id: int,
    message_id: int,
    response: Response,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        ticket = await _telegram_media(context).issue_video_ticket(
            account_id=_selected_account_id(context),
            chat_id=chat_id,
            message_id=message_id,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return ticket
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.get("/telegram-preview/peers/{peer_id}/avatar")
async def telegram_preview_avatar(
    peer_id: int,
    request: Request,
    context: ApplicationContext = Depends(get_context),
) -> Response:
    try:
        content = await _telegram_preview(context).avatar(
            account_id=_selected_account_id(context),
            peer_id=peer_id,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc
    return _image_response(content, "image/jpeg", request)


@router.get("/telegram-preview/chats/{chat_id}/messages/{message_id}/thumbnail")
async def telegram_preview_thumbnail(
    chat_id: int,
    message_id: int,
    request: Request,
    context: ApplicationContext = Depends(get_context),
) -> Response:
    try:
        content, media_type = await _telegram_preview(context).media_thumbnail(
            account_id=_selected_account_id(context),
            chat_id=chat_id,
            message_id=message_id,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc
    return _image_response(content, media_type, request)


@router.get("/telegram-preview/chats/{chat_id}/messages/{message_id}/visual-media")
async def telegram_preview_visual_media(
    chat_id: int,
    message_id: int,
    context: ApplicationContext = Depends(get_context),
) -> FileResponse:
    try:
        path, media_type, filename = await _telegram_preview(context).download_visual_media(
            account_id=_selected_account_id(context),
            chat_id=chat_id,
            message_id=message_id,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@router.post("/telegram-accounts", status_code=201)
async def create_telegram_account(
    payload: TelegramAccountCreate,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        account = await _accounts(context).create(
            payload.label,
            kind=payload.kind,
            bot_token=payload.bot_token,
        )
    except TelegramAccountError as exc:
        raise _error(exc.code, str(exc), 409) from exc
    context.events.publish("telegram-account", {"action": "create", "id": account["id"]})
    return account


@router.put("/telegram-accounts/{account_id}")
async def update_telegram_account(
    account_id: str,
    payload: TelegramAccountUpdate,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        account = await _accounts(context).rename(account_id, payload.label)
    except TelegramAccountError as exc:
        status_code = 404 if exc.code == "account_not_found" else 409
        raise _error(exc.code, str(exc), status_code) from exc
    context.events.publish("telegram-account", {"action": "rename", "id": account_id})
    return account


@router.put("/telegram-accounts/{account_id}/bot-token", response_model=ApiMessage)
async def update_telegram_bot_token(
    account_id: str,
    payload: BotTokenPayload,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        await _accounts(context).update_bot_token(account_id, payload.bot_token)
    except TelegramAccountError as exc:
        status_code = 404 if exc.code == "account_not_found" else 400
        raise _error(exc.code, str(exc), status_code) from exc
    context.events.publish("telegram-account", {"action": "token-updated", "id": account_id})
    return ApiMessage(code="bot_token_updated")


@router.post("/telegram-accounts/{account_id}/activate")
async def activate_telegram_account(
    account_id: str,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        account = await _accounts(context).activate(account_id)
    except TelegramAccountError as exc:
        raise _error(exc.code, str(exc), 404) from exc
    context.events.publish("telegram-account", {"action": "activate", "id": account_id})
    return account


@router.delete("/telegram-accounts/{account_id}", response_model=ApiMessage)
async def delete_telegram_account(
    account_id: str,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        await _accounts(context).delete(account_id)
    except TelegramAccountError as exc:
        status_code = 409 if exc.code == "last_account" else 404
        raise _error(exc.code, str(exc), status_code) from exc
    if context.telegram_preview:
        await context.telegram_preview.clear_account_cache(account_id)
    context.events.publish("telegram-account", {"action": "delete", "id": account_id})
    return ApiMessage(code="telegram_account_deleted")


@router.get("/meta")
async def meta() -> dict:
    return {
        "version": current_version(),
        "commit": await asyncio.to_thread(current_commit),
        "repository": REPOSITORY_URL,
    }


@router.get("/update-check")
async def update_check() -> dict:
    return (await asyncio.to_thread(check_update)).to_dict()


@router.get("/bot/status")
async def bot_status(context: ApplicationContext = Depends(get_context)) -> dict:
    scope = _account_scope(context)
    if scope:
        return await asyncio.to_thread(context.bot.get_status, scope.account_id)
    return await asyncio.to_thread(context.bot.get_status)


@router.get("/queue/items")
async def queue_items(
    limit: int = Query(50, ge=1, le=100),
    context: ApplicationContext = Depends(get_context),
) -> list[dict]:
    scope = _account_scope(context)
    if scope:
        return await asyncio.to_thread(context.bot.list_queue_items, limit, scope.account_id)
    return await asyncio.to_thread(context.bot.list_queue_items, limit)


@router.post("/bot/start", response_model=ApiMessage)
async def bot_start(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    scope = _account_scope(context)
    config = scope.config if scope else context.config
    valid, message = config.validate(
        bot_token=getattr(scope.runtime, "bot_token", None) if scope else None
    )
    if not valid:
        raise _error("invalid_config", message, 422)
    started = (
        await context.bot.start_account(scope.account_id)
        if scope
        else await context.bot.start()
    )
    if not started:
        raise _error("already_running", "Telegram runtime is already running", 409)
    context.events.publish(
        "bot",
        {"action": "start", "account_id": scope.account_id if scope else None},
    )
    return ApiMessage(code="bot_started")


@router.post("/bot/stop", response_model=ApiMessage)
async def bot_stop(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    scope = _account_scope(context)
    stopped = (
        await context.bot.stop_account(scope.account_id)
        if scope
        else await context.bot.stop()
    )
    if not stopped:
        raise _error("not_running", "Telegram runtime is not running", 409)
    context.events.publish(
        "bot",
        {"action": "stop", "account_id": scope.account_id if scope else None},
    )
    return ApiMessage(code="bot_stopped")


@router.post("/bot/restart", response_model=ApiMessage)
async def bot_restart(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    scope = _account_scope(context)
    config = scope.config if scope else context.config
    config.load()
    restarted = (
        await context.bot.get_runtime(scope.account_id).restart()
        if scope
        else await context.bot.restart()
    )
    if not restarted:
        raise _error("restart_failed", "Telegram runtime could not restart", 500)
    context.events.publish(
        "bot",
        {"action": "restart", "account_id": scope.account_id if scope else None},
    )
    return ApiMessage(code="bot_restarted")


@router.post("/bot/reset-stats", response_model=ApiMessage)
async def reset_stats(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    scope = _account_scope(context)
    if scope:
        await asyncio.to_thread(context.bot.reset_stats, scope.account_id)
    else:
        await asyncio.to_thread(context.bot.reset_stats)
    context.events.publish(
        "stats",
        {"action": "reset", "account_id": scope.account_id if scope else None},
    )
    return ApiMessage(code="stats_reset")


@router.get("/telegram-auth")
async def telegram_auth_state(context: ApplicationContext = Depends(get_context)) -> dict:
    if context.accounts:
        account_id = _selected_account_id(context)
        account = context.accounts.store.get_public(account_id)
        auth = context.accounts.get_auth(account_id)
        return {
            **auth.get_state(),
            "account_id": account_id,
            "authenticated": account["authenticated"],
        }
    return {
        "state": "not_required",
        "error": "",
        "user_info": "",
        "authenticated": True,
    }


@router.post("/telegram-auth/start", response_model=ApiMessage)
async def telegram_auth_start(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    if context.accounts:
        account_id = _selected_account_id(context)
        if context.accounts.is_authentication_running(account_id):
            return ApiMessage(code="auth_in_progress")
        auth = context.accounts.get_auth(account_id)
        auth.reset()
        valid, message = context.config.validate_connection()
        if not valid:
            raise _error("invalid_connection_config", message, 422)
        await context.accounts.start_authentication(account_id)
        context.events.publish("telegram-auth", {"state": "started", "account_id": account_id})
        return ApiMessage(code="auth_started")
    raise _error("not_user_mode", "Telegram authentication is only used in user mode", 409)


def _submit_auth(context: ApplicationContext, kind: str, value: str) -> ApiMessage:
    if not context.accounts:
        raise _error("not_user_mode", "Telegram authentication is only used in user mode", 409)
    account_id = _selected_account_id(context)
    auth = context.accounts.get_auth(account_id)
    submitter = getattr(auth, f"submit_{kind}")
    if not submitter(value):
        raise _error("auth_value_rejected", f"No {kind} challenge is waiting", 409)
    context.events.publish(
        "telegram-auth",
        {"submitted": kind, "account_id": account_id},
    )
    return ApiMessage(code=f"{kind}_submitted")


@router.post("/telegram-auth/phone", response_model=ApiMessage)
async def submit_phone(
    payload: AuthValue,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    return _submit_auth(context, "phone", payload.value)


@router.post("/telegram-auth/code", response_model=ApiMessage)
async def submit_code(
    payload: AuthValue,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    return _submit_auth(context, "code", payload.value)


@router.post("/telegram-auth/password", response_model=ApiMessage)
async def submit_password(
    payload: AuthValue,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    return _submit_auth(context, "password", payload.value)


@router.delete("/telegram-auth/session", response_model=ApiMessage)
async def clear_telegram_session(
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    account_id = _selected_account_id(context) if context.accounts else None
    if context.accounts:
        await context.accounts.clear_session(account_id)
    else:
        if context.bot.is_running:
            await context.bot.stop()
        await asyncio.to_thread(TelegramClientManager(context.config).clear_session)
    context.events.publish("telegram-account", {"action": "deauthenticated", "account_id": account_id})
    context.events.publish("telegram-auth", {"state": "cleared", "account_id": account_id})
    return ApiMessage(code="telegram_session_cleared")


@router.get("/rules")
async def list_rules(context: ApplicationContext = Depends(get_context)) -> list[dict]:
    return _active_rules(context).list_rules()


@router.post("/rules", status_code=201)
async def create_rule(
    payload: ForwardingRulePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _active_rules(context).create_rule(payload)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 422) from exc


@router.put("/rules/{index}")
async def update_rule(
    index: int,
    payload: ForwardingRulePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _active_rules(context).update_rule(index, payload)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 404 if exc.code == "not_found" else 422) from exc


@router.patch("/rules/{index}")
async def toggle_rule(
    index: int,
    payload: TogglePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _active_rules(context).set_rule_enabled(
            index,
            payload.enabled,
        )
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 404 if exc.code == "not_found" else 422) from exc


@router.delete("/rules/{index}", response_model=ApiMessage)
async def delete_rule(
    index: int,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        await _active_rules(context).delete_rule(index)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 404 if exc.code == "not_found" else 422) from exc
    return ApiMessage(code="rule_deleted")


def _subscriber_store(context: ApplicationContext):
    """Resolve the request-bound account's push subscription store."""
    scope = _account_scope(context)
    return scope.runtime.get_subscriber_store()


@router.get("/subscribers")
async def list_subscribers(
    context: ApplicationContext = Depends(get_context),
) -> dict:
    store = _subscriber_store(context)
    return {
        "items": store.list(),
        "counts": store.counts(),
    }


@router.post("/subscribers/{user_id}/pause", response_model=ApiMessage)
async def pause_subscriber(
    user_id: int,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    store = _subscriber_store(context)
    if store.get(user_id) is None:
        raise _error("subscriber_not_found", "Subscriber does not exist", 404)
    store.set_status(user_id, "paused")
    return ApiMessage(code="subscriber_paused")


@router.post("/subscribers/{user_id}/resume", response_model=ApiMessage)
async def resume_subscriber(
    user_id: int,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    store = _subscriber_store(context)
    if store.get(user_id) is None:
        raise _error("subscriber_not_found", "Subscriber does not exist", 404)
    store.set_status(user_id, "active")
    return ApiMessage(code="subscriber_resumed")


@router.get("/button-rules")
async def list_button_rules(context: ApplicationContext = Depends(get_context)) -> list[dict]:
    return _active_rules(context).list_button_rules()


@router.post("/button-rules", status_code=201)
async def create_button_rule(
    payload: ButtonActionRulePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _active_rules(context).create_button_rule(payload)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 422) from exc


@router.put("/button-rules/{index}")
async def update_button_rule(
    index: int,
    payload: ButtonActionRulePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _active_rules(context).update_button_rule(index, payload)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 404 if exc.code == "not_found" else 422) from exc


@router.delete("/button-rules/{index}", response_model=ApiMessage)
async def delete_button_rule(
    index: int,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        await _active_rules(context).delete_button_rule(index)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 404 if exc.code == "not_found" else 422) from exc
    return ApiMessage(code="button_rule_deleted")


@router.get("/stats")
async def stats(
    date_limit: StatsDateLimit = "30day",
    context: ApplicationContext = Depends(get_context),
) -> dict:
    database = _active_stats(context)
    report_days = STATS_DATE_LIMIT_DAYS[date_limit]
    details, button_details, daily = await asyncio.gather(
        asyncio.to_thread(database.get_rule_stats_detail),
        asyncio.to_thread(database.get_button_action_stats),
        asyncio.to_thread(
            database.get_daily_stats,
            None if report_days is None else report_days * 2,
        ),
    )
    return {"rules": details, "button_rules": button_details, "daily": daily}


@router.get("/history")
async def history(
    rule_name: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    context: ApplicationContext = Depends(get_context),
) -> dict:
    rows, total = await asyncio.to_thread(
        _active_stats(context).query_history,
        rule_name or None,
        keyword or None,
        page_size,
        (page - 1) * page_size,
    )
    return {"items": rows, "page": page, "page_size": page_size, "total": total}


@router.get("/logs")
async def logs(
    lines: int = Query(200, ge=1, le=2000),
    account_id: str | None = Query(None, min_length=1, max_length=64),
) -> dict:
    path = Path("logs/telerelay.log")
    if not path.exists():
        return {"lines": []}
    content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
    log_lines = content.splitlines()
    if account_id:
        account_tag = f"[account:{account_id}]"
        log_lines = [line for line in log_lines if account_tag in line]
    return {"lines": log_lines[-lines:]}


@router.get("/events")
async def events(
    all_accounts: bool = False,
    context: ApplicationContext = Depends(get_context),
) -> StreamingResponse:
    account_id = None if all_accounts or not context.accounts else _selected_account_id(context)
    return StreamingResponse(
        context.events.stream(lambda event: _event_visible_to_account(event, account_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/events/recent")
async def recent_events(
    limit: int = Query(10, ge=1, le=100),
    types: list[str] | None = Query(None),
    context: ApplicationContext = Depends(get_context),
) -> list[dict]:
    event_types = {value for value in (types or []) if value}
    account_id = _selected_account_id(context) if context.accounts else None
    return context.events.recent(
        limit,
        event_types or None,
        lambda event: _event_visible_to_account(event, account_id),
    )


@router.get("/exports/availability")
async def export_availability(context: ApplicationContext = Depends(get_context)) -> dict:
    available, reason = _active_exports(context).availability(require_connection=True)
    return {"available": available, "reason": reason}


@router.post("/exports/jobs/groups", status_code=202)
async def start_group_export(
    payload: GroupExportRequest,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        job_id = _active_exports(context).start_group_export(payload.formats, payload.subdirectory)
        return {"job_id": job_id}
    except ExportError as exc:
        raise _error("export_failed", str(exc), 422) from exc


@router.post("/exports/jobs/messages", status_code=202)
async def start_message_export(
    payload: MessageExportRequest,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        account_id = _selected_account_id(context)
        chat = await asyncio.to_thread(
            _telegram_chats(context).get_chat, account_id, payload.chat_id
        )
        job_id = _active_exports(context).start_message_export(
            chat_id=payload.chat_id,
            chat_title=chat.title,
            start_at=payload.start_at,
            end_at=payload.end_at,
            formats=payload.formats,
            subdirectory=payload.subdirectory,
            all_history=payload.all_history,
        )
        return {"job_id": job_id}
    except TelegramChatError as exc:
        raise _telegram_chat_error(exc) from exc
    except ExportError as exc:
        raise _error("export_failed", str(exc), 422) from exc


@router.get("/exports/jobs/{job_id}")
async def export_job(
    job_id: str,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    snapshot = _active_exports(context).get_job(job_id)
    if not snapshot:
        raise _error("not_found", "Export job does not exist", 404)
    return _dataclass(snapshot)


@router.post("/exports/jobs/{job_id}/cancel", response_model=ApiMessage)
async def cancel_export_job(
    job_id: str,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    if not _active_exports(context).cancel_job(job_id):
        raise _error("not_cancellable", "Export job cannot be cancelled", 409)
    return ApiMessage(code="export_cancelling")


@router.get("/exports/tasks")
async def export_tasks(context: ApplicationContext = Depends(get_context)) -> list[dict]:
    return [_dataclass(task) for task in _active_exports(context).list_tasks()]


async def _save_task(
    context: ApplicationContext, payload: ExportTaskPayload, task_id=None
):
    account_id = _selected_account_id(context)
    chat = await asyncio.to_thread(
        _telegram_chats(context).get_chat, account_id, payload.chat_id
    )
    return _active_exports(context).save_task(
        task_id=task_id,
        name=payload.name,
        chat_id=payload.chat_id,
        chat_title=chat.title,
        initial_start_at=payload.initial_start_at,
        formats=payload.formats,
        subdirectory=payload.subdirectory,
        schedule_type=payload.schedule_type,
        minute=payload.minute,
        hour=payload.hour,
        weekday=payload.weekday,
        timezone_name=payload.timezone,
        all_history=payload.all_history,
        enabled=payload.enabled,
    )


@router.post("/exports/tasks", status_code=201)
async def create_export_task(
    payload: ExportTaskPayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return _dataclass(await _save_task(context, payload))
    except TelegramChatError as exc:
        raise _telegram_chat_error(exc) from exc
    except (ExportError, ValueError) as exc:
        raise _error("invalid_export_task", str(exc), 422) from exc


@router.put("/exports/tasks/{task_id}")
async def update_export_task(
    task_id: int,
    payload: ExportTaskPayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return _dataclass(await _save_task(context, payload, task_id))
    except KeyError as exc:
        raise _error("not_found", "Export task does not exist", 404) from exc
    except TelegramChatError as exc:
        raise _telegram_chat_error(exc) from exc
    except (ExportError, ValueError) as exc:
        raise _error("invalid_export_task", str(exc), 422) from exc


@router.patch("/exports/tasks/{task_id}")
async def toggle_export_task(
    task_id: int,
    payload: TogglePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return _dataclass(_active_exports(context).set_task_enabled(task_id, payload.enabled))
    except KeyError as exc:
        raise _error("not_found", "Export task does not exist", 404) from exc


@router.delete("/exports/tasks/{task_id}", response_model=ApiMessage)
async def delete_export_task(
    task_id: int,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        _active_exports(context).delete_task(task_id)
    except KeyError as exc:
        raise _error("not_found", "Export task does not exist", 404) from exc
    except ExportError as exc:
        raise _error("task_running", str(exc), 409) from exc
    return ApiMessage(code="export_task_deleted")


@router.post("/exports/tasks/{task_id}/run", status_code=202)
async def run_export_task(
    task_id: int,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        job_id = _active_scheduler(context).run_now(task_id)
    except KeyError as exc:
        raise _error("not_found", "Export task does not exist", 404) from exc
    except ExportError as exc:
        raise _error("export_failed", str(exc), 409) from exc
    if job_id is None:
        raise _error("already_running", "Export task is already running", 409)
    return {"job_id": job_id}


@router.get("/exports/runs")
async def export_runs(
    limit: int = Query(50, ge=1, le=500),
    context: ApplicationContext = Depends(get_context),
) -> list[dict]:
    return [_dataclass(run) for run in _active_exports(context).list_runs(limit)]


@router.delete("/exports/runs/{run_id}", response_model=ApiMessage)
async def delete_export_run(
    run_id: int,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        _active_exports(context).delete_run(run_id)
    except KeyError as exc:
        raise _error("not_found", "Export run does not exist", 404) from exc
    return ApiMessage(code="export_run_deleted")


@router.get("/exports/file")
async def export_file(
    path: str,
    context: ApplicationContext = Depends(get_context),
) -> FileResponse:
    candidate = Path(path).resolve()
    exports = _active_exports(context)
    roots = [exports.export_root.resolve(), exports.message_db_root.resolve()]
    if not candidate.is_file() or not any(candidate == root or root in candidate.parents for root in roots):
        raise _error("not_found", "Export file does not exist", 404)
    return FileResponse(candidate, filename=candidate.name)


@router.get("/exports/preview-token")
async def export_preview_token(
    path: str,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        token = _active_exports(context).create_preview_token(path)
    except ExportError as exc:
        raise _error("export_failed", str(exc), 422) from exc
    return {"token": token}


@router.get("/config")
async def get_config(context: ApplicationContext = Depends(get_context)) -> dict:
    config = _active_config(context)
    return {
        "runtime": config.to_dict(),
        "config": config.config_data,
        "schema": config_json_schema(),
    }


@router.put("/config", response_model=ApiMessage)
async def replace_config(
    payload: ConfigPayload,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        validate_config(payload.config)
    except ValidationError as exc:
        raise _error("invalid_config", config_validation_message(exc), 422) from exc
    scope = _account_scope(context)
    if scope:
        context.account_registry.replace_config(scope.account_id, payload.config)
        runtime = scope.runtime
        if runtime.is_running:
            await runtime.restart()
    else:
        context.config.replace(payload.config)
        if context.bot.is_running:
            await context.bot.restart()
    return ApiMessage(code="config_saved")


@router.get("/config/export")
async def export_config(context: ApplicationContext = Depends(get_context)) -> FileResponse:
    config = _active_config(context)
    path = Path(config.config_file)
    if not path.is_file():
        raise _error("not_found", "Configuration file does not exist", 404)
    scope = _account_scope(context)
    filename = f"config-{scope.account_id}.yaml" if scope else "config.yaml"
    return FileResponse(path, filename=filename, media_type="application/yaml")


@router.post("/config/import", response_model=ApiMessage)
async def import_config(
    file: UploadFile = File(...),
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    content = await file.read(1_048_577)
    if len(content) > 1_048_576:
        raise _error("file_too_large", "Configuration file must be at most 1 MiB", 413)
    try:
        loaded = yaml.safe_load(content.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise _error("invalid_yaml", "Configuration file is not valid YAML", 422) from exc
    if not isinstance(loaded, dict):
        raise _error("invalid_config", "Configuration root must be an object", 422)
    try:
        validate_config(loaded)
    except ValidationError as exc:
        raise _error("invalid_config", config_validation_message(exc), 422) from exc
    scope = _account_scope(context)
    if scope:
        context.account_registry.replace_config(scope.account_id, loaded)
        runtime = scope.runtime
        if runtime.is_running:
            await runtime.restart()
    else:
        context.config.replace(loaded)
        if context.bot.is_running:
            await context.bot.restart()
    return ApiMessage(code="config_imported")


@router.post("/utils/validate-regex")
async def validate_regex(payload: RegexValidateRequest) -> dict:
    errors = validate_regex_patterns(payload.patterns)
    return {"valid": len(errors) == 0, "errors": errors}
