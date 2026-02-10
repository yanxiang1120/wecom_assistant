import os

from app.logging_setup import setup_logging


def get_wechat_logger():
    return setup_logging(
        log_dir=os.getenv("LOG_DIR", "logs"),
        logger_name="wechat",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        backup_days=os.getenv("LOG_BACKUP_DAYS", "30"),
    )
