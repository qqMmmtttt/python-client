import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    player_id: int
    player_name: str
    version: str
    log_dir: str = "logs"
    log_level: str = "INFO"
    route_profile: str = "auto"


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
        choices=["auto", "first-round-safe", "generic"],
        default="auto",
        help="Route policy profile. auto uses dynamic routing; first-round-safe keeps the first-round land route.",
    )
    args = parser.parse_args()
    return Config(
        host=args.host,
        port=args.port,
        player_id=args.player_id,
        player_name=args.player_name,
        version=args.version,
        log_dir=args.log_dir,
        log_level=args.log_level,
        route_profile=args.route_profile,
    )
