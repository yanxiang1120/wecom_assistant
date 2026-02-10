import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def _parse_log_level(log_level: str) -> int:
    level_name = (log_level or "INFO").upper()
    level_value = getattr(logging, level_name, None)
    if isinstance(level_value, int):
        return level_value
    return logging.INFO


def _parse_backup_days(backup_days: int | str) -> int:
    try:
        value = int(backup_days)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return 30


def setup_logging(
    log_dir: str = "logs",
    logger_name: str = "assistant",
    log_level: str = "INFO",
    backup_days: int | str = 30,
) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / "service.log"

    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=_parse_backup_days(backup_days),
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
    file_handler.setLevel(_parse_log_level(log_level))

    logger.setLevel(_parse_log_level(log_level))
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger
