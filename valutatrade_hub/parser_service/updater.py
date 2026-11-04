"""Обновление курсов с независимой обработкой источников."""

import logging
from datetime import UTC, datetime

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
    positive_rate,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RateStorage

logger = logging.getLogger("valutatrade.parser")


class RatesUpdater:
    """Получает курсы всех доступных источников и передаёт их хранилищу."""

    def __init__(self, clients=None, storage=None, config=None):
        """Разрешает подменить клиентов и хранилище для проверок."""
        self.config = config or ParserConfig()
        self.clients = (
            clients
            if clients is not None
            else [CoinGeckoClient(self.config), ExchangeRateApiClient(self.config)]
        )
        self.storage = storage or RateStorage(self.config)

    def run_update(self, source=None):
        """Обновляет выбранные источники; ошибка одного не отменяет остальные."""
        if source not in (None, "coingecko", "exchangerate"):
            raise ValueError("Источник должен быть coingecko или exchangerate.")
        logger.info("Starting rates update")
        pairs = {}
        errors = []
        for client in self.clients:
            client_source = client.source.lower().replace("-api", "")
            if source is not None and source != client_source:
                continue
            try:
                rates = client.fetch_rates()
                if not isinstance(rates, dict) or not rates:
                    raise ApiRequestError(
                        f"{client.source}: получен пустой список курсов"
                    )
                updated_at = getattr(client, "updated_at", None) or datetime.now(
                    UTC
                ).isoformat(timespec="seconds")
                current = {
                    pair: {
                        "rate": positive_rate(rate),
                        "updated_at": updated_at,
                        "source": client.source,
                        "meta": getattr(client, "metadata", {}),
                    }
                    for pair, rate in rates.items()
                }
                pairs.update(current)
                logger.info(
                    "Fetching from %s: OK (%d rates)", client.source, len(rates)
                )
            except ApiRequestError as error:
                errors.append(str(error))
                logger.warning("Failed to fetch from %s: %s", client.source, error)
        if not pairs:
            raise ApiRequestError(
                "; ".join(errors) or "Нет доступных источников курсов"
            )
        refreshed_at = datetime.now(UTC).isoformat(timespec="seconds")
        snapshot = self.storage.save_rates(pairs, refreshed_at=refreshed_at)
        logger.info("Writing %d rates: completed", len(pairs))
        return {
            "updated_count": len(pairs),
            "last_refresh": snapshot["last_refresh"],
            "errors": errors,
            "pairs": snapshot["pairs"],
        }
