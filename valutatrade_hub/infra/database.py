import copy
import json
import os
import tempfile
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    """Предоставляет общий доступ к JSON-файлам приложения."""

    _instance = None

    def __new__(cls):
        """Создаёт один менеджер через простой Singleton на __new__."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, settings=None):
        """Создаёт отсутствующие файлы базы, сохраняя существующие данные."""
        settings = settings or SettingsLoader()
        defaults = {
            "users_file": [],
            "portfolios_file": [],
            "history_file": [],
            "rates_file": {"pairs": {}, "last_refresh": None},
        }
        for key, default in defaults.items():
            filepath = settings.get(key)
            if not Path(filepath).exists():
                self.write_json(filepath, default)

    def read_json(self, filepath, default):
        """Читает JSON; для отсутствующего файла возвращает копию default."""
        try:
            with open(filepath, encoding="utf-8") as source:
                return json.load(source)
        except FileNotFoundError:
            return copy.deepcopy(default)
        except json.JSONDecodeError as error:
            raise ValueError(f"Некорректный JSON в файле {filepath}.") from error

    def write_json(self, filepath, data):
        """Сохраняет JSON атомарной заменой временного файла."""
        destination = Path(filepath)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as output:
                temporary = output.name
                json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
