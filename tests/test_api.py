import asyncio
from contextvars import ContextVar
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import router
from backend.application import AccountScope, ApplicationContext
from backend.auth_manager import AuthManager
from backend.config import AccountConfigRegistry, Config
from backend.events import EventBus
from backend.services import RuleService
from backend.stats_db import AccountStatsRegistry
from backend.telegram_accounts import (
    TelegramAccountError,
    TelegramAccountService,
    TelegramAccountStore,
)
from backend.telegram_chats import TelegramChat
from backend.telegram_preview import TelegramPreviewError
from backend.telegram_runtimes import TelegramRuntimeRegistry


class FakeBot:
    def __init__(
        self,
        config=None,
        auth_manager=None,
        session_name=None,
        queue_db_path=None,
        account_id=None,
        bot_token=None,
        session_type=None,
    ):
        self.is_running = False
        self.is_connected = False
        self.restarts = 0
        self.session_name = Path(session_name or "data/telegram_session")
        self.queue_db_path = Path(queue_db_path) if queue_db_path else None
        self.account_id = account_id
        self.bot_token = bot_token
        self.session_type = session_type
        self.client_manager = None
        self.forwarders = []
        self.on_user_authenticated = None
        self.subscriber_store = None

    def get_subscriber_store(self):
        from backend.subscriptions import SubscriberStore

        if self.subscriber_store is None:
            base = Path(self.queue_db_path).parent if self.queue_db_path else Path("data")
            self.subscriber_store = SubscriberStore(base / "subscribers.db")
        return self.subscriber_store

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

    async def send_text_message(self, **values):
        self.calls.append(("send_message", values))
        return {
            "id": 13,
            "chat_id": values["chat_id"],
            "text": values["text"],
            "outgoing": True,
        }

    async def list_bot_commands(self, **values):
        self.calls.append(("bot_commands", values))
        return {
            "account_id": values["account_id"],
            "chat_id": values["chat_id"],
            "items": [{"command": "start", "description": "开始使用"}],
        }

    async def stream_updates(self, **values):
        self.calls.append(("updates", values))

        async def generate():
            yield "event: ready\ndata: {}\n\n"
            yield 'event: message\ndata: {"chat_id": -1001, "message_id": 13}\n\n'

        return generate()


class FakeTelegramMedia:
    def __init__(self):
        self.calls = []

    async def issue_video_ticket(self, **values):
        self.calls.append(("video_ticket", values))
        return {
            "ticket": "video-ticket-123",
            "expires_at": 2_000_000_000,
            "mime_type": "video/mp4",
        }

    async def clear_account(self, account_id):
        self.calls.append(("clear_account", account_id))


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

    def create_preview_token(self, zip_path):
        return "preview-token-123"

    def delete_run(self, run_id):
        if int(run_id) == 999:
            raise KeyError("missing")


class FakeAccountRegistry:
    """Minimal registry backing the router's single account-scope entry point."""

    def __init__(self, context):
        self.context = context

    def for_account(self, account_id):
        return AccountScope(
            account_id=account_id,
            config=self.context.config,
            stats=self.stats,
            rules=self.context.rules,
            exports=self.context.exports,
            scheduler=getattr(self.context, "scheduler", SimpleNamespace()),
            runtime=self.context.bot.get_runtime(account_id),
        )

    @property
    def stats(self):
        from backend.stats_db import get_stats_db

        return get_stats_db()

    def replace_config(self, account_id, config_data):
        self.context.config.replace(config_data)
        return self.context.config


class FakeScopedRules:
    def __init__(self, name):
        self.rule = {
            "name": name,
            "enabled": False,
            "source_chats": [],
            "target_chats": [],
            "filters": {
                "mode": "whitelist",
                "keywords": [],
                "regex_patterns": [],
                "media_types": [],
                "max_file_size": 0,
                "min_file_size": 0,
            },
            "ignore": {"user_ids": [], "keywords": []},
            "forwarding": {
                "preserve_format": True,
                "add_source_info": True,
                "delay": 0.5,
                "force_forward": False,
                "hide_sender": False,
                "deduplicate": False,
                "deduplicate_window": 3600,
            },
        }

    def list_rules(self):
        return [dict(self.rule)]

    async def update_rule(self, index, payload):
        if index != 0:
            raise AssertionError("unexpected rule index")
        self.rule = payload.model_dump()
        return dict(self.rule)


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
        self.config = Config(
            env_file=str(root / "missing.env"),
            config_file=str(root / "config.yaml"),
        )
        self.account_store = TelegramAccountStore(root / "data")
        self.account_id = self.account_store.active_account_id
        self.bot = TelegramRuntimeRegistry(
            self.config,
            self.account_store,
            auth_timeout=1,
            bot_factory=FakeBot,
        )
        self.auth = self.bot.get_auth()
        self.events = EventBus()
        self.rules = RuleService(self.config, self.bot)
        self.stats_db = self.rules.stats_db
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
        self.telegram_media = FakeTelegramMedia()
        self.telegram_chats = FakeTelegramChats()
        self.exports = FakeExports()
        self.account_registry = FakeAccountRegistry(self)
        self.context = ApplicationContext(
            config=self.config,
            bot=self.bot,
            exports=self.exports,
            scheduler=SimpleNamespace(),
            rules=self.rules,
            events=self.events,
            log_handler=SimpleNamespace(),
            accounts=self.accounts,
            account_registry=self.account_registry,
            telegram_chats=self.telegram_chats,
            telegram_preview=self.telegram_preview,
            telegram_media=self.telegram_media,
        )
        self.client = TestClient(make_app(self.context))
        self.addCleanup(self.client.close)

    def test_session_and_bot_status_contracts(self):
        session = self.client.get("/api/v1/session")
        self.assertEqual(session.status_code, 200)
        self.assertNotIn("session_type", session.json())
        self.assertIn("active_account_id", session.json())

        status = self.client.get("/api/v1/bot/status")
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["is_running"])

    def test_subscribers_contract(self):
        from backend.subscriptions import SubscriberStore

        runtime = self.bot.get_runtime(self.account_id)
        runtime.subscriber_store = SubscriberStore(
            Path(self.temp_dir.name) / "subscribers.db"
        )
        store = runtime.subscriber_store

        empty = self.client.get("/api/v1/subscribers")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["items"], [])
        self.assertEqual(empty.json()["counts"], {"total": 0, "active": 0, "paused": 0})

        store.record(111, username="alice")
        store.set_status(222, "paused")

        listed = self.client.get("/api/v1/subscribers")
        self.assertEqual(listed.status_code, 200)
        body = listed.json()
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["counts"], {"total": 2, "active": 1, "paused": 1})

        paused = self.client.post("/api/v1/subscribers/111/pause")
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["code"], "subscriber_paused")
        self.assertTrue(store.is_suppressed(111))

        resumed = self.client.post("/api/v1/subscribers/111/resume")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["code"], "subscriber_resumed")
        self.assertFalse(store.is_suppressed(111))

        missing = self.client.post("/api/v1/subscribers/999/pause")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["code"], "subscriber_not_found")

    def test_auth_state_reports_persisted_session_when_runtime_state_is_idle(self):
        original_get_public = self.account_store.get_public

        def authenticated_account(account_id, *args, **kwargs):
            account = original_get_public(account_id, *args, **kwargs)
            return {**account, "authenticated": True}

        with patch.object(self.account_store, "get_public", authenticated_account):
            response = self.client.get("/api/v1/telegram-auth")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "idle")
        self.assertTrue(response.json()["authenticated"])

    def test_meta_contract(self):
        meta = self.client.get("/api/v1/meta")
        self.assertEqual(meta.status_code, 200)
        body = meta.json()
        self.assertIsInstance(body["version"], str)
        self.assertIn("commit", body)
        self.assertTrue(body["repository"].startswith("https://github.com/"))

    def test_update_check_contract(self):
        from backend.meta import UpdateInfo

        with patch(
            "backend.api.router.check_update",
            return_value=UpdateInfo(
                current_version="2.0.0",
                latest_tag="v2.1.0",
                latest_version="2.1.0",
                update_available=True,
                release_url="https://github.com/journey-ad/telerelay/releases/tag/v2.1.0",
                published_at="2026-07-31T00:00:00Z",
                commit="abcdef0",
            ),
        ):
            body = self.client.get("/api/v1/update-check").json()
        self.assertEqual(body["current_version"], "2.0.0")
        self.assertEqual(body["latest_tag"], "v2.1.0")
        self.assertTrue(body["update_available"])
        self.assertEqual(body["commit"], "abcdef0")
        self.assertIsNone(body["error"])

    def test_update_check_reports_failure_contract(self):
        from backend.meta import UpdateInfo

        with patch(
            "backend.api.router.check_update",
            return_value=UpdateInfo(current_version="2.0.0", error="HTTP 403"),
        ):
            body = self.client.get("/api/v1/update-check").json()
        self.assertFalse(body["update_available"])
        self.assertEqual(body["error"], "HTTP 403")

    def test_export_preview_token_contract(self):
        response = self.client.get(
            "/api/v1/exports/preview-token",
            params={"path": "/exports/chat.html.zip"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token"], "preview-token-123")

    def test_delete_export_run_contract(self):
        ok = self.client.delete("/api/v1/exports/runs/1")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["code"], "export_run_deleted")

        missing = self.client.delete("/api/v1/exports/runs/999")
        self.assertEqual(missing.status_code, 404)

    def test_queue_preview_contract_and_limit_validation(self):
        calls = []
        expected = [
            {
                "id": 4,
                "account_id": "default",
                "account_label": "Default",
                "rule_name": "news",
                "source_chat_id": -1001,
                "source_chat_name": "Release Room",
                "source_message_id": 42,
                "grouped_id": None,
                "status": "pending",
                "attempt_count": 1,
                "failure_count": 1,
                "next_target_index": 1,
                "target_count": 2,
                "available_at": 123.0,
                "last_error": "temporary",
                "created_at": 100.0,
                "updated_at": 120.0,
            }
        ]
        self.bot.list_queue_items = (
            lambda limit, account_id=None: calls.append((limit, account_id)) or expected
        )

        response = self.client.get("/api/v1/queue/items", params={"limit": 25})
        invalid = self.client.get("/api/v1/queue/items", params={"limit": 101})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), expected)
        self.assertEqual(calls, [(25, self.account_id)])
        self.assertEqual(invalid.status_code, 422)

    def test_recent_events_contract_filters_types_and_limits_results(self):
        self.events.publish("bot", {"action": "start"})
        self.events.publish("telegram-auth", {"submitted": "phone"})
        self.events.publish("forward", {"status": "completed"})

        response = self.client.get(
            "/api/v1/events/recent",
            params=[("limit", 2), ("types", "bot"), ("types", "forward")],
        )
        invalid = self.client.get("/api/v1/events/recent", params={"limit": 101})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [event["type"] for event in response.json()], ["forward", "bot"]
        )
        self.assertEqual([event["id"] for event in response.json()], [3, 1])
        self.assertEqual(invalid.status_code, 422)

    def test_recent_events_hide_other_accounts(self):
        self.events.publish("forward", {"account_id": self.account_id, "status": "completed"})
        self.events.publish("forward", {"account_id": "another", "status": "completed"})

        response = self.client.get("/api/v1/events/recent")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["payload"]["account_id"], self.account_id)

    def test_recent_events_deliver_account_id_finalization_to_pending_account(self):
        self.events.publish(
            "telegram-auth",
            {
                "state": "success",
                "account_id": "89336672",
                "previous_account_id": self.account_id,
            },
        )

        response = self.client.get("/api/v1/events/recent")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["payload"]["account_id"], "89336672")

    def test_account_header_pins_rule_requests_when_active_account_changes(self):
        account_ids = {"101", "202"}
        store = SimpleNamespace(
            active_account_id="202",
            get_public=lambda account_id: (
                {"id": account_id}
                if account_id in account_ids
                else (_ for _ in ()).throw(
                    TelegramAccountError("account_not_found", "missing")
                )
            ),
        )
        services = {account_id: FakeScopedRules(account_id) for account_id in account_ids}
        request_account_id = ContextVar("test_request_account_id", default=None)
        scope_registry = SimpleNamespace(
            for_account=lambda account_id: AccountScope(
                account_id=account_id,
                config=SimpleNamespace(),
                stats=SimpleNamespace(),
                rules=services[account_id],
                exports=SimpleNamespace(),
                scheduler=SimpleNamespace(),
                runtime=SimpleNamespace(),
            )
        )
        context = SimpleNamespace(
            config=SimpleNamespace(web_auth_username="", web_auth_password=""),
            accounts=SimpleNamespace(store=store),
            account_registry=scope_registry,
            request_account_id=request_account_id,
            scope_for=lambda account_id=None: scope_registry.for_account(
                account_id or request_account_id.get() or store.active_account_id
            ),
        )
        client = TestClient(make_app(context))
        self.addCleanup(client.close)

        read = client.get(
            "/api/v1/rules", headers={"X-TeleRelay-Account-ID": "101"}
        )
        payload = {**services["101"].rule, "name": "updated-101"}
        updated = client.put(
            "/api/v1/rules/0",
            headers={"X-TeleRelay-Account-ID": "101"},
            json=payload,
        )
        missing = client.get(
            "/api/v1/rules", headers={"X-TeleRelay-Account-ID": "303"}
        )

        self.assertEqual(read.json()[0]["name"], "101")
        self.assertEqual(updated.json()["name"], "updated-101")
        self.assertEqual(services["101"].rule["name"], "updated-101")
        self.assertEqual(services["202"].rule["name"], "202")
        self.assertEqual(missing.status_code, 404)

    def test_stats_accepts_date_limit_presets(self):
        calls = []
        database = SimpleNamespace(
            get_rule_stats_detail=list,
            get_daily_stats=lambda days: calls.append(days) or [{"days": days}],
            get_button_action_stats=lambda: [{"rule_name": "button", "triggered": 3}],
        )

        with patch("backend.stats_db.get_stats_db", return_value=database):
            default = self.client.get("/api/v1/stats")
            responses = {
                date_limit: self.client.get(
                    "/api/v1/stats", params={"date_limit": date_limit}
                )
                for date_limit in ("7day", "14day", "30day", "all")
            }
            invalid = self.client.get("/api/v1/stats", params={"date_limit": "90day"})

        self.assertEqual(default.status_code, 200, default.text)
        self.assertEqual(default.json()["button_rules"], [{"rule_name": "button", "triggered": 3}])
        self.assertEqual(calls, [60, 14, 28, 60, None])
        self.assertTrue(all(response.status_code == 200 for response in responses.values()))
        self.assertEqual(invalid.status_code, 422)

    def test_telegram_account_create_list_and_activate_contracts(self):
        initial = self.client.get("/api/v1/telegram-accounts")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()[0]["id"], self.account_id)

        created = self.client.post(
            "/api/v1/telegram-accounts",
            json={"label": "工作账号"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertTrue(created.json()["active"])

        activated = self.client.post(
            f"/api/v1/telegram-accounts/{self.account_id}/activate"
        )
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertTrue(activated.json()["active"])

    def test_bot_account_can_be_created_with_token(self):
        class FakeClientManager:
            def __init__(
                self,
                config,
                auth_manager=None,
                session_name=None,
                on_user_authenticated=None,
                bot_token=None,
            ):
                self.session_name = Path(session_name)
                self.on_user_authenticated = on_user_authenticated
                self.bot_token = bot_token

            async def connect(self):
                Path(f"{self.session_name}.session").write_bytes(b"fake-session")
                if self.on_user_authenticated:
                    self.on_user_authenticated(
                        {
                            "display_name": "Relay Bot",
                            "username": "relay_bot",
                            "telegram_user_id": 777001,
                        }
                    )
                return True

            async def disconnect(self):
                return None

        with patch("backend.telegram_accounts.TelegramClientManager", FakeClientManager):
            response = self.client.post(
                "/api/v1/telegram-accounts",
                json={
                    "label": "Relay Bot",
                    "kind": "bot",
                    "bot_token": "123456789:AA" + "x" * 30,
                },
            )

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["kind"], "bot")
        self.assertEqual(body["telegram_user_id"], 777001)
        self.assertNotIn("bot_token", body)
        self.assertEqual(body["username"], "relay_bot")

        auth_state = self.client.get(
            "/api/v1/telegram-auth",
            headers={"X-TeleRelay-Account-ID": body["id"]},
        )
        self.assertEqual(auth_state.status_code, 200)
        self.assertEqual(auth_state.json()["state"], "success")

        runtime = self.bot.get_runtime(body["id"])
        runtime.is_running = False
        with patch("backend.telegram_accounts.TelegramClientManager", FakeClientManager):
            updated = self.client.put(
                f"/api/v1/telegram-accounts/{body['id']}/bot-token",
                json={"bot_token": "987654321:BB" + "y" * 30},
            )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["code"], "bot_token_updated")
        self.assertEqual(
            self.account_store.get_bot_token(body["id"]),
            "987654321:BB" + "y" * 30,
        )
        self.assertTrue(runtime.is_running)

    def test_bot_account_create_surfaces_auth_failure(self):
        class FailingClientManager:
            def __init__(
                self,
                config,
                auth_manager=None,
                session_name=None,
                on_user_authenticated=None,
                bot_token=None,
            ):
                self.session_name = Path(session_name)

            async def connect(self):
                return False

            async def disconnect(self):
                return None

        with patch("backend.telegram_accounts.TelegramClientManager", FailingClientManager):
            response = self.client.post(
                "/api/v1/telegram-accounts",
                json={
                    "label": "Broken Bot",
                    "kind": "bot",
                    "bot_token": "123456789:AA" + "x" * 30,
                },
            )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "bot_auth_failed")
        accounts = self.client.get("/api/v1/telegram-accounts").json()
        self.assertEqual([account["id"] for account in accounts], [self.account_id])
        self.assertTrue(accounts[0]["active"])
        token_directory = self.account_store.data_dir / "bot_tokens"
        self.assertEqual(list(token_directory.glob("*.token")), [])

    def test_bot_token_update_keeps_current_token_when_verification_fails(self):
        class SuccessfulClientManager:
            def __init__(
                self,
                config,
                auth_manager=None,
                session_name=None,
                on_user_authenticated=None,
                bot_token=None,
            ):
                self.session_name = Path(session_name)
                self.on_user_authenticated = on_user_authenticated

            async def connect(self):
                Path(f"{self.session_name}.session").write_bytes(b"fake-session")
                if self.on_user_authenticated:
                    self.on_user_authenticated(
                        {
                            "display_name": "Relay Bot",
                            "username": "relay_bot",
                            "telegram_user_id": 777001,
                        }
                    )
                return True

            async def disconnect(self):
                return None

        class FailingClientManager(SuccessfulClientManager):
            async def connect(self):
                return False

        original_token = "123456789:AA" + "x" * 30
        with patch(
            "backend.telegram_accounts.TelegramClientManager",
            SuccessfulClientManager,
        ):
            created = self.client.post(
                "/api/v1/telegram-accounts",
                json={
                    "label": "Relay Bot",
                    "kind": "bot",
                    "bot_token": original_token,
                },
            ).json()

        runtime = self.bot.get_runtime(created["id"])
        runtime.is_running = True
        runtime.restarts = 0
        with patch(
            "backend.telegram_accounts.TelegramClientManager",
            FailingClientManager,
        ):
            response = self.client.put(
                f"/api/v1/telegram-accounts/{created['id']}/bot-token",
                json={"bot_token": "987654321:BB" + "y" * 30},
            )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"]["code"], "bot_auth_failed")
        self.assertEqual(self.account_store.get_bot_token(created["id"]), original_token)
        self.assertEqual(runtime.bot_token, original_token)
        self.assertEqual(runtime.restarts, 0)

    def test_bot_account_requires_token(self):
        response = self.client.post(
            "/api/v1/telegram-accounts",
            json={"label": "Broken Bot", "kind": "bot"},
        )
        self.assertEqual(response.status_code, 422)

    def test_telegram_account_name_can_be_updated(self):
        updated = self.client.put(
            f"/api/v1/telegram-accounts/{self.account_id}",
            json={"label": "Primary account"},
        )

        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["label"], "Primary account")
        listed = self.client.get("/api/v1/telegram-accounts").json()
        self.assertEqual(listed[0]["label"], "Primary account")

    def test_telegram_account_avatar_contract(self):
        missing = self.client.get(
            f"/api/v1/telegram-accounts/{self.account_id}/avatar"
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["code"], "avatar_not_found")

        self.account_store.update_avatar(self.account_id, b"fake-jpeg-avatar")
        response = self.client.get(
            f"/api/v1/telegram-accounts/{self.account_id}/avatar"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(response.content, b"fake-jpeg-avatar")
        account = self.client.get("/api/v1/telegram-accounts").json()[0]
        self.assertIsNotNone(account["avatar_version"])

    def test_telegram_account_refresh_contract(self):
        refreshed = {
            **self.account_store.get_public(self.account_id),
            "display_name": "Updated Account",
            "avatar_version": "updated-avatar-version",
        }
        with patch.object(
            self.accounts,
            "refresh_identity",
            AsyncMock(return_value=refreshed),
        ) as refresh_identity:
            response = self.client.post(
                f"/api/v1/telegram-accounts/{self.account_id}/refresh"
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["avatar_version"], "updated-avatar-version")
        refresh_identity.assert_awaited_once_with(self.account_id)

    def test_telegram_account_chats_contract(self):
        response = self.client.get(
            f"/api/v1/telegram-accounts/{self.account_id}/chats"
        )

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
        self.assertEqual(self.telegram_chats.calls, [("list", self.account_id)])
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
        self.assertEqual(self.telegram_chats.calls, [("get", self.account_id, -1001)])
        self.assertEqual(self.exports.message_export["chat_title"], "Release Room")

    def test_telegram_preview_dialog_and_message_contracts(self):
        dialogs = self.client.get(
            "/api/v1/telegram-preview/dialogs",
            params={"account_id": self.account_id, "folder": "archived", "limit": 25},
        )
        messages = self.client.get(
            "/api/v1/telegram-preview/chats/-1001/messages",
            params={"account_id": self.account_id, "query": "release"},
        )
        message = self.client.get(
            "/api/v1/telegram-preview/chats/-1001/messages/12",
            params={"account_id": self.account_id},
        )
        sent = self.client.post(
            "/api/v1/telegram-preview/chats/-1001/messages",
            headers={"X-TeleRelay-Account-ID": self.account_id},
            json={"text": "  release sent  "},
        )

        self.assertEqual(dialogs.status_code, 200, dialogs.text)
        self.assertEqual(dialogs.json()["folder"], "archived")
        self.assertEqual(messages.status_code, 200, messages.text)
        self.assertEqual(messages.json()["chat"]["id"], -1001)
        self.assertEqual(message.status_code, 200, message.text)
        self.assertEqual(message.json()["id"], 12)
        self.assertEqual(sent.status_code, 201, sent.text)
        self.assertEqual(sent.json()["text"], "release sent")
        self.assertEqual(
            self.telegram_preview.calls,
            [
                (
                    "dialogs",
                    {
                        "account_id": self.account_id,
                        "folder": "archived",
                        "limit": 25,
                        "cursor": None,
                    },
                ),
                (
                    "messages",
                    {
                        "account_id": self.account_id,
                        "chat_id": -1001,
                        "limit": 40,
                        "before_id": None,
                        "query": "release",
                    },
                ),
                (
                    "message",
                    {
                        "account_id": self.account_id,
                        "chat_id": -1001,
                        "message_id": 12,
                    },
                ),
                (
                    "send_message",
                    {
                        "account_id": self.account_id,
                        "chat_id": -1001,
                        "text": "release sent",
                    },
                ),
            ],
        )

    def test_telegram_preview_send_rejects_non_text_payloads(self):
        whitespace = self.client.post(
            "/api/v1/telegram-preview/chats/-1001/messages",
            json={"text": "   "},
        )
        media = self.client.post(
            "/api/v1/telegram-preview/chats/-1001/messages",
            json={"text": "hello", "media": "file.jpg"},
        )
        too_long = self.client.post(
            "/api/v1/telegram-preview/chats/-1001/messages",
            json={"text": "x" * 4097},
        )

        self.assertEqual(whitespace.status_code, 422)
        self.assertEqual(media.status_code, 422)
        self.assertEqual(too_long.status_code, 422)

    def test_telegram_video_ticket_contract(self):
        ticket = self.client.post(
            "/api/v1/telegram-preview/chats/-1001/messages/12/video-ticket",
            headers={"X-TeleRelay-Account-ID": self.account_id},
        )
        self.assertEqual(ticket.status_code, 200, ticket.text)
        self.assertEqual(ticket.json()["ticket"], "video-ticket-123")
        self.assertEqual(ticket.headers["cache-control"], "no-store")
        self.assertEqual(
            self.telegram_media.calls[:1],
            [
                (
                    "video_ticket",
                    {
                        "account_id": self.account_id,
                        "chat_id": -1001,
                        "message_id": 12,
                    },
                ),
            ],
        )

    def test_telegram_preview_bot_commands_and_updates_contracts(self):
        commands = self.client.get(
            "/api/v1/telegram-preview/chats/303/bot-commands",
            headers={"X-TeleRelay-Account-ID": self.account_id},
        )
        updates = self.client.get(
            "/api/v1/telegram-preview/updates",
            headers={"X-TeleRelay-Account-ID": self.account_id},
        )

        self.assertEqual(commands.status_code, 200, commands.text)
        self.assertEqual(commands.json()["items"][0]["command"], "start")
        self.assertEqual(updates.status_code, 200, updates.text)
        self.assertIn("event: ready", updates.text)
        self.assertIn('"message_id": 13', updates.text)
        self.assertIn(
            (
                "bot_commands",
                {"account_id": self.account_id, "chat_id": 303},
            ),
            self.telegram_preview.calls,
        )
        self.assertIn(
            ("updates", {"account_id": self.account_id}),
            self.telegram_preview.calls,
        )

    def test_telegram_preview_bot_commands_preserve_structured_errors(self):
        self.telegram_preview.list_bot_commands = AsyncMock(
            side_effect=TelegramPreviewError(
                "bot_commands_unavailable",
                "Telegram bot commands are unavailable",
            )
        )

        response = self.client.get(
            "/api/v1/telegram-preview/chats/303/bot-commands",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            {
                "code": "bot_commands_unavailable",
                "message": "Telegram bot commands are unavailable",
            },
        )

    def test_telegram_preview_send_preserves_structured_errors(self):
        self.telegram_preview.send_text_message = AsyncMock(
            side_effect=TelegramPreviewError(
                "message_send_failed",
                "Telegram could not send the text message",
            )
        )

        response = self.client.post(
            "/api/v1/telegram-preview/chats/-1001/messages",
            json={"text": "hello"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            {
                "code": "message_send_failed",
                "message": "Telegram could not send the text message",
            },
        )

    def test_telegram_preview_send_maps_flood_wait_to_429(self):
        self.telegram_preview.send_text_message = AsyncMock(
            side_effect=TelegramPreviewError(
                "flood_wait",
                "Telegram rate limited, retry in 5s",
            )
        )

        response = self.client.post(
            "/api/v1/telegram-preview/chats/-1001/messages",
            json={"text": "hello"},
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response.json()["detail"],
            {
                "code": "flood_wait",
                "message": "Telegram rate limited, retry in 5s",
            },
        )

    def test_telegram_preview_send_maps_write_forbidden_to_403(self):
        self.telegram_preview.send_text_message = AsyncMock(
            side_effect=TelegramPreviewError(
                "chat_write_forbidden",
                "Telegram denied sending to this chat",
            )
        )

        response = self.client.post(
            "/api/v1/telegram-preview/chats/-1001/messages",
            json={"text": "hello"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["code"],
            "chat_write_forbidden",
        )

    def test_config_schema_drives_known_fields_and_preserves_extensions(self):
        response = self.client.get("/api/v1/config")

        self.assertEqual(response.status_code, 200, response.text)
        schema = response.json()["schema"]
        definitions = schema["$defs"]
        self.assertTrue(schema["additionalProperties"])
        self.assertEqual(next(iter(schema["properties"])), "session_type")
        self.assertEqual(
            definitions["ConfigFilter"]["properties"]["mode"]["enum"],
            ["whitelist", "blacklist"],
        )
        self.assertEqual(
            definitions["ConfigForwardQueue"]["properties"]["max_retries"]["maximum"],
            100,
        )
        self.assertEqual(
            definitions["ConfigIgnore"]["properties"]["user_ids"]["x-item-control"],
            "integer-tags",
        )
        self.assertTrue(
            definitions["ConfigExport"]["properties"]["root_dir"]["readOnly"]
        )

        saved = self.client.put(
            "/api/v1/config",
            json={
                "config": {
                    "forwarding": {"delay": 1.5},
                    "legacy_extension": {"strategy": "custom"},
                }
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(
            self.config.config_data["legacy_extension"], {"strategy": "custom"}
        )

    def test_config_put_and_import_share_schema_validation(self):
        replaced = self.client.put(
            "/api/v1/config",
            json={"config": {"forward_queue": {"max_retries": 101}}},
        )
        imported = self.client.post(
            "/api/v1/config/import",
            files={
                "file": (
                    "invalid.yaml",
                    "filters:\n  mode: unsupported\n",
                    "application/yaml",
                )
            },
        )

        self.assertEqual(replaced.status_code, 422, replaced.text)
        self.assertEqual(replaced.json()["detail"]["code"], "invalid_config")
        self.assertIn("forward_queue.max_retries", replaced.json()["detail"]["message"])
        self.assertEqual(imported.status_code, 422, imported.text)
        self.assertEqual(imported.json()["detail"]["code"], "invalid_config")
        self.assertIn("filters.mode", imported.json()["detail"]["message"])

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
