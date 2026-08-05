"""FastAPI entry point for the TeleRelay control plane."""

import argparse
import os
import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

PREVIEW_MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}

from backend.account_paths import AccountPathRegistry
from backend.account_migration import AccountMigration
from backend.api import router
from backend.application import AccountScopeRegistry, ApplicationContext
from backend.config import AccountConfigRegistry, create_config
from backend.events import EventBus, EventLogHandler
from backend.forwarder.downloader import MediaDownloader
from backend.i18n import set_language, t
from backend.logger import setup_logger
from backend.meta import current_version
from backend.stats_db import AccountStatsRegistry
from backend.telegram_accounts import (
    TelegramAccountError,
    TelegramAccountService,
    TelegramAccountStore,
)
from backend.telegram_chats import TelegramChatService
from backend.telegram_preview import TelegramPreviewService
from backend.telegram_media import TelegramMediaService
from backend.telegram_runtimes import TelegramRuntimeRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = create_config()
    set_language(config.language)
    logger = setup_logger(level=config.log_level)

    events = EventBus()
    events.bind(asyncio.get_running_loop())
    log_handler = EventLogHandler(events)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s · %(levelname)s · [%(account_tag)s] %(message)s",
            "%H:%M:%S",
        )
    )
    logger.addHandler(log_handler)

    paths = AccountPathRegistry(config_dir=Path(config.config_file).parent, data_dir="data")
    migration = AccountMigration(paths)
    migration.run()
    account_store = TelegramAccountStore(paths=paths)
    legacy_bot_token = os.getenv("BOT_TOKEN")
    if legacy_bot_token:
        # One-time migration for pre-account-store bot installs.
        account_store.seed_bot(legacy_bot_token)
    config_registry = AccountConfigRegistry(config, paths=paths, account_store=account_store)
    stats_registry = AccountStatsRegistry(paths=paths)
    bot = TelegramRuntimeRegistry(
        config,
        account_store,
        auth_timeout=300,
        events=events,
        config_registry=config_registry,
        stats_registry=stats_registry,
        paths=paths,
    )
    bot.bind_loop(asyncio.get_running_loop())
    accounts = TelegramAccountService(account_store, bot)
    telegram_chats = TelegramChatService(bot, account_store)
    bot.chat_recorder = telegram_chats.record_chat
    telegram_preview = TelegramPreviewService(bot, account_store)
    telegram_media = TelegramMediaService(bot, account_store, config)
    bot.on_user_authenticated = accounts.update_identity
    account_registry = AccountScopeRegistry(
        config_registry,
        stats_registry,
        bot,
        paths,
        events=events,
    )
    accounts.on_account_finalized = account_registry.for_account
    accounts.on_account_deleted = account_registry.discard
    context = ApplicationContext(
        config=config,
        bot=bot,
        exports=account_registry,
        scheduler=account_registry,
        rules=account_registry,
        events=events,
        log_handler=log_handler,
        accounts=accounts,
        telegram_chats=telegram_chats,
        telegram_preview=telegram_preview,
        telegram_media=telegram_media,
        account_registry=account_registry,
    )
    app.state.context = context

    await asyncio.to_thread(MediaDownloader.purge_temp_dir)
    account_registry.start()
    await bot.start()
    await migration.resolve_default_account(accounts)
    for account in account_store.list_public():
        if account["kind"] == "bot" and not account["authenticated"]:
            try:
                await accounts.start_authentication(account["id"])
            except TelegramAccountError as exc:
                logger.error("Failed to start bot authentication for %s: %s", account["id"], exc)

    if config.admin_bot_token and config.admin_chat_id:
        from backend.bot_commands import AdminBotManager

        admin = AdminBotManager(config, bot, context)
        context.admin_thread = threading.Thread(
            target=admin.run,
            daemon=True,
            name="telerelay-admin-bot",
        )
        context.admin_thread.start()

    logger.info(t("log.main.api_ready", host=config.web_host, port=config.web_port))
    try:
        yield
    finally:
        await accounts.shutdown()
        account_registry.shutdown()
        if bot.is_running:
            await bot.stop()
        logger.removeHandler(log_handler)


def create_app() -> FastAPI:
    app = FastAPI(
        title="TeleRelay API",
        version=current_version(),
        lifespan=lifespan,
        docs_url=None,
        openapi_url=None,
        redoc_url=None,
    )

    @app.get("/api/v1/health", tags=["system"])
    async def health() -> dict:
        return {"status": "ok", "service": "telerelay"}

    @app.get("/api/v1/exports/preview/{token}/{file:path}", tags=["system"])
    async def export_preview(
        token: str,
        file: str,
        request: Request,
    ) -> Response:
        context = request.app.state.context
        try:
            exports = (
                context.account_registry
                if context.accounts
                else context.exports
            )
        except (ValueError, TelegramAccountError) as exc:
            return JSONResponse(
                {"code": "account_not_authenticated", "message": str(exc)},
                status_code=409,
            )
        zip_path = exports.resolve_preview_token(token)
        if zip_path is None:
            return JSONResponse(
                {"code": "invalid_preview_token", "message": "Preview link is invalid or expired"},
                status_code=404,
            )
        content = exports.read_archive_file(zip_path, file)
        if content is None:
            return JSONResponse(
                {"code": "preview_file_not_found", "message": "Archive file does not exist"},
                status_code=404,
            )
        media_type = PREVIEW_MEDIA_TYPES.get(Path(file).suffix.lower(), "application/octet-stream")
        return Response(content=content, media_type=media_type)

    app.include_router(router)

    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    assets = frontend_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        if frontend_dist.is_dir():
            candidate = (frontend_dist / path).resolve()
            if frontend_dist.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            index = frontend_dist / "index.html"
            if index.is_file():
                return FileResponse(index)
        return JSONResponse(
            {
                "service": "TeleRelay API",
                "docs": "/api/docs",
                "frontend": "not built",
            }
        )

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TeleRelay API server")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="reload the server when backend Python files change",
    )
    args = parser.parse_args()
    load_dotenv(".env", override=True)
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("WEB_HOST", "0.0.0.0"),
        port=int(os.getenv("WEB_PORT", "8080")),
        workers=1,
        log_config=None,
        reload=args.reload,
        reload_dirs=[str(Path(__file__).resolve().parent)] if args.reload else None,
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()
