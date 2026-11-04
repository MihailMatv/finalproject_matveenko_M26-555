import math


def validate_amount(value):
    """Проверяет положительную конечную сумму и возвращает float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("'amount' должен быть положительным числом")
    amount = float(value)
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return amount


def validate_currency_code(code):
    """Приводит код к верхнему регистру и проверяет его формат."""
    if not isinstance(code, str):
        raise ValueError("Код валюты должен быть строкой")
    normalized = code.strip().upper()
    if (
        not 2 <= len(normalized) <= 5
        or not normalized.isascii()
        or not normalized.isalpha()
    ):
        raise ValueError("Код валюты должен содержать от 2 до 5 латинских букв")
    return normalized
