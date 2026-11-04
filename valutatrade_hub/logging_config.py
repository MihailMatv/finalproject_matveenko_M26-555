import json
import logging
import math
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

LOGGER_FILES = {
    "valutatrade.actions": "actions.log",
    "valutatrade.parser": "parser.log",
}


class JsonLogFormatter(logging.Formatter):
    """Преобразует каждую запись журнала в одну строку JSON."""

    def format(self, record):
        """Добавляет время и уровень к сообщению или полям операции."""
        fields = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
        }
        if isinstance(record.msg, dict):
            fields.update(record.msg)
        else:
            fields["message"] = record.getMessage()
        for key, value in fields.items():
            if isinstance(value, float) and not math.isfinite(value):
                fields[key] = str(value)
        return json.dumps(fields, ensure_ascii=False, default=str, allow_nan=False)


def setup_logging(settings=None):
    """Настраивает JSON-журналы операций и парсера с ротацией."""
    settings = settings or SettingsLoader()
    directory = Path(settings.get("logs_dir"))
    directory.mkdir(parents=True, exist_ok=True)
    level = settings.get("log_level", "INFO").upper()
    for name, filename in LOGGER_FILES.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        destination = str((directory / filename).resolve())
        if (
            len(logger.handlers) == 1
            and getattr(logger.handlers[0], "baseFilename", None) == destination
        ):
            continue
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
        handler = RotatingFileHandler(
            destination,
            maxBytes=settings.get("log_max_bytes"),
            backupCount=settings.get("log_backup_count"),
            encoding="utf-8",
        )
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
