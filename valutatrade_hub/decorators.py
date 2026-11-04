import inspect
import logging
from functools import wraps


def log_action(action=None, verbose=False):
    """Записывает результат операции и пробрасывает её исключения."""

    def decorator(func):
        """Добавляет журналирование к методу бизнес-логики."""
        signature = inspect.signature(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            """Логирует только разрешённые поля, без аргументов с паролями."""
            bound = signature.bind_partial(*args, **kwargs)
            arguments = bound.arguments
            service = arguments.get("self")
            user = getattr(service, "current_user", None)
            event = {
                "action": (action or func.__name__).upper(),
                "username": getattr(user, "username", None),
                "user_id": getattr(user, "user_id", None),
                "currency_code": arguments.get("currency_code"),
                "amount": arguments.get("amount"),
                "base": "USD",
            }
            logger = logging.getLogger("valutatrade.actions")
            try:
                result = func(*args, **kwargs)
            except Exception as error:
                event.update(
                    result="ERROR",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                logger.info(event)
                raise
            event["result"] = "OK"
            if isinstance(result, dict):
                for field in ("currency_code", "amount", "rate", "base"):
                    if field in result:
                        event[field] = result[field]
                if verbose:
                    for field in ("before", "after", "usd_before", "usd_after"):
                        if field in result:
                            event[field] = result[field]
            logger.info(event)
            return result

        return wrapper

    return decorator


def create_cacher():
    """Создаёт независимый кэш результатов в замыкании."""
    cache = {}

    def cache_result(key, value_func):
        """Возвращает сохранённый результат или вычисляет его один раз."""
        if key not in cache:
            cache[key] = value_func()
        return cache[key]

    cache_result.clear = cache.clear
    return cache_result
