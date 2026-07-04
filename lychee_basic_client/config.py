import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# strategy_config.json
# "wuguan-trap"， "fastest-wuguan"

ROUTE_PROFILE_CHOICES = (
    "speed-priority",
    "auto",
    "first-round-water",
    "first-round-safe",
    "generic",
)
STRATEGY_PROFILE_CHOICES = (
    "wuguan-trap",
    "fastest-wuguan",
    "speed-guard",
    "balanced",
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STRATEGY_CONFIG_PATH = PROJECT_ROOT / "strategy_config.json"


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    player_id: int
    player_name: str
    version: str
    log_dir: str = "logs"
    log_level: str = "INFO"
    route_profile: str = "speed-priority"
    strategy_profile: str = "wuguan-trap"


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Minimal Lychee arena Python client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=30000)
    parser.add_argument("--player-id", type=int, default=1006)
    parser.add_argument("--player-name", default="BasicPy")
    parser.add_argument("--version", default="0.1")
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument(
        "--log-level",
        choices=["TRACE", "DEBUG", "INFO", "IMPORTANT", "WARNING", "ERROR"],
        default="INFO",
    )
    parser.add_argument(
        "--route-profile",
        choices=ROUTE_PROFILE_CHOICES,
        default=None,
        help=(
            "Route policy profile. speed-priority forces the first-round water race to Wuguan; "
            "auto uses dynamic routing with weather, process, obstacle, residue and guard costs. "
            "first-round-water forces the known water route."
        ),
    )
    parser.add_argument(
        "--strategy-profile",
        choices=STRATEGY_PROFILE_CHOICES,
        default=None,
        help=(
            "Top-level strategy profile. wuguan-trap uses the staged S09/S10 guard race; "
            "fastest-wuguan dynamically races to S10 and then uses the Wuguan repeat-guard plan; "
            "speed-guard keeps the direct Wuguan guard behavior; balanced uses conservative guards."
        ),
    )
    args = parser.parse_args()
    file_config = _load_strategy_file_config(parser)
    route_profile = args.route_profile or _file_value(
        parser,
        file_config,
        "route_profile",
        ROUTE_PROFILE_CHOICES,
        "speed-priority",
    )
    strategy_profile = args.strategy_profile or _file_value(
        parser,
        file_config,
        "strategy_profile",
        STRATEGY_PROFILE_CHOICES,
        "wuguan-trap",
    )
    return Config(
        host=args.host,
        port=args.port,
        player_id=args.player_id,
        player_name=args.player_name,
        version=args.version,
        log_dir=args.log_dir,
        log_level=args.log_level,
        route_profile=route_profile,
        strategy_profile=strategy_profile,
    )


def _load_strategy_file_config(parser: argparse.ArgumentParser) -> dict[str, Any]:
    if not STRATEGY_CONFIG_PATH.exists():
        return {}
    try:
        raw = json.loads(STRATEGY_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        parser.error(f"{STRATEGY_CONFIG_PATH} is not valid JSON: {exc}")
    if not isinstance(raw, dict):
        parser.error(f"{STRATEGY_CONFIG_PATH} must contain a JSON object")
    return raw


def _file_value(
    parser: argparse.ArgumentParser,
    file_config: dict[str, Any],
    key: str,
    choices: tuple[str, ...],
    default: str,
) -> str:
    value = str(file_config.get(key) or default)
    if value not in choices:
        parser.error(
            f"{STRATEGY_CONFIG_PATH} has invalid {key}={value!r}; "
            f"expected one of {', '.join(choices)}"
        )
    return value
