"""
Logging Configuration
=====================

Root logging setup: console output plus a rotating log file.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from app.core.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILENAME = "lighting.log"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

# Loggers that emit per-frame/per-request noise once the root level drops to DEBUG.
NOISY_LOGGERS = (
    "asyncio",
    "urllib3",
    "httpx",
    "httpcore",
    "watchfiles",
    "PIL",
    "matplotlib",
    "numba",
)


def get_log_dir() -> Path:
    """Return the directory log files are written to (next to the database)."""
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            return Path(db_path).resolve().parent / "logs"
    return Path(__file__).resolve().parents[2] / "logs"


def configure_logging() -> Optional[Path]:
    """Install console and rotating file handlers on the root logger.

    Returns the active log file path, or None if file logging is unavailable.
    """
    level = logging.DEBUG if settings.DEBUG else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        if getattr(handler, "_ils_managed", False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    console._ils_managed = True
    root.addHandler(console)

    log_file: Optional[Path] = None
    try:
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / LOG_FILENAME
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler._ils_managed = True
        root.addHandler(file_handler)
    except OSError as e:
        log_file = None
        root.warning("File logging unavailable (%s) - console only", e)

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(level, logging.INFO))
    # SQLAlchemy and aiosqlite echo every statement when left at DEBUG.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    root.info(
        "Logging configured (level=%s, file=%s)",
        logging.getLevelName(level),
        log_file,
    )
    return log_file
