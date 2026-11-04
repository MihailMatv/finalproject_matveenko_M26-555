"""Командная строка кошелька: разбор аргументов и вывод результатов."""

import argparse
import shlex
import sys

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CURRENCIES
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.usecases import TradingService
from valutatrade_hub.logging_config import setup_logging


class CommandParser(argparse.ArgumentParser):
    """Возвращает ошибку ввода вместо завершения всей консоли."""

    def error(self, message):
        """Передаёт сообщение обработчику CLI."""
        raise ValueError(message)


def build_parser():
    """Описывает команды приложения и их аргументы."""
    parser = CommandParser(
        prog="valutatrade", description="Виртуальный валютный кошелёк"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("register", "login"):
        command = commands.add_parser(name)
        command.add_argument("--username", required=True)
        command.add_argument("--password", required=True)
    command = commands.add_parser("show-portfolio")
    command.add_argument("--base", default="USD")
    for name in ("buy", "sell"):
        command = commands.add_parser(name)
        command.add_argument("--currency", required=True)
        command.add_argument("--amount", type=float, required=True)
    command = commands.add_parser("deposit")
    command.add_argument("--currency", default="USD")
    command.add_argument("--amount", type=float, required=True)
    command = commands.add_parser("get-rate")
    command.add_argument("--from", dest="from_code", required=True)
    command.add_argument("--to", dest="to_code", required=True)
    command = commands.add_parser("update-rates")
    command.add_argument("--source", choices=("coingecko", "exchangerate"))
    command = commands.add_parser("show-rates")
    command.add_argument("--currency")
    command.add_argument("--top", type=int)
    command.add_argument("--base", default="USD")
    command = commands.add_parser("help")
    command.add_argument("topic", nargs="?")
    commands.add_parser("logout")
    commands.add_parser("exit")
    return parser


class WalletCLI:
    """Показывает результаты usecases и обрабатывает ошибки пользователя."""

    def __init__(self, service=None):
        """Принимает сервис с текущей пользовательской сессией."""
        self.service = service or TradingService()
        self.parser = build_parser()

    def _print_portfolio(self, result):
        """Печатает кошельки и итоговую стоимость."""
        print(f"Портфель пользователя '{result['username']}' (база: {result['base']}):")
        if not result["wallets"]:
            print("Портфель пуст. Начните с deposit --amount 10000")
            return
        table = PrettyTable(["Валюта", "Баланс", f"Стоимость в {result['base']}"])
        for wallet in result["wallets"]:
            table.add_row(
                [
                    wallet["currency_code"],
                    f"{wallet['balance']:.8g}",
                    f"{wallet['value']:,.2f}",
                ]
            )
        print(table)
        print(f"ИТОГО: {result['total']:,.2f} {result['base']}")

    def _print_trade(self, action, result):
        """Показывает изменения валютного и расчётного кошельков."""
        title = "Покупка" if action == "buy" else "Продажа"
        code = result["currency_code"]
        print(
            f"{title} выполнена: {result['amount']:.8g} {code} "
            f"по курсу {result['rate']:.8g} USD/{code}"
        )
        print(f"- {code}: было {result['before']:.8g} → стало {result['after']:.8g}")
        print(
            f"- USD: было {result['usd_before']:.8g} → стало {result['usd_after']:.8g}"
        )
        print(f"Стоимость сделки: {result['cost']:,.2f} USD")

    def _print_rates(self, result):
        """Печатает локальные курсы, отмечая устаревшие значения."""
        print(f"Курсы из кэша (обновлено: {result['last_refresh']}):")
        table = PrettyTable(["Пара", "Курс", "Время UTC", "Состояние"])
        for quote in result["pairs"]:
            table.add_row(
                [
                    quote["pair"],
                    f"{quote['rate']:.10g}",
                    quote["updated_at"],
                    "устарел" if quote["stale"] else "актуален",
                ]
            )
        print(table)

    def dispatch(self, arguments):
        """Вызывает бизнес-операцию по разобранной команде."""
        action = arguments.command
        if action == "register":
            user = self.service.register(arguments.username, arguments.password)
            print(
                f"Пользователь '{user['username']}' зарегистрирован "
                f"(id={user['user_id']}). Войдите командой login"
            )
        elif action == "login":
            user = self.service.login(arguments.username, arguments.password)
            print(f"Вы вошли как '{user['username']}'")
        elif action == "logout":
            self.service.logout()
            print("Вы вышли из аккаунта")
        elif action == "show-portfolio":
            self._print_portfolio(self.service.show_portfolio(arguments.base))
        elif action == "deposit":
            result = self.service.deposit(arguments.amount, arguments.currency)
            print(
                f"Виртуальный кошелёк USD пополнен на {result['amount']:.8g}. "
                f"Баланс: {result['balance']:.8g} USD"
            )
        elif action in {"buy", "sell"}:
            operation = self.service.buy if action == "buy" else self.service.sell
            self._print_trade(action, operation(arguments.currency, arguments.amount))
        elif action == "get-rate":
            quote = self.service.get_rate(arguments.from_code, arguments.to_code)
            print(
                f"Курс {arguments.from_code.upper()}→{arguments.to_code.upper()}: "
                f"{quote['rate']:.10g} (обновлено: {quote['updated_at']})"
            )
            print(f"Обратный курс: {1 / quote['rate']:.10g}")
        elif action == "update-rates":
            result = self.service.update_rates(arguments.source)
            print(
                f"Обновлено курсов: {result['updated_count']}. "
                f"Время: {result['last_refresh']}"
            )
            for error in result["errors"]:
                print(f"Предупреждение: {error}")
            print("Rates By Exchange Rate API — https://www.exchangerate-api.com")
        elif action == "show-rates":
            self._print_rates(
                self.service.show_rates(
                    arguments.currency, arguments.top, arguments.base
                )
            )
        elif action == "help":
            if arguments.topic:
                self.parser.parse_args([arguments.topic, "--help"])
            else:
                self.parser.print_help()
        elif action == "exit":
            return False
        return True

    def execute(self, text):
        """Выполняет одну строку, сохраняя консоль после ошибки."""
        try:
            return self.dispatch(self.parser.parse_args(shlex.split(text)))
        except SystemExit as error:
            if error.code:
                print("Проверьте аргументы команды. Для справки введите help")
        except CurrencyNotFoundError as error:
            print(error)
            print(f"Поддерживаемые валюты: {', '.join(sorted(CURRENCIES))}")
        except InsufficientFundsError as error:
            print(error)
        except ApiRequestError as error:
            print(error)
            print("Проверьте сеть или повторите обновление позже")
        except (ValueError, OSError, KeyError) as error:
            print(f"Ошибка: {error}")
        return True

    def run(self):
        """Запускает интерактивную консоль до команды exit."""
        print("ValutaTrade Hub. Виртуальная торговля. help — справка, exit — выход.")
        while True:
            try:
                text = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if text.strip() and self.execute(text) is False:
                break


def main(argv=None):
    """Запускает консоль или одну команду, переданную в аргументах."""
    try:
        setup_logging()
        interface = WalletCLI()
        arguments = sys.argv[1:] if argv is None else argv
        if arguments:
            interface.execute(shlex.join(arguments))
        else:
            interface.run()
    except (OSError, ValueError) as error:
        print(f"Не удалось запустить приложение: {error}")


if __name__ == "__main__":
    main()
