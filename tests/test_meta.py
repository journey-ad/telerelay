import io
import json
import os
import unittest
from types import SimpleNamespace
from urllib import error as url_error
from unittest.mock import patch

from backend.meta import (
    _short_hash,
    _version_tuple,
    check_update,
    current_commit,
    current_version,
)


class VersionParsingTests(unittest.TestCase):
    def test_version_tuple_strips_v_prefix(self):
        self.assertEqual(_version_tuple("v2.1.0"), (2, 1, 0))
        self.assertEqual(_version_tuple("2.0.0"), (2, 0, 0))

    def test_version_ordering_prefers_latest(self):
        self.assertGreater(_version_tuple("v2.1.0"), _version_tuple("2.0.0"))
        self.assertLess(_version_tuple("2.0.0"), _version_tuple("v2.1.0"))

    def test_current_version_prefers_environment_override(self):
        with patch.dict(os.environ, {"TELERELAY_VERSION": "v9.9.9"}, clear=False):
            self.assertEqual(current_version(), "v9.9.9")

    def test_current_version_reads_version_file(self):
        with patch.dict(os.environ, {}, clear=False), patch(
            "backend.meta.VERSION_FILE"
        ) as version_file:
            version_file.is_file.return_value = True
            version_file.read_text.return_value = "2.0.0-12-g3f9a1c2\n"
            self.assertEqual(current_version(), "2.0.0-12-g3f9a1c2")

    def test_current_version_ignores_blank_version_file(self):
        from backend import __version__

        with patch.dict(os.environ, {}, clear=False), patch(
            "backend.meta.VERSION_FILE"
        ) as version_file:
            version_file.is_file.return_value = True
            version_file.read_text.return_value = "   \n"
            self.assertEqual(current_version(), __version__)

    def test_current_version_falls_back_to_package_version(self):
        from backend import __version__

        with patch.dict(os.environ, {}, clear=False), patch(
            "backend.meta.VERSION_FILE"
        ) as version_file:
            version_file.is_file.return_value = False
            self.assertEqual(current_version(), __version__)

    def test_short_hash_truncates_full_sha(self):
        self.assertEqual(_short_hash("0123456789abcdef"), "0123456")
        self.assertEqual(_short_hash("abc1234"), "abc1234")

    def test_current_commit_prefers_environment_override(self):
        current_commit.cache_clear()
        with patch.dict(os.environ, {"TELERELAY_COMMIT": "0123456789abcdef"}, clear=False):
            try:
                self.assertEqual(current_commit(), "0123456")
            finally:
                current_commit.cache_clear()

    def test_current_commit_reads_git_head(self):
        current_commit.cache_clear()
        with patch.dict(os.environ, {}, clear=False), patch(
            "backend.meta.COMMIT_FILE"
        ) as commit_file, patch(
            "backend.meta.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="abcdef0123\n"),
        ):
            commit_file.is_file.return_value = False
            try:
                self.assertEqual(current_commit(), "abcdef0")
            finally:
                current_commit.cache_clear()


class UpdateCheckTests(unittest.TestCase):
    def release_response(self, release):
        return io.BytesIO(json.dumps(release).encode())

    def test_update_available_from_version_info(self):
        release = {
            "version": "v2.1.0",
            "tag_name": "v2.1.0",
            "date": "2026-07-31",
            "published_at": "2026-07-31T00:00:00Z",
            "url": "https://github.com/journey-ad/telerelay/releases/tag/v2.1.0",
            "homepage": "https://github.com/journey-ad/telerelay",
            "repository": "https://github.com/journey-ad/telerelay.git",
            "image": "ghcr.io/journey-ad/telerelay:v2.1.0",
        }
        with patch("backend.meta.current_version", return_value="2.0.0"), patch(
            "backend.meta.url_request.urlopen", return_value=self.release_response(release)
        ):
            info = check_update()
        self.assertTrue(info.update_available)
        self.assertEqual(info.latest_tag, "v2.1.0")
        self.assertEqual(info.latest_version, "2.1.0")
        self.assertEqual(info.published_at, "2026-07-31")
        self.assertEqual(info.repository, "https://github.com/journey-ad/telerelay.git")
        self.assertEqual(info.image, "ghcr.io/journey-ad/telerelay:v2.1.0")
        self.assertIsNone(info.error)

    def test_up_to_date_when_current_is_latest(self):
        release = {"tag_name": "v2.0.0"}
        with patch("backend.meta.current_version", return_value="2.0.0"), patch(
            "backend.meta.url_request.urlopen", return_value=self.release_response(release)
        ):
            info = check_update()
        self.assertFalse(info.update_available)

    def test_http_error_is_reported(self):
        with patch("backend.meta.current_version", return_value="2.0.0"), patch(
            "backend.meta.url_request.urlopen",
            side_effect=url_error.HTTPError(
                "https://api.github.com", 404, "Not Found", {}, io.BytesIO()
            ),
        ):
            info = check_update()
        self.assertEqual(info.error, "HTTP 404")
        self.assertFalse(info.update_available)

    def test_network_error_is_reported(self):
        with patch("backend.meta.current_version", return_value="2.0.0"), patch(
            "backend.meta.url_request.urlopen", side_effect=url_error.URLError("offline")
        ):
            info = check_update()
        self.assertIsNotNone(info.error)
        self.assertFalse(info.update_available)
