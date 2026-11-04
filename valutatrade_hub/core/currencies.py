import math
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.utils import validate_currency_code


class Currency(ABC):
    """Общий интерфейс фиатной или цифровой валюты."""

    def __init__(self, name, code):
        """Проверяет название и код валюты."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")
        self.name = name.strip()
        self.code = validate_currency_code(code)

    @abstractmethod
    def get_display_info(self):
        """Возвращает описание валюты для интерфейса."""


class FiatCurrency(Currency):
    """Фиатная валюта со страной или зоной эмиссии."""

    def __init__(self, name, code, issuing_country):
        """Создаёт фиатную валюту."""
        super().__init__(name, code)
        if not isinstance(issuing_country, str) or not issuing_country.strip():
            raise ValueError("Страна или зона эмиссии не может быть пустой")
        self.issuing_country = issuing_country.strip()

    def get_display_info(self):
        """Возвращает название и зону эмиссии."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта с описанием алгоритма и капитализации."""

    def __init__(self, name, code, algorithm, market_cap=0.0):
        """Создаёт криптовалюту с указанными характеристиками."""
        super().__init__(name, code)
        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValueError("Алгоритм не может быть пустым")
        if isinstance(market_cap, bool) or not isinstance(market_cap, (int, float)):
            raise ValueError("Капитализация должна быть неотрицательным числом")
        if not math.isfinite(market_cap) or market_cap < 0:
            raise ValueError("Капитализация должна быть неотрицательным числом")
        self.algorithm = algorithm.strip()
        self.market_cap = float(market_cap)

    def get_display_info(self):
        """Возвращает название, алгоритм и краткую капитализацию."""
        market_cap = f"{self.market_cap:.3g}".replace("e+", "e")
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {market_cap})"
        )


CURRENCIES = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("Pound Sterling", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256"),
    "ETH": CryptoCurrency("Ethereum", "ETH", "PoS"),
    "SOL": CryptoCurrency("Solana", "SOL", "PoH"),
}


def get_currency(code):
    """Находит зарегистрированную валюту по её коду."""
    normalized = validate_currency_code(code)
    if normalized not in CURRENCIES:
        raise CurrencyNotFoundError(normalized)
    return CURRENCIES[normalized]
