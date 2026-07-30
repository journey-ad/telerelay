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


class FakeBot:
    def __init__(self):
        self.is_running = False
        self.restarts = 0

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

    def get_status(self):
        return {
            "is_running": self.is_running,
            "is_connected": False,
            "stats": {"forwarded": 0, "filtered": 0, "total": 0},
            "queue": {"counts": {}, "paused_until": 0, "pause_reason": None},
        }

    def reset_stats(self):
        return None


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
        self.bot = FakeBot()
        self.auth = AuthManager(input_timeout=1)
        self.events = EventBus()
        self.rules = RuleService(self.config, self.bot)
        self.context = ApplicationContext(
            config=self.config,
            auth=self.auth,
            bot=self.bot,
            exports=SimpleNamespace(),
            scheduler=SimpleNamespace(),
            rules=self.rules,
            events=self.events,
            log_handler=SimpleNamespace(),
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
