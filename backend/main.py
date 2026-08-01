"""FastAPI entry point for the TeleRelay control plane."""

import argparse
import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
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
from backend.application import ApplicationContext
from backend.bot_manager import BotManager
from backend.config import AccountConfigRegistry, create_config
from backend.events import EventBus, EventLogHandler
from backend.exporter.registry import AccountExportRegistry
from backend.exporter.scheduler import ExportScheduler
from backend.exporter.service import ExportService
from backend.forwarder.downloader import MediaDownloader
from backend.i18n import set_language, t
from backend.logger import setup_logger
from backend.meta import current_version
from backend.services import RuleService
from backend.services.rules import AccountRuleRegistry
from backend.stats_db import AccountStatsRegistry
from backend.telegram_accounts import TelegramAccountService, TelegramAccountStore
from backend.telegram_chats import TelegramChatService
from backend.telegram_preview import TelegramPreviewService
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
        logging.Formatter("%(asctime)s · %(levelname)s · %(message)s", "%H:%M:%S")
    )
    logger.addHandler(log_handler)

    paths = AccountPathRegistry(config_dir=Path(config.config_file).parent, data_dir="data")
    migration = AccountMigration(paths)
    account_store = None
    if config.session_type == "user":
        migration.run()
        account_store = TelegramAccountStore(paths=paths)
        config_registry = AccountConfigRegistry(config, paths=paths)
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
    else:
        config_registry = None
        stats_registry = None
        bot = BotManager(config, events=events)
    bot.bind_loop(asyncio.get_running_loop())
    accounts = TelegramAccountService(account_store, bot) if account_store else None
    telegram_chats = TelegramChatService(bot, account_store) if account_store else None
    telegram_preview = TelegramPreviewService(bot, account_store) if account_store else None
    if accounts:
        bot.on_user_authenticated = accounts.update_identity
    if account_store:
        export_registry = AccountExportRegistry(config_registry, bot, paths, events=events)
        rule_registry = AccountRuleRegistry(config_registry, bot, stats_registry)
        exports = export_registry
        scheduler = export_registry
        rules = rule_registry
        accounts.on_account_finalized = export_registry.for_account

        def discard_account(account_id: str) -> None:
            export_registry.discard(account_id)
            rule_registry.discard(account_id)
            config_registry.discard(account_id)
            stats_registry.discard(account_id)

        accounts.on_account_deleted = discard_account
    else:
        export_registry = None
        rule_registry = None
        exports = ExportService(config, bot, events=events)
        scheduler = ExportScheduler(exports)
        rules = RuleService(config, bot)
    context = ApplicationContext(
        config=config,
        bot=bot,
        exports=exports,
        scheduler=scheduler,
        rules=rules,
        events=events,
        log_handler=log_handler,
        accounts=accounts,
        telegram_chats=telegram_chats,
        telegram_preview=telegram_preview,
        config_registry=config_registry,
        stats_registry=stats_registry,
        export_registry=export_registry,
        rule_registry=rule_registry,
    )
    app.state.context = context

    await asyncio.to_thread(MediaDownloader.purge_temp_dir)
    scheduler.start()
    if account_store:
        await bot.start()
        await migration.resolve_default_account(accounts)
    elif Path(f"{bot.session_name}.session").exists():
        await bot.start()

    if config.admin_bot_token and config.admin_chat_id:
        from backend.bot_commands import AdminBotManager

        admin = AdminBotManager(config, bot)
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
        if accounts:
            await accounts.shutdown()
        if export_registry:
            export_registry.shutdown()
        else:
            scheduler.shutdown()
            exports.shutdown()
        if bot.is_running:
            await bot.stop()
        logger.removeHandler(log_handler)


def create_app() -> FastAPI:
    app = FastAPI(
        title="TeleRelay API",
        version=current_version(),
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/v1/health", tags=["system"])
    async def health() -> dict:
        return {"status": "ok", "service": "telerelay"}

    @app.get("/api/v1/exports/preview/{token}/{file:path}", tags=["system"])
    async def export_preview(token: str, file: str, request: Request) -> Response:
        exports = request.app.state.context.exports
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
    config = create_config()
    uvicorn.run(
        "backend.main:app",
        host=config.web_host,
        port=config.web_port,
        workers=1,
        log_config=None,
        reload=args.reload,
        reload_dirs=[str(Path(__file__).resolve().parent)] if args.reload else None,
    )


if __name__ == "__main__":
    main()
