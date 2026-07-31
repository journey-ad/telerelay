"""Versioned REST and SSE API."""

import asyncio
import json
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
from starlette.background import BackgroundTask

from backend.api.dependencies import get_context, require_auth
from backend.application import ApplicationContext
from backend.client import TelegramClientManager
from backend.exporter.service import ExportError
from backend.schemas import (
    ApiMessage,
    AuthValue,
    ButtonActionRulePayload,
    ConfigPayload,
    ExportTaskPayload,
    ForwardingRulePayload,
    GroupExportRequest,
    MessageExportRequest,
    RegexValidateRequest,
    TelegramAccountCreate,
    TogglePayload,
)
from backend.services import ServiceError, validate_regex_patterns
from backend.stats_db import get_stats_db
from backend.telegram_accounts import TelegramAccountError
from backend.telegram_preview import TelegramPreviewError

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])

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
        "session_type": context.config.session_type,
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
        "visual_media_download_failed": 502,
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


@router.get("/telegram-preview/dialogs")
async def telegram_preview_dialogs(
    account_id: str | None = None,
    folder: str = Query("main", pattern="^(main|archived)$"),
    limit: int = Query(40, ge=1, le=100),
    cursor: str | None = None,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _telegram_preview(context).list_dialogs(
            account_id=account_id,
            folder=folder,
            limit=limit,
            cursor=cursor,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.get("/telegram-preview/chats/{chat_id}/messages")
async def telegram_preview_messages(
    chat_id: int,
    account_id: str,
    limit: int = Query(40, ge=1, le=100),
    before_id: int | None = Query(None, ge=1),
    query: str | None = Query(None, max_length=200),
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _telegram_preview(context).list_messages(
            account_id=account_id,
            chat_id=chat_id,
            limit=limit,
            before_id=before_id,
            query=(query or "").strip() or None,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.get("/telegram-preview/chats/{chat_id}/messages/{message_id}")
async def telegram_preview_message(
    chat_id: int,
    message_id: int,
    account_id: str,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await _telegram_preview(context).get_message(
            account_id=account_id,
            chat_id=chat_id,
            message_id=message_id,
        )
    except TelegramPreviewError as exc:
        raise _preview_error(exc) from exc


@router.get("/telegram-preview/peers/{peer_id}/avatar")
async def telegram_preview_avatar(
    peer_id: int,
    request: Request,
    account_id: str,
    context: ApplicationContext = Depends(get_context),
) -> Response:
    try:
        content = await _telegram_preview(context).avatar(
            account_id=account_id,
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
    account_id: str,
    context: ApplicationContext = Depends(get_context),
) -> Response:
    try:
        content, media_type = await _telegram_preview(context).media_thumbnail(
            account_id=account_id,
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
    account_id: str,
    context: ApplicationContext = Depends(get_context),
) -> FileResponse:
    try:
        path, media_type, filename = await _telegram_preview(context).download_visual_media(
            account_id=account_id,
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
        account = await _accounts(context).create(payload.label)
    except TelegramAccountError as exc:
        raise _error(exc.code, str(exc), 409) from exc
    context.events.publish("telegram-account", {"action": "create", "id": account["id"]})
    return account


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


@router.get("/bot/status")
async def bot_status(context: ApplicationContext = Depends(get_context)) -> dict:
    return await asyncio.to_thread(context.bot.get_status)


@router.post("/bot/start", response_model=ApiMessage)
async def bot_start(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    valid, message = context.config.validate()
    if not valid:
        raise _error("invalid_config", message, 422)
    if not await context.bot.start():
        raise _error("already_running", "Telegram runtime is already running", 409)
    context.events.publish("bot", {"action": "start"})
    return ApiMessage(code="bot_started")


@router.post("/bot/stop", response_model=ApiMessage)
async def bot_stop(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    if not await context.bot.stop():
        raise _error("not_running", "Telegram runtime is not running", 409)
    context.events.publish("bot", {"action": "stop"})
    return ApiMessage(code="bot_stopped")


@router.post("/bot/restart", response_model=ApiMessage)
async def bot_restart(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    context.config.load()
    if not await context.bot.restart():
        raise _error("restart_failed", "Telegram runtime could not restart", 500)
    context.events.publish("bot", {"action": "restart"})
    return ApiMessage(code="bot_restarted")


@router.post("/bot/reset-stats", response_model=ApiMessage)
async def reset_stats(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    await asyncio.to_thread(context.bot.reset_stats)
    context.events.publish("stats", {"action": "reset"})
    return ApiMessage(code="stats_reset")


@router.get("/telegram-auth")
async def telegram_auth_state(context: ApplicationContext = Depends(get_context)) -> dict:
    if context.accounts:
        auth = context.accounts.get_auth()
        return {
            **auth.get_state(),
            "account_id": context.accounts.store.active_account_id,
        }
    return {"state": "not_required", "error": "", "user_info": ""}


@router.post("/telegram-auth/start", response_model=ApiMessage)
async def telegram_auth_start(context: ApplicationContext = Depends(get_context)) -> ApiMessage:
    if context.accounts:
        account_id = context.accounts.store.active_account_id
        if context.accounts.runtimes.is_account_running(account_id):
            return ApiMessage(code="auth_in_progress")
        auth = context.accounts.get_auth()
        auth.reset()
        valid, message = context.config.validate_connection()
        if not valid:
            raise _error("invalid_connection_config", message, 422)
        await context.accounts.start_authentication()
        return ApiMessage(code="auth_started")
    raise _error("not_user_mode", "Telegram authentication is only used in user mode", 409)


def _submit_auth(context: ApplicationContext, kind: str, value: str) -> ApiMessage:
    if not context.accounts:
        raise _error("not_user_mode", "Telegram authentication is only used in user mode", 409)
    auth = context.accounts.get_auth()
    submitter = getattr(auth, f"submit_{kind}")
    if not submitter(value):
        raise _error("auth_value_rejected", f"No {kind} challenge is waiting", 409)
    context.events.publish("telegram-auth", {"submitted": kind})
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
    if context.accounts:
        await context.accounts.clear_active_session()
    else:
        if context.bot.is_running:
            await context.bot.stop()
        await asyncio.to_thread(TelegramClientManager(context.config).clear_session)
    return ApiMessage(code="telegram_session_cleared")


@router.get("/rules")
async def list_rules(context: ApplicationContext = Depends(get_context)) -> list[dict]:
    return context.rules.list_rules()


@router.post("/rules", status_code=201)
async def create_rule(
    payload: ForwardingRulePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await context.rules.create_rule(payload)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 422) from exc


@router.put("/rules/{index}")
async def update_rule(
    index: int,
    payload: ForwardingRulePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await context.rules.update_rule(index, payload)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 404 if exc.code == "not_found" else 422) from exc


@router.delete("/rules/{index}", response_model=ApiMessage)
async def delete_rule(
    index: int,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        await context.rules.delete_rule(index)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 404 if exc.code == "not_found" else 422) from exc
    return ApiMessage(code="rule_deleted")


@router.get("/button-rules")
async def list_button_rules(context: ApplicationContext = Depends(get_context)) -> list[dict]:
    return context.rules.list_button_rules()


@router.post("/button-rules", status_code=201)
async def create_button_rule(
    payload: ButtonActionRulePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await context.rules.create_button_rule(payload)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 422) from exc


@router.put("/button-rules/{index}")
async def update_button_rule(
    index: int,
    payload: ButtonActionRulePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return await context.rules.update_button_rule(index, payload)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 404 if exc.code == "not_found" else 422) from exc


@router.delete("/button-rules/{index}", response_model=ApiMessage)
async def delete_button_rule(
    index: int,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        await context.rules.delete_button_rule(index)
    except ServiceError as exc:
        raise _error(exc.code, str(exc), 404 if exc.code == "not_found" else 422) from exc
    return ApiMessage(code="button_rule_deleted")


@router.get("/stats")
async def stats(
    date_limit: StatsDateLimit = "30day",
) -> dict:
    database = get_stats_db()
    report_days = STATS_DATE_LIMIT_DAYS[date_limit]
    details, daily = await asyncio.gather(
        asyncio.to_thread(database.get_rule_stats_detail),
        asyncio.to_thread(
            database.get_daily_stats,
            None if report_days is None else report_days * 2,
        ),
    )
    return {"rules": details, "daily": daily}


@router.get("/history")
async def history(
    rule_name: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict:
    rows, total = await asyncio.to_thread(
        get_stats_db().query_history,
        rule_name or None,
        keyword or None,
        page_size,
        (page - 1) * page_size,
    )
    return {"items": rows, "page": page, "page_size": page_size, "total": total}


@router.get("/logs")
async def logs(lines: int = Query(200, ge=1, le=2000)) -> dict:
    path = Path("logs/telerelay.log")
    if not path.exists():
        return {"lines": []}
    content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
    return {"lines": content.splitlines()[-lines:]}


@router.get("/events")
async def events(context: ApplicationContext = Depends(get_context)) -> StreamingResponse:
    return StreamingResponse(
        context.events.stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/exports/availability")
async def export_availability(context: ApplicationContext = Depends(get_context)) -> dict:
    available, reason = context.exports.availability(require_connection=True)
    return {"available": available, "reason": reason}


@router.get("/exports/chats")
async def export_chats(context: ApplicationContext = Depends(get_context)) -> list[dict]:
    try:
        choices = await asyncio.to_thread(context.exports.list_chat_choices)
        return [{"label": label, "chat_id": int(chat_id)} for label, chat_id in choices]
    except ExportError as exc:
        raise _error("export_unavailable", str(exc), 409) from exc


@router.post("/exports/jobs/groups", status_code=202)
async def start_group_export(
    payload: GroupExportRequest,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        job_id = context.exports.start_group_export(payload.formats, payload.subdirectory)
        return {"job_id": job_id}
    except ExportError as exc:
        raise _error("export_failed", str(exc), 422) from exc


@router.post("/exports/jobs/messages", status_code=202)
async def start_message_export(
    payload: MessageExportRequest,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        job_id = context.exports.start_message_export(
            chat_id=payload.chat_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
            formats=payload.formats,
            subdirectory=payload.subdirectory,
            all_history=payload.all_history,
        )
        return {"job_id": job_id}
    except ExportError as exc:
        raise _error("export_failed", str(exc), 422) from exc


@router.get("/exports/jobs/{job_id}")
async def export_job(
    job_id: str,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    snapshot = context.exports.get_job(job_id)
    if not snapshot:
        raise _error("not_found", "Export job does not exist", 404)
    return _dataclass(snapshot)


@router.post("/exports/jobs/{job_id}/cancel", response_model=ApiMessage)
async def cancel_export_job(
    job_id: str,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    if not context.exports.cancel_job(job_id):
        raise _error("not_cancellable", "Export job cannot be cancelled", 409)
    return ApiMessage(code="export_cancelling")


@router.get("/exports/tasks")
async def export_tasks(context: ApplicationContext = Depends(get_context)) -> list[dict]:
    return [_dataclass(task) for task in context.exports.list_tasks()]


def _save_task(context: ApplicationContext, payload: ExportTaskPayload, task_id=None):
    return context.exports.save_task(
        task_id=task_id,
        name=payload.name,
        chat_id=payload.chat_id,
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
        return _dataclass(_save_task(context, payload))
    except (ExportError, ValueError) as exc:
        raise _error("invalid_export_task", str(exc), 422) from exc


@router.put("/exports/tasks/{task_id}")
async def update_export_task(
    task_id: int,
    payload: ExportTaskPayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return _dataclass(_save_task(context, payload, task_id))
    except KeyError as exc:
        raise _error("not_found", "Export task does not exist", 404) from exc
    except (ExportError, ValueError) as exc:
        raise _error("invalid_export_task", str(exc), 422) from exc


@router.patch("/exports/tasks/{task_id}")
async def toggle_export_task(
    task_id: int,
    payload: TogglePayload,
    context: ApplicationContext = Depends(get_context),
) -> dict:
    try:
        return _dataclass(context.exports.set_task_enabled(task_id, payload.enabled))
    except KeyError as exc:
        raise _error("not_found", "Export task does not exist", 404) from exc


@router.delete("/exports/tasks/{task_id}", response_model=ApiMessage)
async def delete_export_task(
    task_id: int,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    try:
        context.exports.delete_task(task_id)
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
        job_id = context.scheduler.run_now(task_id)
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
    return [_dataclass(run) for run in context.exports.list_runs(limit)]


@router.get("/exports/file")
async def export_file(
    path: str,
    context: ApplicationContext = Depends(get_context),
) -> FileResponse:
    candidate = Path(path).resolve()
    roots = [context.exports.export_root.resolve(), context.exports.message_db_root.resolve()]
    if not candidate.is_file() or not any(candidate == root or root in candidate.parents for root in roots):
        raise _error("not_found", "Export file does not exist", 404)
    return FileResponse(candidate, filename=candidate.name)


@router.get("/config")
async def get_config(context: ApplicationContext = Depends(get_context)) -> dict:
    return {
        "runtime": context.config.to_dict(),
        "config": context.config.config_data,
    }


@router.put("/config", response_model=ApiMessage)
async def replace_config(
    payload: ConfigPayload,
    context: ApplicationContext = Depends(get_context),
) -> ApiMessage:
    context.config.replace(payload.config)
    if context.bot.is_running:
        await context.bot.restart()
    return ApiMessage(code="config_saved")


@router.get("/config/export")
async def export_config(context: ApplicationContext = Depends(get_context)) -> FileResponse:
    path = Path(context.config.config_file)
    if not path.is_file():
        raise _error("not_found", "Configuration file does not exist", 404)
    return FileResponse(path, filename="config.yaml", media_type="application/yaml")


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
    context.config.replace(loaded)
    if context.bot.is_running:
        await context.bot.restart()
    return ApiMessage(code="config_imported")


@router.post("/utils/validate-regex")
async def validate_regex(payload: RegexValidateRequest) -> dict:
    errors = validate_regex_patterns(payload.patterns)
    return {"valid": len(errors) == 0, "errors": errors}
