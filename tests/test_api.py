import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import router
from backend.application import ApplicationContext
from backend.auth_manager import AuthManager
from backend.config import Config
from backend.events import EventBus
from backend.services import RuleService
from backend.telegram_accounts import TelegramAccountService, TelegramAccountStore
from backend.telegram_chats import TelegramChat
from backend.telegram_runtimes import TelegramRuntimeRegistry


class FakeBot:
    def __init__(
        self,
        config=None,
        auth_manager=None,
        session_name=None,
        queue_db_path=None,
        account_id=None,
    ):
        self.is_running = False
        self.is_connected = False
        self.restarts = 0
        self.session_name = Path(session_name or "data/telegram_session")
        self.queue_db_path = Path(queue_db_path) if queue_db_path else None
        self.account_id = account_id
        self.client_manager = None
        self.forwarders = []
        self.on_user_authenticated = None

    async def start(self):
        if self.is_running:
            return False
        self.is_running = True
        return True

    async def stop(self):
        if not self.is_running:
            return False
        self.is_running = False
        return True

    async def restart(self):
        self.restarts += 1
        self.is_running = True
        return True

    def bind_loop(self, loop):
        self.loop = loop

    def get_status(self):
        return {
            "is_running": self.is_running,
            "is_connected": False,
            "stats": {"forwarded": 0, "filtered": 0, "total": 0},
            "queue": {"counts": {}, "paused_until": 0, "pause_reason": None},
        }

    def reset_stats(self):
        return None


class FakeTelegramPreview:
    def __init__(self):
        self.calls = []

    async def list_dialogs(self, **values):
        self.calls.append(("dialogs", values))
        return {
            "account_id": values["account_id"],
            "folder": values["folder"],
            "items": [],
            "next_cursor": None,
        }

    async def list_messages(self, **values):
        self.calls.append(("messages", values))
        return {
            "account_id": values["account_id"],
            "chat": {"id": values["chat_id"], "title": "测试会话"},
            "items": [],
            "next_before_id": None,
        }

    async def get_message(self, **values):
        self.calls.append(("message", values))
        return {
            "id": values["message_id"],
            "chat_id": values["chat_id"],
            "text": "原始消息",
        }


class FakeTelegramChats:
    def __init__(self):
        self.calls = []
        self.chat = TelegramChat(
            id=-1001,
            title="Release Room",
            kind="supergroup",
            username="release_room",
        )

    def list_chats(self, account_id):
        self.calls.append(("list", account_id))
        return [self.chat]

    def get_chat(self, account_id, chat_id):
        self.calls.append(("get", account_id, chat_id))
        return self.chat


class FakeExports:
    def __init__(self):
        self.message_export = None

    def start_message_export(self, **values):
        self.message_export = values
        return "job-1"


def make_app(context: ApplicationContext) -> FastAPI:
    app = FastAPI()
    app.state.context = context
    app.include_router(router)
    return app


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.env_patch = patch.dict(os.environ, {"SESSION_TYPE": "user"}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.config = Config(
            env_file=str(root / "missing.env"),
            config_file=str(root / "config.yaml"),
        )
        self.account_store = TelegramAccountStore(root / "data")
        self.bot = TelegramRuntimeRegistry(
            self.config,
            self.account_store,
            auth_timeout=1,
            bot_factory=FakeBot,
        )
        self.auth = self.bot.get_auth()
        self.events = EventBus()
        self.rules = RuleService(self.config, self.bot)
        self.accounts = TelegramAccountService(self.account_store, self.bot)
        self.stats_patch = patch(
            "backend.telegram_runtimes.get_stats_db",
            return_value=SimpleNamespace(
                get_all_stats=dict,
                reset_stats=lambda: None,
            ),
        )
        self.stats_patch.start()
        self.addCleanup(self.stats_patch.stop)
        self.telegram_preview = FakeTelegramPreview()
        self.telegram_chats = FakeTelegramChats()
        self.exports = FakeExports()
        self.context = ApplicationContext(
            config=self.config,
            bot=self.bot,
            exports=self.exports,
            scheduler=SimpleNamespace(),
            rules=self.rules,
            events=self.events,
            log_handler=SimpleNamespace(),
            accounts=self.accounts,
            telegram_chats=self.telegram_chats,
            telegram_preview=self.telegram_preview,
        )
        self.client = TestClient(make_app(self.context))
        self.addCleanup(self.client.close)

    def test_session_and_bot_status_contracts(self):
        session = self.client.get("/api/v1/session")
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.json()["session_type"], "user")

        status = self.client.get("/api/v1/bot/status")
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["is_running"])

    def test_stats_accepts_date_limit_presets(self):
        calls = []
        database = SimpleNamespace(
            get_rule_stats_detail=list,
            get_daily_stats=lambda days: calls.append(days) or [{"days": days}],
        )

        with patch("backend.api.router.get_stats_db", return_value=database):
            default = self.client.get("/api/v1/stats")
            responses = {
                date_limit: self.client.get(
                    "/api/v1/stats", params={"date_limit": date_limit}
                )
                for date_limit in ("7day", "14day", "30day", "all")
            }
            invalid = self.client.get("/api/v1/stats", params={"date_limit": "90day"})

        self.assertEqual(default.status_code, 200, default.text)
        self.assertEqual(calls, [60, 14, 28, 60, None])
        self.assertTrue(all(response.status_code == 200 for response in responses.values()))
        self.assertEqual(invalid.status_code, 422)

    def test_telegram_account_create_list_and_activate_contracts(self):
        initial = self.client.get("/api/v1/telegram-accounts")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()[0]["id"], "default")

        created = self.client.post(
            "/api/v1/telegram-accounts",
            json={"label": "工作账号"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertTrue(created.json()["active"])

        activated = self.client.post("/api/v1/telegram-accounts/default/activate")
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertTrue(activated.json()["active"])

    def test_telegram_account_avatar_contract(self):
        missing = self.client.get("/api/v1/telegram-accounts/default/avatar")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["code"], "avatar_not_found")

        self.account_store.update_avatar("default", b"fake-jpeg-avatar")
        response = self.client.get("/api/v1/telegram-accounts/default/avatar")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(response.content, b"fake-jpeg-avatar")
        account = self.client.get("/api/v1/telegram-accounts").json()[0]
        self.assertIsNotNone(account["avatar_version"])

    def test_telegram_account_chats_contract(self):
        response = self.client.get("/api/v1/telegram-accounts/default/chats")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            [
                {
                    "id": -1001,
                    "title": "Release Room",
                    "kind": "supergroup",
                    "username": "release_room",
                }
            ],
        )
        self.assertEqual(self.telegram_chats.calls, [("list", "default")])
        self.assertEqual(self.client.get("/api/v1/exports/chats").status_code, 404)

    def test_message_export_resolves_chat_title_without_listing_chats(self):
        response = self.client.post(
            "/api/v1/exports/jobs/messages",
            json={
                "chat_id": -1001,
                "formats": ["json"],
                "all_history": True,
            },
        )

        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json(), {"job_id": "job-1"})
        self.assertEqual(self.telegram_chats.calls, [("get", "default", -1001)])
        self.assertEqual(self.exports.message_export["chat_title"], "Release Room")

    def test_telegram_preview_dialog_and_message_contracts(self):
        dialogs = self.client.get(
            "/api/v1/telegram-preview/dialogs",
            params={"account_id": "default", "folder": "archived", "limit": 25},
        )
        messages = self.client.get(
            "/api/v1/telegram-preview/chats/-1001/messages",
            params={"account_id": "default", "query": "release"},
        )
        message = self.client.get(
            "/api/v1/telegram-preview/chats/-1001/messages/12",
            params={"account_id": "default"},
        )

        self.assertEqual(dialogs.status_code, 200, dialogs.text)
        self.assertEqual(dialogs.json()["folder"], "archived")
        self.assertEqual(messages.status_code, 200, messages.text)
        self.assertEqual(messages.json()["chat"]["id"], -1001)
        self.assertEqual(message.status_code, 200, message.text)
        self.assertEqual(message.json()["id"], 12)
        self.assertEqual(
            self.telegram_preview.calls,
            [
                (
                    "dialogs",
                    {
                        "account_id": "default",
                        "folder": "archived",
                        "limit": 25,
                        "cursor": None,
                    },
                ),
                (
                    "messages",
                    {
                        "account_id": "default",
                        "chat_id": -1001,
                        "limit": 40,
                        "before_id": None,
                        "query": "release",
                    },
                ),
                (
                    "message",
                    {
                        "account_id": "default",
                        "chat_id": -1001,
                        "message_id": 12,
                    },
                ),
            ],
        )

    def test_rule_crud_persists_yaml(self):
        payload = {
            "name": "news relay",
            "enabled": True,
            "source_chats": [-1001],
            "target_chats": [-2001],
            "filters": {"mode": "whitelist", "keywords": ["alert"]},
            "ignore": {},
            "forwarding": {"delay": 0.25},
        }
        created = self.client.post("/api/v1/rules", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["name"], "news relay")

        listed = self.client.get("/api/v1/rules")
        self.assertEqual(len(listed.json()), 1)
        self.assertTrue(Path(self.config.config_file).is_file())

        deleted = self.client.delete("/api/v1/rules/0")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/rules").json(), [])

    def test_invalid_button_regex_is_structured_error(self):
        payload = {
            "name": "confirm",
            "enabled": True,
            "source_chats": ["@example_bot"],
            "button_texts": ["[invalid"],
            "match_mode": "regex",
        }
        response = self.client.post("/api/v1/button-rules", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_regex")

    def test_regex_validation_reports_invalid_patterns(self):
        response = self.client.post(
            "/api/v1/utils/validate-regex",
            json={"patterns": [r"^valid\s+$", "[invalid", "(also-invalid"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["valid"])
        self.assertEqual(
            [error["pattern"] for error in response.json()["errors"]],
            ["[invalid", "(also-invalid"],
        )

    def test_http_basic_is_enforced_when_configured(self):
        with patch.dict(
            os.environ,
            {
                "SESSION_TYPE": "user",
                "WEB_AUTH_USERNAME": "operator",
                "WEB_AUTH_PASSWORD": "secret",
            },
            clear=True,
        ):
            denied = self.client.get("/api/v1/session")
            allowed = self.client.get(
                "/api/v1/session",
                auth=("operator", "secret"),
            )
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)


class AsyncAuthManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_phone_challenge_is_resolved_without_thread_queue(self):
        auth = AuthManager(input_timeout=1)
        waiting = asyncio.create_task(auth.phone_callback())
        await asyncio.sleep(0)
        self.assertEqual(auth.get_state()["state"], "waiting_phone")
        self.assertTrue(auth.submit_phone("+8613800138000"))
        self.assertEqual(await waiting, "+8613800138000")
        self.assertIsNone(auth.get_state()["waiting_for"])


if __name__ == "__main__":
    unittest.main()
