import logging
import tempfile
import unittest
from pathlib import Path

from lychee_basic_client.observability.logging_setup import get_logger, setup_logging


class LoggingSetupTests(unittest.TestCase):
    def test_logs_are_split_by_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            setup_logging(tmp_dir, "DEBUG")
            logger = get_logger("tests")

            logger.info("debugging details")
            logger.important("match started")
            logger.error("boom")
            logging.shutdown()

            info_log = Path(tmp_dir) / "info.log"
            important_log = Path(tmp_dir) / "important.log"
            error_log = Path(tmp_dir) / "error.log"

            self.assertIn("debugging details", info_log.read_text(encoding="utf-8"))
            self.assertIn("match started", important_log.read_text(encoding="utf-8"))
            self.assertIn("boom", error_log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

