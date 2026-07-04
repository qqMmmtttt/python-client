import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lychee_basic_client import config as config_module


class ConfigTests(unittest.TestCase):
    def test_parse_args_reads_strategy_profile_from_file_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "strategy_config.json"
            config_path.write_text(
                '{"route_profile": "auto", "strategy_profile": "fastest-wuguan"}',
                encoding="utf-8",
            )

            with patch.object(config_module, "STRATEGY_CONFIG_PATH", config_path), patch(
                "sys.argv",
                ["basic_client.py", "--player-id", "1001", "--host", "127.0.0.1", "--port", "30000"],
            ):
                config = config_module.parse_args()

        self.assertEqual("auto", config.route_profile)
        self.assertEqual("fastest-wuguan", config.strategy_profile)

    def test_parse_args_keeps_default_strategy_when_file_is_missing(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "missing-lychee-strategy-config.json"
        with patch.object(config_module, "STRATEGY_CONFIG_PATH", missing_path), patch(
            "sys.argv",
            ["basic_client.py", "--player-id", "1001", "--host", "127.0.0.1", "--port", "30000"],
        ):
            config = config_module.parse_args()

        self.assertEqual("speed-priority", config.route_profile)
        self.assertEqual("wuguan-trap", config.strategy_profile)


if __name__ == "__main__":
    unittest.main()
