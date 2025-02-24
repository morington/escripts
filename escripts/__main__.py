import argparse
import os
import subprocess
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import yaml


class Escripts:
    """
    Класс для управления и выполнения скриптов и алиасов, определённых в конфигурационном файле.

    Конфигурация ожидается в файле `config.yml` внутри рабочей папки (по умолчанию ~/.escripts).
    """

    def __init__(self, namespace: Optional[Path] = None) -> None:
        """
        Инициализация Escripts.

        Args:
            namespace (Optional[Path]): Путь к рабочей папке, где хранятся конфигурация и скрипты.
                                        По умолчанию используется папка '.escripts' в домашней директории.
        """
        self.namespace: Path = namespace if namespace else (Path.home() / ".escripts")
        self.data: Dict[str, Any] = self._load_config()

    def run(self) -> None:
        """
        Основной метод для разбора аргументов командной строки и выполнения соответствующей команды.
        При отсутствии аргументов выводит справку по использованию.
        """
        if len(sys.argv) < 2:
            self.print_usage()
            return

        command = sys.argv[1]
        argv = sys.argv[2:]

        if command == "--list":
            self.command_list()
        elif command in self.data.get("scripts", {}):
            self.process_command("scripts", command, self.data.get("scripts", {}), argv)
        elif command in self.data.get("aliases", {}):
            self.process_command("aliases", command, self.data.get("aliases", {}), argv)
        else:
            print("Неизвестная команда. Воспользуйтесь `--list` для просмотра доступных команд.")

    @staticmethod
    def print_usage() -> None:
        """Выводит инструкции по использованию утилиты."""
        usage_message = (
            "Использование:\n"
            "\tescripts [--list] <command> [--args=args] [--help]\n"
            "Для просмотра списка команд используйте --list."
        )
        print(usage_message)

    @staticmethod
    def print_help(name: str, description: str, args: Optional[Dict[str, Any]] = None) -> None:
        """
        Вывод справки по конкретной команде.

        Args:
            name (str): Имя команды.
            description (str): Описание команды.
            args (Optional[Dict[str, Any]]): Параметры команды.
        """
        print(f"Команда: {name}")
        print(f"Описание: {description}")
        if args:
            print("Аргументы:")
            for arg, details in args.items():
                arg_desc = details.get("description", "")
                arg_default = details.get("default", None)
                if arg_default is not None:
                    print(f"\t--{arg} [default: {arg_default}] - {arg_desc}")
                else:
                    print(f"\t--{arg} - {arg_desc}")

    def process_command(self, type_command: str, name: str, data: Dict[str, Any], argv: list) -> None:
        """
        Разбирает аргументы команды и выполняет её.

        Args:
            type_command (str): Тип команды ('scripts' или 'aliases').
            name (str): Имя команды.
            data (Dict[str, Any]): Словарь с описанием команды.
            argv (list): Список аргументов командной строки.
        """
        details = data.get(name)
        args_config = details.get("args", {})

        if "--help" in argv:
            self.print_help(name, details.get("description", ""), args_config)
            return

        parser = argparse.ArgumentParser(add_help=False)
        for arg, arg_details in args_config.items():
            # Определение типа аргумента (по умолчанию str)
            arg_type = str
            if "type" in arg_details:
                if arg_details["type"] == "int":
                    arg_type = int
                elif arg_details["type"] == "float":
                    arg_type = float

            kwargs = {"type": arg_type, "help": arg_details.get("description", "")}
            if "default" in arg_details:
                kwargs["default"] = arg_details["default"]
                kwargs["required"] = False
            else:
                kwargs["required"] = True

            parser.add_argument(f"--{arg}", **kwargs)

        try:
            parsed_args, _ = parser.parse_known_args(argv)
        except Exception as e:
            logging.error("Ошибка при разборе аргументов: %s", e)
            return

        command_args = vars(parsed_args)

        try:
            if type_command == "scripts":
                self.run_script(details, command_args)
            elif type_command == "aliases":
                self.run_alias(details, command_args)
            else:
                raise ValueError(f"Неизвестный тип команды: {type_command}")
        except Exception as e:
            logging.error("Ошибка при выполнении команды '%s': %s", name, e)

    def run_script(self, data: Dict[str, Any], args: Dict[str, Any]) -> None:
        """
        Выполняет скрипт, указанный в конфигурации.

        Args:
            data (Dict[str, Any]): Детали скрипта из конфигурации.
            args (Dict[str, Any]): Разобранные аргументы командной строки.

        Raises:
            FileNotFoundError: Если файл скрипта не существует.
            ValueError: Если путь не указывает на файл или отсутствует в конфигурации.
        """
        script_rel_path = data.get("path")
        if not script_rel_path:
            raise ValueError("Путь к скрипту не указан в конфигурации")
        script_path = self.namespace / script_rel_path

        if not script_path.exists():
            raise FileNotFoundError(f"Файл '{script_path.absolute()}' не существует")
        if not script_path.is_file():
            raise ValueError(f"'{script_path.absolute()}' не является файлом")

        # Используем переменную окружения для определения интерпретатора, если задана, иначе текущий sys.executable
        python_executable = os.environ.get("ESCRIPTS_PYTHON", sys.executable)
        cmd = [python_executable, str(script_path.absolute())]

        # Добавление аргументов команды
        for key, value in args.items():
            cmd.extend([f"--{key}", str(value)])

        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.namespace.absolute())

        try:
            subprocess.run(cmd, env=env, check=True)
        except subprocess.CalledProcessError as e:
            logging.error("Ошибка при выполнении скрипта: %s", e)
            raise

    def run_alias(self, data: Dict[str, Any], args: Dict[str, Any]) -> None:
        """
        Выполняет алиас, определённый в конфигурации.

        Args:
            data (Dict[str, Any]): Детали алиаса из конфигурации.
            args (Dict[str, Any]): Разобранные аргументы командной строки.

        Raises:
            ValueError: Если команда не указана или отсутствует необходимый аргумент.
        """
        command_template = data.get("command")
        if not command_template:
            raise ValueError("Команда не указана для алиаса")
        try:
            command_to_run = command_template.format(**args)
        except KeyError as e:
            raise ValueError(f"Отсутствует аргумент для формирования команды: {e}")

        try:
            subprocess.run(command_to_run, shell=True, cwd=self.namespace, check=True)
        except subprocess.CalledProcessError as e:
            logging.error("Ошибка при выполнении алиаса: %s", e)
            raise

    def command_list(self) -> None:
        """
        Выводит список доступных скриптов и алиасов с кратким описанием.
        """
        print("Скрипты:")
        scripts = self.data.get("scripts", {})
        if scripts:
            for name, details in scripts.items():
                print(f"\t- {name}: {details.get('description', '')}")
        else:
            print("\tПусто")

        print("Алиасы:")
        aliases = self.data.get("aliases", {})
        if aliases:
            for name, details in aliases.items():
                print(f"\t- {name}: {details.get('description', '')}")
        else:
            print("\tПусто")

    def _load_config(self) -> Dict[str, Any]:
        """
        Загружает конфигурацию из файла config.yml.

        Returns:
            Dict[str, Any]: Загруженные данные конфигурации.

        Raises:
            FileNotFoundError: Если рабочая папка или файл конфигурации не найдены.
            NotADirectoryError: Если указанный путь не является папкой.
            ValueError: Если конфигурация пуста или имеет ошибочный формат.
        """
        if not self.namespace.exists():
            raise FileNotFoundError(f"Папка '{self.namespace.absolute()}' не существует")
        if not self.namespace.is_dir():
            raise NotADirectoryError(f"'{self.namespace.absolute()}' не является папкой")

        config_path = self.namespace / "config.yml"
        if not config_path.exists():
            raise FileNotFoundError(f"Файл конфигурации '{config_path.absolute()}' не найден")
        if not config_path.is_file():
            raise ValueError(f"'{config_path.absolute()}' не является файлом")

        try:
            with config_path.open("r", encoding="utf-8") as file:
                config = yaml.safe_load(file)
        except yaml.YAMLError as e:
            raise ValueError(f"Ошибка разбора конфигурации: {e}")

        if config is None:
            raise ValueError("Конфигурация пуста")

        return config


def main() -> None:
    """
    Точка входа для CLI.
    Настраивает логирование, создаёт экземпляр Escripts и запускает разбор командной строки.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        es = Escripts()
        es.run()
    except Exception as e:
        logging.error("Ошибка: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
