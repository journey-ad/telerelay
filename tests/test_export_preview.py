import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from backend.exporter.service import ExportService, ExportValidationError


def make_service(root: Path) -> ExportService:
    config = SimpleNamespace(
        export_root_dir=str(root / "exports"),
        export_message_db_dir=str(root / "db"),
        export_concurrency=1,
        session_type="user",
    )
    return ExportService(
        config,
        bot_manager=None,
        source=SimpleNamespace(),
        store=SimpleNamespace(),
    )


class ExportPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.exports = self.root / "exports"
        self.exports.mkdir(parents=True)
        self.zip_path = self.exports / "chat.html.zip"
        with zipfile.ZipFile(self.zip_path, "w") as archive:
            archive.writestr("chat/index.html", "<html>hello</html>")
            archive.writestr("chat/manifest.js", "const x = 1;")

    def test_token_round_trip_resolves_archive(self):
        service = make_service(self.root)
        token = service.create_preview_token(self.zip_path)
        self.assertEqual(service.resolve_preview_token(token), self.zip_path.resolve())

    def test_token_rejects_file_outside_export_root(self):
        outside = self.root / "outside.html.zip"
        outside.write_text("x")
        service = make_service(self.root)
        with self.assertRaises(ExportValidationError):
            service.create_preview_token(outside)

    def test_token_rejects_non_html_zip(self):
        plain = self.exports / "notes.zip"
        plain.write_text("x")
        service = make_service(self.root)
        with self.assertRaises(ExportValidationError):
            service.create_preview_token(plain)

    def test_invalid_token_resolves_none(self):
        service = make_service(self.root)
        self.assertIsNone(service.resolve_preview_token("bogus"))

    def test_read_archive_file_returns_inner_file(self):
        service = make_service(self.root)
        content = service.read_archive_file(self.zip_path, "chat/index.html")
        self.assertEqual(content, b"<html>hello</html>")

    def test_read_archive_file_falls_back_to_any_index_html(self):
        service = make_service(self.root)
        content = service.read_archive_file(self.zip_path, "index.html")
        self.assertEqual(content, b"<html>hello</html>")

    def test_read_archive_file_rejects_traversal(self):
        service = make_service(self.root)
        self.assertIsNone(service.read_archive_file(self.zip_path, "../secret.txt"))
        self.assertIsNone(service.read_archive_file(self.zip_path, "/etc/passwd"))


if __name__ == "__main__":
    unittest.main()
