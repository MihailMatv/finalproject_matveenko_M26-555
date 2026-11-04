import json
import math
import os
import tomllib
from pathlib import Path

DEFAULT_SETTINGS = {
    "data_dir": "data",
    "users_file": "data/users.json",
    "portfolios_file": "data/portfolios.json",
    "rates_file": "data/rates.json",
    "history_file": "data/exchange_rates.json",
    "rates_ttl_seconds": 300,
    "default_base_currency": "USD",
    "logs_dir": "logs",
    "log_level": "INFO",
    "log_format": "json",
    "log_max_bytes": 1_000_000,
    "log_backup_count": 3,
}
DATA_FILES = {
    "users_file": "users.json",
    "portfolios_file": "portfolios.json",
    "rates_file": "rates.json",
    "history_file": "exchange_rates.json",
}


class SettingsLoader:
    """Загружает общие настройки один раз на процесс."""

    _instance = None

    def __new__(cls):
        """Использует __new__: для одного класса это проще метакласса."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Инициализирует единственный экземпляр при первом обращении."""
        if not self._initialized:
            self.reload()

    def get(self, key, default=None):
        """Возвращает параметр или переданное значение по умолчанию."""
        return self._settings.get(key.lower(), default)

    def reload(self):
        """Перечитывает конфигурацию и переменные окружения."""
        configured_path = os.getenv("VALUTATRADE_CONFIG")
        if configured_path:
            path = Path(configured_path)
        elif Path("config.json").is_file():
            path = Path("config.json")
        else:
            path = Path("pyproject.toml")

        configured = {}
        if path.is_file():
            if path.suffix.lower() == ".toml":
                with path.open("rb") as source:
                    configured = (
                        tomllib.load(source).get("tool", {}).get("valutatrade", {})
                    )
            else:
                with path.open(encoding="utf-8") as source:
                    configured = json.load(source)
            if not isinstance(configured, dict):
                raise ValueError(
                    "Конфигурация должна быть JSON-объектом или TOML-секцией."
                )
        elif configured_path:
            raise FileNotFoundError(f"Файл конфигурации не найден: {path}")

        configured = {key.lower(): value for key, value in configured.items()}
        settings = {**DEFAULT_SETTINGS, **configured}
        data_override = os.getenv("VALUTATRADE_DATA_DIR")
        if data_override:
            settings["data_dir"] = data_override
        for key, filename in DATA_FILES.items():
            if data_override or key not in configured:
                settings[key] = str(Path(settings["data_dir"]) / filename)
        settings["logs_dir"] = os.getenv("VALUTATRADE_LOG_DIR", settings["logs_dir"])

        ttl = settings["rates_ttl_seconds"]
        if (
            isinstance(ttl, bool)
            or not isinstance(ttl, (int, float))
            or not math.isfinite(ttl)
            or ttl <= 0
        ):
            raise ValueError("rates_ttl_seconds должен быть положительным числом.")
        for key, minimum in (("log_max_bytes", 1), ("log_backup_count", 0)):
            value = settings[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{key} должен быть целым числом не меньше {minimum}.")
        if settings["log_format"] != "json":
            raise ValueError("Поддерживается формат логов json.")
        self._settings = settings
        self._initialized = True
