"""Отдельная команда для разового или периодического обновления."""

import argparse
import math
import time

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.updater import RatesUpdater


def main(argv=None):
    """Запускает обновление; при --interval повторяет его до Ctrl+C."""
    parser = argparse.ArgumentParser(description="Обновление курсов валют")
    parser.add_argument("--source", choices=("coingecko", "exchangerate"))
    parser.add_argument("--interval", type=float, help="Интервал обновления в секундах")
    parser.add_argument("--once", action="store_true", help="Выполнить один запрос")
    args = parser.parse_args(argv)
    if args.interval is not None and (
        not math.isfinite(args.interval) or args.interval <= 0
    ):
        parser.error("Интервал должен быть положительным.")
    setup_logging()
    updater = RatesUpdater()
    try:
        while True:
            try:
                result = updater.run_update(source=args.source)
                print(f"Обновлено курсов: {result['updated_count']}.")
                for error in result["errors"]:
                    print(error)
            except ApiRequestError as error:
                print(error)
            if args.once or args.interval is None:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nОбновление остановлено.")


if __name__ == "__main__":
    main()
