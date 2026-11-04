"""Настройки источников курсов и файлов Parser Service."""

import os
from dataclasses import dataclass, field

from valutatrade_hub.infra.settings import SettingsLoader


@dataclass
class ParserConfig:
    """Хранит параметры запросов; ключи берутся из окружения."""

    EXCHANGERATE_API_KEY: str = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY", "")
    )
    COINGECKO_API_KEY: str = field(
        default_factory=lambda: os.getenv("COINGECKO_API_KEY", "")
    )
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"
    EXCHANGERATE_OPEN_URL: str = "https://open.er-api.com/v6/latest"
    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict = field(
        default_factory=lambda: {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
    )
    REQUEST_TIMEOUT: float = 10
    UPDATE_INTERVAL_SECONDS: float = 300
    RATES_FILE_PATH: str = field(
        default_factory=lambda: SettingsLoader().get("rates_file", "data/rates.json")
    )
    HISTORY_FILE_PATH: str = field(
        default_factory=lambda: SettingsLoader().get(
            "history_file", "data/exchange_rates.json"
        )
    )
