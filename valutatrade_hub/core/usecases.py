"""Операции пользователя и расчёты виртуального портфеля."""

import json
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    AuthenticationError,
    InsufficientFundsError,
    RateExpiredError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import validate_amount
from valutatrade_hub.decorators import create_cacher, log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RateStorage, parse_timestamp
from valutatrade_hub.parser_service.updater import RatesUpdater


class TradingService:
    """Связывает модели, файловое хранилище, сессию и сервис курсов."""

    def __init__(self, settings=None, database=None, updater=None):
        """Принимает зависимости, чтобы их можно было заменить при проверке."""
        self.settings = settings or SettingsLoader()
        self.database = database or DatabaseManager()
        self.database.initialize(self.settings)
        config = ParserConfig(
            RATES_FILE_PATH=self.settings.get("rates_file"),
            HISTORY_FILE_PATH=self.settings.get("history_file"),
        )
        self.storage = RateStorage(config, self.database)
        self.updater = updater
        self.current_user = None
        self._rate_cache = create_cacher()

    def _records(self, key):
        """Читает список записей из выбранного файла."""
        records = self.database.read_json(self.settings.get(key), [])
        if not isinstance(records, list):
            raise ValueError(f"Некорректный формат хранилища: {key}")
        return records

    def _require_user(self):
        """Проверяет наличие текущей сессии."""
        if self.current_user is None:
            raise AuthenticationError("Сначала выполните login")
        return self.current_user

    def register(self, username, password):
        """Создаёт пользователя с пустым портфелем, не выполняя вход."""
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        username = username.strip()
        users = self._records("users_file")
        if any(record["username"] == username for record in users):
            raise ValueError(f"Имя пользователя '{username}' уже занято")
        user_id = max((record["user_id"] for record in users), default=0) + 1
        user = User.create(user_id, username, password)
        portfolios = self._records("portfolios_file")
        portfolios.append(Portfolio(user_id, user=user).to_dict())
        self.database.write_json(self.settings.get("portfolios_file"), portfolios)
        self.database.write_json(
            self.settings.get("users_file"), users + [user.to_dict()]
        )
        return user.get_user_info()

    def login(self, username, password):
        """Проверяет пароль и устанавливает текущего пользователя."""
        self.current_user = None
        for record in self._records("users_file"):
            if record["username"] == username:
                user = User.from_dict(record)
                if not user.verify_password(password):
                    raise AuthenticationError("Неверный пароль")
                self.current_user = user
                return user.get_user_info()
        raise AuthenticationError(f"Пользователь '{username}' не найден")

    def logout(self):
        """Завершает текущую сессию."""
        self.current_user = None

    def _load_portfolio(self):
        """Восстанавливает актуальные кошельки из хранилища."""
        user = self._require_user()
        for record in self._records("portfolios_file"):
            if record["user_id"] == user.user_id:
                wallets = {
                    code: Wallet(code, values["balance"])
                    for code, values in record["wallets"].items()
                }
                return Portfolio(user.user_id, wallets, user, self.get_rate)
        raise ValueError("Портфель пользователя не найден")

    def _save_portfolio(self, portfolio):
        """Сохраняет обе стороны сделки одним изменением файла портфелей."""
        records = self._records("portfolios_file")
        for index, record in enumerate(records):
            if record["user_id"] == portfolio.user_id:
                records[index] = portfolio.to_dict()
                self.database.write_json(self.settings.get("portfolios_file"), records)
                return
        raise ValueError("Портфель пользователя не найден")

    def deposit(self, amount, currency_code="USD"):
        """Пополняет виртуальный USD-кошелёк для учебной торговли."""
        portfolio = self._load_portfolio()
        code = get_currency(currency_code).code
        if code != "USD":
            raise ValueError("Пополнение доступно только для расчётной валюты USD")
        amount = validate_amount(amount)
        wallet = portfolio.add_currency(code)
        wallet.deposit(amount)
        self._save_portfolio(portfolio)
        return {"currency_code": code, "amount": amount, "balance": wallet.balance}

    def update_rates(self, source=None):
        """Обновляет курсы через Parser Service."""
        updater = self.updater or RatesUpdater(storage=self.storage)
        result = updater.run_update(source=source)
        self._rate_cache.clear()
        return result

    @staticmethod
    def _resolve_rate(pairs, from_code, to_code):
        """Находит прямой, обратный или кросс-курс через USD."""
        if from_code == to_code:
            return {
                "rate": 1.0,
                "updated_at": datetime.now(UTC).isoformat(),
                "source": "identity",
            }
        direct = pairs.get(f"{from_code}_{to_code}")
        reverse = pairs.get(f"{to_code}_{from_code}")
        if direct is not None:
            return {**direct, "rate": validate_amount(direct["rate"])}
        if reverse is not None:
            return {
                **reverse,
                "rate": validate_amount(1 / validate_amount(reverse["rate"])),
            }
        usd = {
            "rate": 1.0,
            "updated_at": datetime.now(UTC).isoformat(),
            "source": "USD",
        }
        left = usd if from_code == "USD" else pairs.get(f"{from_code}_USD")
        right = usd if to_code == "USD" else pairs.get(f"{to_code}_USD")
        if left is None or right is None:
            raise ApiRequestError(f"Курс {from_code}→{to_code} недоступен")
        timestamp = min(
            parse_timestamp(left["updated_at"]), parse_timestamp(right["updated_at"])
        )
        return {
            "rate": validate_amount(
                validate_amount(left["rate"]) / validate_amount(right["rate"])
            ),
            "updated_at": timestamp.isoformat(),
            "source": f"{left.get('source', '')} / {right.get('source', '')}",
        }

    def _cached_rate(self, from_code, to_code):
        """Кэширует расчёт курса по содержимому файлового снимка."""
        pairs = self.storage.load_rates()["pairs"]
        key = (from_code, to_code, json.dumps(pairs, sort_keys=True))
        result = self._rate_cache(
            key, lambda: self._resolve_rate(pairs, from_code, to_code)
        )
        age = (
            datetime.now(UTC) - parse_timestamp(result["updated_at"])
        ).total_seconds()
        if age > self.settings.get("rates_ttl_seconds"):
            raise RateExpiredError("Курс устарел. Выполните update-rates")
        return result.copy()

    def get_rate(self, from_code, to_code):
        """Получает свежий курс; при необходимости один раз обновляет кэш."""
        from_code = get_currency(from_code).code
        to_code = get_currency(to_code).code
        if from_code == to_code:
            return self._resolve_rate({}, from_code, to_code)
        try:
            return self._cached_rate(from_code, to_code)
        except (ApiRequestError, ValueError):
            try:
                self.update_rates()
                return self._cached_rate(from_code, to_code)
            except (ApiRequestError, ValueError) as error:
                raise ApiRequestError(
                    f"Курс {from_code}→{to_code} недоступен или устарел. "
                    f"Выполните update-rates и повторите попытку. {error}"
                ) from error

    def show_portfolio(self, base_currency="USD"):
        """Возвращает кошельки и общую стоимость для вывода в CLI."""
        portfolio = self._load_portfolio()
        base = get_currency(base_currency).code
        rows = []
        for code, wallet in sorted(portfolio.wallets.items()):
            rate = self.get_rate(code, base)["rate"] if wallet.balance else 0.0
            rows.append(
                {
                    "currency_code": code,
                    "balance": wallet.balance,
                    "value": wallet.balance * rate,
                }
            )
        return {
            "username": portfolio.user.username,
            "base": base,
            "wallets": rows,
            "total": portfolio.get_total_value(base),
        }

    @log_action("BUY", verbose=True)
    def buy(self, currency_code, amount):
        """Списывает USD и зачисляет купленную валюту."""
        portfolio = self._load_portfolio()
        code = get_currency(currency_code).code
        amount = validate_amount(amount)
        if code == "USD":
            raise ValueError(
                "USD — расчётная валюта. Используйте deposit для пополнения"
            )
        rate = self.get_rate(code, "USD")["rate"]
        cost = validate_amount(amount * rate)
        usd_wallet = portfolio.add_currency("USD")
        if cost > usd_wallet.balance:
            raise InsufficientFundsError(usd_wallet.balance, cost, "USD")
        wallet = portfolio.add_currency(code)
        before, usd_before = wallet.balance, usd_wallet.balance
        usd_wallet.withdraw(cost)
        wallet.deposit(amount)
        self._save_portfolio(portfolio)
        return {
            "currency_code": code,
            "amount": amount,
            "rate": rate,
            "base": "USD",
            "before": before,
            "after": wallet.balance,
            "usd_before": usd_before,
            "usd_after": usd_wallet.balance,
            "cost": cost,
        }

    @log_action("SELL", verbose=True)
    def sell(self, currency_code, amount):
        """Списывает проданную валюту и зачисляет выручку в USD."""
        portfolio = self._load_portfolio()
        code = get_currency(currency_code).code
        amount = validate_amount(amount)
        if code == "USD":
            raise ValueError(
                "USD — расчётная валюта, выберите другую валюту для продажи"
            )
        wallet = portfolio.get_wallet(code)
        if amount > wallet.balance:
            raise InsufficientFundsError(wallet.balance, amount, code)
        rate = self.get_rate(code, "USD")["rate"]
        proceeds = validate_amount(amount * rate)
        usd_wallet = portfolio.add_currency("USD")
        before, usd_before = wallet.balance, usd_wallet.balance
        wallet.withdraw(amount)
        usd_wallet.deposit(proceeds)
        self._save_portfolio(portfolio)
        return {
            "currency_code": code,
            "amount": amount,
            "rate": rate,
            "base": "USD",
            "before": before,
            "after": wallet.balance,
            "usd_before": usd_before,
            "usd_after": usd_wallet.balance,
            "cost": proceeds,
        }

    def show_rates(self, currency=None, top=None, base="USD"):
        """Фильтрует локальные курсы без скрытого обращения к сети."""
        base = get_currency(base).code
        selected = get_currency(currency).code if currency is not None else None
        if top is not None and (
            isinstance(top, bool) or not isinstance(top, int) or top <= 0
        ):
            raise ValueError("--top должен быть положительным целым числом")
        snapshot = self.storage.load_rates()
        pairs = snapshot["pairs"]
        if not pairs:
            raise ValueError("Локальный кеш курсов пуст. Выполните update-rates")
        codes = {pair.split("_")[0] for pair in pairs}
        codes = {selected} if selected is not None else codes
        rows = []
        for code in sorted(codes):
            if top is not None and not isinstance(get_currency(code), CryptoCurrency):
                continue
            quote = self._resolve_rate(pairs, code, base)
            age = (
                datetime.now(UTC) - parse_timestamp(quote["updated_at"])
            ).total_seconds()
            rows.append(
                {
                    "pair": f"{code}_{base}",
                    **quote,
                    "stale": age > self.settings.get("rates_ttl_seconds"),
                }
            )
        if top is not None:
            rows = sorted(rows, key=lambda row: row["rate"], reverse=True)[:top]
        return {
            "pairs": rows,
            "last_refresh": snapshot.get("last_refresh"),
            "base": base,
        }
