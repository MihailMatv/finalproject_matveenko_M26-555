import hashlib
import hmac
import math
import secrets
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import validate_amount

MIN_PASSWORD_LENGTH = 4
SALT_BYTES = 16

# Учебные значения для отдельной модели без подключённого сервиса курсов.
EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 1.0786,
    "GBP": 1.27,
    "RUB": 0.01016,
    "BTC": 59337.21,
    "ETH": 3720.0,
    "SOL": 145.12,
}


class User:
    """Пользователь с солёным хешем пароля."""

    def __init__(self, user_id, username, hashed_password, salt, registration_date):
        """Восстанавливает пользователя из сохранённых полей."""
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным целым числом")
        if not isinstance(hashed_password, str) or not hashed_password:
            raise ValueError("Хеш пароля не может быть пустым")
        if not isinstance(salt, str) or not salt:
            raise ValueError("Соль пароля не может быть пустой")
        if isinstance(registration_date, str):
            registration_date = datetime.fromisoformat(registration_date)
        if not isinstance(registration_date, datetime):
            raise ValueError("Дата регистрации должна быть датой в формате ISO")
        if registration_date.tzinfo is None:
            registration_date = registration_date.replace(tzinfo=UTC)
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id, username, password):
        """Создаёт пользователя с новой солью и хешем пароля."""
        cls._validate_password(password)
        salt = secrets.token_hex(SALT_BYTES)
        hashed_password = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
        return cls(user_id, username, hashed_password, salt, datetime.now(UTC))

    @staticmethod
    def _validate_password(password):
        """Проверяет минимальную длину пароля."""
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError("Пароль должен быть не короче 4 символов")

    @property
    def user_id(self):
        """Возвращает неизменяемый ID пользователя."""
        return self._user_id

    @property
    def username(self):
        """Возвращает имя пользователя."""
        return self._username

    @username.setter
    def username(self, value):
        """Проверяет непустое имя пользователя."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self):
        """Возвращает хеш для сохранения в хранилище."""
        return self._hashed_password

    @property
    def salt(self):
        """Возвращает соль для сохранения пользователя."""
        return self._salt

    @property
    def registration_date(self):
        """Возвращает дату регистрации."""
        return self._registration_date

    def get_user_info(self):
        """Возвращает публичные данные без хеша и соли."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": self.registration_date.isoformat(),
        }

    def change_password(self, new_password):
        """Заменяет пароль, создавая новую соль."""
        self._validate_password(new_password)
        salt = secrets.token_hex(SALT_BYTES)
        hashed_password = hashlib.sha256(
            (new_password + salt).encode("utf-8")
        ).hexdigest()
        self._salt = salt
        self._hashed_password = hashed_password

    def verify_password(self, password):
        """Сравнивает хеш введённого пароля с сохранённым."""
        if not isinstance(password, str):
            return False
        candidate = hashlib.sha256((password + self.salt).encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate, self.hashed_password)

    def to_dict(self):
        """Возвращает запись для users.json."""
        return {
            **self.get_user_info(),
            "hashed_password": self.hashed_password,
            "salt": self.salt,
        }

    @classmethod
    def from_dict(cls, data):
        """Восстанавливает пользователя из JSON-записи."""
        return cls(
            data["user_id"],
            data["username"],
            data["hashed_password"],
            data["salt"],
            data["registration_date"],
        )


class Wallet:
    """Баланс одной валюты с проверкой пополнения и списания."""

    def __init__(self, currency_code, balance=0.0):
        """Создаёт кошелёк для поддерживаемой валюты."""
        self.currency_code = get_currency(currency_code).code
        self.balance = balance

    @property
    def balance(self):
        """Возвращает текущий баланс."""
        return self._balance

    @balance.setter
    def balance(self, value):
        """Запрещает отрицательные и некорректные значения баланса."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Баланс должен быть неотрицательным числом")
        if not math.isfinite(value) or value < 0:
            raise ValueError("Баланс должен быть неотрицательным числом")
        self._balance = float(value)

    def deposit(self, amount):
        """Пополняет кошелёк на положительную сумму."""
        self.balance += validate_amount(amount)

    def withdraw(self, amount):
        """Списывает сумму, если на кошельке хватает средств."""
        amount = validate_amount(amount)
        if amount > self.balance:
            raise InsufficientFundsError(self.balance, amount, self.currency_code)
        self.balance -= amount

    def get_balance_info(self):
        """Возвращает код валюты и текущий остаток."""
        return f"{self.currency_code}: {self.balance:.4f}"

    def to_dict(self):
        """Возвращает сериализуемую запись кошелька."""
        return {"currency_code": self.currency_code, "balance": self.balance}


class Portfolio:
    """Коллекция валютных кошельков одного пользователя."""

    def __init__(self, user_id, wallets=None, user=None, rate_provider=None):
        """Связывает пользователя, его кошельки и источник курсов."""
        if isinstance(user_id, User):
            user = user_id
            user_id = user.user_id
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным целым числом")
        if user is not None and (not isinstance(user, User) or user.user_id != user_id):
            raise ValueError("Пользователь не соответствует владельцу портфеля")
        self._user_id = user_id
        self._user = user
        self._rate_provider = rate_provider
        self._wallets = {}
        for code, wallet in (wallets or {}).items():
            normalized = get_currency(code).code
            if not isinstance(wallet, Wallet) or wallet.currency_code != normalized:
                raise ValueError("Код валюты не соответствует кошельку")
            self._wallets[normalized] = wallet

    @property
    def user_id(self):
        """Возвращает ID владельца портфеля."""
        return self._user_id

    @property
    def user(self):
        """Возвращает связанный объект пользователя без права замены."""
        return self._user

    @property
    def wallets(self):
        """Возвращает копию словаря кошельков."""
        return self._wallets.copy()

    def add_currency(self, currency_code):
        """Создаёт отсутствующий кошелёк, сохраняя уже имеющийся баланс."""
        code = get_currency(currency_code).code
        if code not in self._wallets:
            self._wallets[code] = Wallet(code)
        return self._wallets[code]

    def get_wallet(self, currency_code):
        """Находит кошелёк или сообщает, что он ещё не создан."""
        code = get_currency(currency_code).code
        if code not in self._wallets:
            raise ValueError(
                f"У вас нет кошелька '{code}'. "
                "Он создаётся автоматически при первой покупке."
            )
        return self._wallets[code]

    def get_total_value(self, base_currency="USD"):
        """Считает общую стоимость кошельков в базовой валюте."""
        base = get_currency(base_currency).code
        total = 0.0
        for code, wallet in self._wallets.items():
            if wallet.balance == 0:
                continue
            if code == base:
                rate = 1.0
            elif self._rate_provider is None:
                rate = EXCHANGE_RATES[code] / EXCHANGE_RATES[base]
            else:
                rate = self._rate_provider(code, base)
                if isinstance(rate, dict):
                    rate = rate["rate"]
                rate = validate_amount(rate)
            total += wallet.balance * rate
        if not math.isfinite(total):
            raise ValueError("Итоговая стоимость выходит за допустимый диапазон")
        return total

    def to_dict(self):
        """Возвращает запись портфеля для JSON-хранилища."""
        return {
            "user_id": self.user_id,
            "wallets": {
                code: wallet.to_dict() for code, wallet in self._wallets.items()
            },
        }
