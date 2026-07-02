import logging
from pathlib import Path
from typing import Any

IMPORTANT_LEVEL = 25
PACKAGE_LOGGER_NAME = "lychee_basic_client"


class _ExactLevelFilter(logging.Filter):
    def __init__(self, level: int) -> None:
        super().__init__()
        self._level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self._level


class _LevelRangeFilter(logging.Filter):
    def __init__(self, low: int, high: int) -> None:
        super().__init__()
        self._low = low
        self._high = high

    def filter(self, record: logging.LogRecord) -> bool:
        return self._low <= record.levelno <= self._high


def _important(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    if self.isEnabledFor(IMPORTANT_LEVEL):
        self._log(IMPORTANT_LEVEL, message, args, **kwargs)


def _install_important_level() -> None:
    logging.addLevelName(IMPORTANT_LEVEL, "IMPORTANT")
    if not hasattr(logging.Logger, "important"):
        setattr(logging.Logger, "important", _important)


_install_important_level()


def setup_logging(log_dir: str, level_name: str = "INFO") -> logging.Logger:
    _install_important_level()

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    info_handler = logging.FileHandler(log_path / "info.log", encoding="utf-8")
    info_handler.setLevel(logging.DEBUG)
    info_handler.addFilter(_LevelRangeFilter(logging.DEBUG, logging.INFO))
    info_handler.setFormatter(formatter)

    important_handler = logging.FileHandler(log_path / "important.log", encoding="utf-8")
    important_handler.setLevel(IMPORTANT_LEVEL)
    important_handler.addFilter(_ExactLevelFilter(IMPORTANT_LEVEL))
    important_handler.setFormatter(formatter)

    error_handler = logging.FileHandler(log_path / "error.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logger.level)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logger.addHandler(info_handler)
    logger.addHandler(important_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{PACKAGE_LOGGER_NAME}.{name}")
