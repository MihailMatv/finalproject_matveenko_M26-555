"""Сохранение текущих курсов и истории измерений."""

from datetime import UTC, datetime

from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.parser_service.api_clients import positive_rate
from valutatrade_hub.parser_service.config import ParserConfig


def parse_timestamp(value):
    """Разбирает ISO-время, считая время без пояса временем UTC."""
    if not isinstance(value, str):
        raise ValueError("Время курса должно быть строкой ISO.")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    )


class RateStorage:
    """Записывает историю без дублей и последний срез по каждой паре."""

    def __init__(self, config=None, database=None):
        """Принимает общие настройки и файловое хранилище."""
        self.config = config or ParserConfig()
        self.database = database or DatabaseManager()

    def load_rates(self):
        """Читает снимок; поддерживает также исходный плоский формат ТЗ."""
        data = self.database.read_json(self.config.RATES_FILE_PATH, {})
        if not isinstance(data, dict):
            raise ValueError("Некорректный формат файла курсов.")
        if "pairs" in data:
            if not isinstance(data["pairs"], dict):
                raise ValueError("Некорректный список валютных пар.")
            return data
        pairs = {
            key: value
            for key, value in data.items()
            if isinstance(value, dict) and "rate" in value
        }
        return {"pairs": pairs, "last_refresh": data.get("last_refresh")}

    def save_rates(self, pairs, refreshed_at=None):
        """Обновляет только более свежие срезы, сохраняя все новые измерения."""
        snapshot = self.load_rates()
        history = self.database.read_json(self.config.HISTORY_FILE_PATH, [])
        if not isinstance(history, list):
            raise ValueError("История курсов должна быть списком.")
        known_ids = {record["id"] for record in history}
        measurements = []
        for pair, values in pairs.items():
            codes = pair.split("_")
            if len(codes) != 2 or any(
                not code.isascii()
                or not code.isalpha()
                or not code.isupper()
                or not 2 <= len(code) <= 5
                for code in codes
            ):
                raise ValueError(f"Некорректная валютная пара: {pair}.")
            updated_at = parse_timestamp(values["updated_at"])
            source = values["source"]
            if not isinstance(source, str) or not source.strip():
                raise ValueError("Не указан источник курса.")
            rate = positive_rate(values["rate"])
            stamp = updated_at.isoformat()
            record = {
                "id": f"{pair}_{stamp}",
                "from_currency": codes[0],
                "to_currency": codes[1],
                "rate": rate,
                "timestamp": stamp,
                "source": source,
                "meta": values.get("meta", {}),
            }
            measurements.append((pair, record))

        for pair, record in measurements:
            if record["id"] not in known_ids:
                history.append(record)
                known_ids.add(record["id"])
            previous = snapshot["pairs"].get(pair)
            if previous is None or parse_timestamp(
                record["timestamp"]
            ) > parse_timestamp(previous["updated_at"]):
                snapshot["pairs"][pair] = {
                    "rate": record["rate"],
                    "updated_at": record["timestamp"],
                    "source": record["source"],
                }

        refresh = refreshed_at or datetime.now(UTC).isoformat(timespec="seconds")
        parse_timestamp(refresh)
        old_refresh = snapshot.get("last_refresh")
        if old_refresh is None or parse_timestamp(refresh) > parse_timestamp(
            old_refresh
        ):
            snapshot["last_refresh"] = refresh
        self.database.write_json(self.config.HISTORY_FILE_PATH, history)
        self.database.write_json(self.config.RATES_FILE_PATH, snapshot)
        return snapshot
