class InsufficientFundsError(ValueError):
    """На кошельке недостаточно средств для операции."""

    def __init__(self, available, required, code):
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {available:.8g} {code}, "
            f"требуется {required:.8g} {code}"
        )


class CurrencyNotFoundError(ValueError):
    """Код валюты отсутствует в реестре."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(Exception):
    """Не удалось получить корректный курс валют."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")


class RateExpiredError(ApiRequestError):
    """Курс в локальном кэше устарел."""


class AuthenticationError(ValueError):
    """Ошибка входа или отсутствие пользовательской сессии."""
