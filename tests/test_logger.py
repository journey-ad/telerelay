import logging
import unittest

from backend.logger import AccountTagFilter, account_log_context, run_with_account_log_context


class LoggerContextTests(unittest.TestCase):
    def setUp(self):
        self.filter = AccountTagFilter()

    def test_system_logs_have_system_tag(self):
        record = logging.LogRecord("telerelay", logging.INFO, __file__, 1, "message", (), None)

        self.assertTrue(self.filter.filter(record))
        self.assertEqual(record.account_id, None)
        self.assertEqual(record.account_tag, "system")

    def test_account_context_adds_account_tag(self):
        record = logging.LogRecord("telerelay", logging.INFO, __file__, 1, "message", (), None)

        with account_log_context("89336672"):
            self.assertTrue(self.filter.filter(record))

        self.assertEqual(record.account_id, "89336672")
        self.assertEqual(record.account_tag, "account:89336672")

    def test_account_context_is_propagated_to_worker_callback(self):
        def capture():
            record = logging.LogRecord(
                "telerelay", logging.INFO, __file__, 1, "message", (), None
            )
            self.filter.filter(record)
            return record.account_tag

        self.assertEqual(
            run_with_account_log_context("8999284276", capture),
            "account:8999284276",
        )


if __name__ == "__main__":
    unittest.main()
