import socket

from .config import parse_args
from .observability.logging_setup import get_logger, setup_logging
from .session import ClientSession


def main() -> int:
    config = parse_args()
    setup_logging(config.log_dir, config.log_level)
    logger = get_logger("cli")
    with socket.create_connection((config.host, config.port)) as sock:
        logger.important(
            "connected to %s:%s as player %s",
            config.host,
            config.port,
            config.player_id,
        )
        return ClientSession(sock, config).run()
