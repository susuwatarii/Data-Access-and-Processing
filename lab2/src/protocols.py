"""ЭТАП B. Сравнительная таблица протоколов HTTP / FTP / SMTP.

Таблица заполняется не «по памяти», а по фактическому выводу установленной
сборки: `curl --version` печатает строку Protocols со списком поддерживаемых
протоколов. Официальный manual curl предупреждает, что конкретная сборка
может поддерживать не все протоколы, поэтому проверять надо именно свою.

Результат: results/protocol_comparison.md

Запуск отдельно:
    python lab_2.py protocols
    python -m src.protocols
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):  # запуск файлом: python src/protocols.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, report

# Протокол | типичная задача | шифрованный вариант | какие имена искать в Protocols
PROTOCOL_ROWS = [
    (
        "HTTP",
        "Запросы к REST API: получить список операций (GET), создать (POST), "
        "изменить (PUT/PATCH), удалить (DELETE), посмотреть заголовки ответа",
        "HTTPS",
        ("http", "https"),
    ),
    (
        "FTP",
        "Передача файлов: скачать выгрузку с ftp-сервера или загрузить отчёт; "
        "в curl — команды скачивания/загрузки файла",
        "FTPS",
        ("ftp", "ftps"),
    ),
    (
        "SMTP",
        "Отправка почты: письмо с результатами расчёта или ссылкой на отчёт",
        "SMTPS",
        ("smtp", "smtps"),
    ),
]


def curl_executable() -> str:
    """Путь к настоящему curl. В PowerShell слово curl — алиас Invoke-WebRequest."""
    for name in ("curl.exe", "curl"):
        path = shutil.which(name)
        if path:
            return path
    raise FileNotFoundError("curl не найден в PATH. Установите curl или запустите из другого терминала.")


def read_curl_version() -> dict[str, object]:
    """Запускает `curl --version` и разбирает вывод."""
    result = subprocess.run(
        [curl_executable(), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl --version завершился с кодом {result.returncode}: {result.stderr}")

    text = result.stdout
    lines = [line for line in text.splitlines() if line.strip()]
    protocols_line = next((line for line in lines if line.lower().startswith("protocols:")), "")
    features_line = next((line for line in lines if line.lower().startswith("features:")), "")

    protocols = re.split(r"\s+", protocols_line.split(":", 1)[1].strip()) if protocols_line else []

    return {
        "version_line": lines[0] if lines else "неизвестно",
        "release_line": next((line for line in lines if line.lower().startswith("release-date")), ""),
        "protocols": protocols,
        "protocols_line": protocols_line,
        "features_line": features_line,
        "raw": text,
    }


def _supports(row_names: tuple[str, ...], protocols: list[str]) -> tuple[bool, str]:
    """Проверяет, есть ли протоколы строки в сборке, и возвращает пояснение."""
    available = [name for name in row_names if name in protocols]
    missing = [name for name in row_names if name not in protocols]
    if not missing:
        return True, "да (" + ", ".join(available) + ")"
    if available:
        return True, "частично (" + ", ".join(available) + "); нет: " + ", ".join(missing)
    return False, "нет"


def write_protocol_table(path: Path = config.PROTOCOL_REPORT) -> Path:
    """Собирает markdown-файл с таблицей и короткими пояснениями."""
    info = read_curl_version()
    protocols = list(info["protocols"])  # type: ignore[arg-type]

    rows = []
    for name, task, secure, names in PROTOCOL_ROWS:
        supported, note = _supports(names, protocols)
        rows.append(
            {
                "Протокол": name,
                "Типичная задача": task,
                "Шифрованный вариант": secure,
                "Поддерживается вашей сборкой": note if supported else "**нет**",
            }
        )

    report.heading("ЭТАП B. АНАЛИЗ ПРОТОКОЛОВ")
    report.log(f"Сборка: {info['version_line']}")
    if info["release_line"]:
        report.log(str(info["release_line"]))
    report.log(f"{info['protocols_line']}")
    report.log(f"{info['features_line']}")
    report.log()
    report.log("Сравнительная таблица:")
    for row in rows:
        report.log(f"  {row['Протокол']:<5} | {row['Шифрованный вариант']:<6} | "
                   f"{row['Поддерживается вашей сборкой']}")

    # --- markdown ---------------------------------------------------------
    lines = [
        "# Этап B. Сравнение протоколов и поддержка в установленной сборке curl",
        "",
        f"Проверено фактически командой `curl --version`:",
        "",
        "```",
        str(info["version_line"]),
    ]
    if info["release_line"]:
        lines.append(str(info["release_line"]))
    lines += [str(info["protocols_line"]), str(info["features_line"]), "```", ""]

    lines += [
        "| Протокол | Типичная задача | Шифрованный вариант | Поддерживается вашей сборкой |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['Протокол']} | {row['Типичная задача']} | {row['Шифрованный вариант']} | "
            f"{row['Поддерживается вашей сборкой']} |"
        )

    lines += [
        "",
        "Все протоколы, которые перечисляет установленная сборка:",
        "",
        "`" + ", ".join(protocols) + "`",
        "",
        "## Пояснения",
        "",
        "- `curl --version` печатает строку `Protocols:` со списком протоколов, "
        "которые реально включены в сборку. Официальный manual curl отдельно "
        "предупреждает, что набор зависит от сборки, поэтому проверять нужно свою.",
        "- Шифрованные варианты (HTTPS, FTPS, SMTPS) — это те же протоколы поверх TLS. "
        "Для curl это отдельные имена в списке протоколов, а не «галочка» в настройках.",
        "- Для лабораторной работы реально использовался только HTTP: "
        "`GET/POST/PUT/PATCH/DELETE` к `http://127.0.0.1:8000/api/transactions`. "
        "К внешним FTP- и SMTP-серверам подключения не выполнялись — это и не требуется.",
        "",
        "## Чем curl отличается от библиотеки requests",
        "",
        "- `curl` — отдельная программа командной строки: работает без Python, "
        "умеет HTTP, FTP, SMTP и другие протоколы, показывает заголовки, коды ответа "
        "и редиректы «как есть». Удобен для диагностики: видно, что именно вернул сервер.",
        "- `requests` — библиотека Python: работает только по HTTP(S), зато ответ сразу "
        "превращается в объекты Python (`.json()`, `.status_code`), и его удобно "
        "обрабатывать в коде конвейера.",
        "- В конвейере этой работы оба инструмента дополняют друг друга: curl — "
        "ручная проверка API (этап A), requests — программная загрузка данных (этап C).",
        "",
        f"_Файл сформирован автоматически: `{Path(__file__).name}`._",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

    report.log()
    report.log(f"Таблица сохранена: {path}")
    return path


def main() -> None:
    """Отдельный запуск этапа B: python -m src.protocols"""
    try:
        write_protocol_table()
    except (FileNotFoundError, RuntimeError) as exc:
        report.log(f"\nОШИБКА: {exc}")
        sys.exit(2)


if __name__ == "__main__":
    main()
