"""FastAPI entry point for the TeleRelay control plane."""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api import router
from backend.application import ApplicationContext
from backend.auth_manager import AuthManager
from backend.bot_manager import BotManager
from backend.config import create_config
from backend.events import EventBus, EventLogHandler
from backend.exporter.scheduler import ExportScheduler
from backend.exporter.service import ExportService
from backend.i18n import set_language
from backend.logger import get_logger, setup_logger
from backend.services import RuleService
from backend.telegram_accounts import TelegramAccountService, TelegramAccountStore
from backend.telegram_preview import TelegramPreviewService


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

    auth = AuthManager(input_timeout=300) if config.session_type == "user" else None
    account_store = TelegramAccountStore() if auth else None
    bot = BotManager(
        config,
        auth,
        session_name=account_store.active_session_name if account_store else None,
    )
    bot.bind_loop(asyncio.get_running_loop())
    accounts = TelegramAccountService(account_store, bot, auth) if account_store and auth else None
    telegram_preview = (
        TelegramPreviewService(bot, account_store, events) if account_store else None
    )
    if accounts:
        bot.on_user_authenticated = accounts.update_active_identity
    if telegram_preview:
        bot.on_preview_message = telegram_preview.handle_new_message
    exports = ExportService(config, bot)
    scheduler = ExportScheduler(exports)
    rules = RuleService(config, bot)
    context = ApplicationContext(
        config=config,
        auth=auth,
        bot=bot,
        exports=exports,
        scheduler=scheduler,
        rules=rules,
        events=events,
        log_handler=log_handler,
        accounts=accounts,
        telegram_preview=telegram_preview,
    )
    app.state.context = context

    scheduler.start()
    session_file = Path(f"{bot.session_name}.session")
    if session_file.exists():
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

    logger.info("TeleRelay API ready on %s:%s", config.web_host, config.web_port)
    try:
        yield
    finally:
        scheduler.shutdown()
        exports.shutdown()
        if bot.is_running:
            await bot.stop()
        logger.removeHandler(log_handler)


def create_app() -> FastAPI:
    app = FastAPI(
        title="TeleRelay API",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/v1/health", tags=["system"])
    async def health() -> dict:
        return {"status": "ok", "service": "telerelay"}

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
    config = create_config()
    uvicorn.run(
        "backend.main:app",
        host=config.web_host,
        port=config.web_port,
        workers=1,
        log_config=None,
    )


if __name__ == "__main__":
    main()
