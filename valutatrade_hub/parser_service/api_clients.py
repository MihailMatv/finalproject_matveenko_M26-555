"""Клиенты двух API с общим форматом результата."""

import math
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


def positive_rate(value):
    """Проверяет, что API вернул положительное конечное число."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiRequestError("API вернул некорректный тип курса")
    try:
        rate = float(value)
    except OverflowError as error:
        raise ApiRequestError("API вернул слишком большое значение курса") from error
    if not math.isfinite(rate) or rate <= 0:
        raise ApiRequestError("API вернул неположительный или неконечный курс")
    return rate


class BaseApiClient(ABC):
    """Определяет единый метод получения курсов."""

    source = "API"

    def __init__(self, config=None, session=None):
        """Принимает настройки и необязательный HTTP-клиент для проверок."""
        self.config = config or ParserConfig()
        self.session = session or requests
        self.updated_at = None
        self.metadata = {}

    def _request_json(self, url, params=None, headers=None):
        """Выполняет запрос, не раскрывая URL с ключом в исключениях."""
        started = time.monotonic()
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.REQUEST_TIMEOUT,
            )
        except requests.exceptions.Timeout as error:
            raise ApiRequestError(f"{self.source}: превышено время ожидания") from error
        except requests.exceptions.RequestException as error:
            raise ApiRequestError(f"{self.source}: сетевая ошибка") from error

        status = response.status_code
        if status == 401 or status == 403:
            raise ApiRequestError(f"{self.source}: доступ отклонён, проверьте API-ключ")
        if status == 429:
            raise ApiRequestError(f"{self.source}: превышен лимит запросов")
        if status != 200:
            raise ApiRequestError(f"{self.source}: HTTP {status}")
        try:
            payload = response.json()
        except ValueError as error:
            raise ApiRequestError(f"{self.source}: ответ не является JSON") from error
        if not isinstance(payload, dict):
            raise ApiRequestError(f"{self.source}: неверная структура ответа")
        self.updated_at = datetime.now(UTC).isoformat(timespec="seconds")
        self.metadata = {
            "request_ms": round((time.monotonic() - started) * 1000),
            "status_code": status,
            "etag": response.headers.get("ETag"),
        }
        return payload

    @abstractmethod
    def fetch_rates(self):
        """Возвращает словарь вида {'BTC_USD': 59337.21}."""


class CoinGeckoClient(BaseApiClient):
    """Получает стоимость криптовалют по их CoinGecko ID."""

    source = "CoinGecko"

    def fetch_rates(self):
        """Приводит ответ CoinGecko к парам валют."""
        try:
            ids = [
                self.config.CRYPTO_ID_MAP[code]
                for code in self.config.CRYPTO_CURRENCIES
            ]
        except KeyError as error:
            raise ApiRequestError("Для криптовалюты не задан CoinGecko ID") from error
        headers = {}
        if self.config.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = self.config.COINGECKO_API_KEY
        base = self.config.BASE_CURRENCY
        payload = self._request_json(
            self.config.COINGECKO_URL,
            params={"ids": ",".join(ids), "vs_currencies": base.lower()},
            headers=headers,
        )
        result = {}
        for code in self.config.CRYPTO_CURRENCIES:
            raw_id = self.config.CRYPTO_ID_MAP[code]
            values = payload.get(raw_id)
            if not isinstance(values, dict) or base.lower() not in values:
                raise ApiRequestError(f"CoinGecko: нет курса для {code}")
            result[f"{code}_{base}"] = positive_rate(values[base.lower()])
        return result


class ExchangeRateApiClient(BaseApiClient):
    """Получает фиатные курсы, включая открытый доступ без ключа."""

    source = "ExchangeRate-API"

    def fetch_rates(self):
        """Переводит курсы BASE→CODE в обратные пары CODE→BASE."""
        base = self.config.BASE_CURRENCY
        if self.config.EXCHANGERATE_API_KEY:
            url = (
                f"{self.config.EXCHANGERATE_API_URL}/"
                f"{self.config.EXCHANGERATE_API_KEY}/latest/{base}"
            )
        else:
            url = f"{self.config.EXCHANGERATE_OPEN_URL}/{base}"
        payload = self._request_json(url)
        if payload.get("result") != "success":
            reason = payload.get("error-type", "неизвестная ошибка")
            raise ApiRequestError(f"ExchangeRate-API: {reason}")
        if payload.get("base_code", base) != base:
            raise ApiRequestError("ExchangeRate-API: неожиданная базовая валюта")
        rates = payload.get("conversion_rates", payload.get("rates"))
        if not isinstance(rates, dict):
            raise ApiRequestError("ExchangeRate-API: в ответе нет курсов")
        result = {}
        for code in self.config.FIAT_CURRENCIES:
            if code not in rates:
                raise ApiRequestError(f"ExchangeRate-API: нет курса для {code}")
            # В ответе количество CODE за 1 BASE, а Core нужны BASE за 1 CODE.
            result[f"{code}_{base}"] = positive_rate(1 / positive_rate(rates[code]))
        return result
