"""ЭТАП A. Диагностика и тестирование REST API средствами curl.

Скрипт действительно выполняет curl-запросы к запущенному серверу и сохраняет
в results/curl_commands.txt команду и существенную часть ответа — это и есть
требуемый «след» этапа A.

Проверяется:
  * curl --version (версия, сборка TLS, список протоколов);
  * GET списка и GET одного ресурса, POST, PUT, PATCH, DELETE;
  * параметры: -i (заголовки ответа), -I (HEAD), query-параметры в URL,
    -d (JSON в теле), -H (свой заголовок), -L (следование redirect), -o (в файл).

Запуск (в отдельном терминале должен работать сервер):
    python lab_2.py curl
    python scripts/curl_demo.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # чтобы работал импорт src при прямом запуске файла
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from src import config, report  # noqa: E402

CURL = shutil.which("curl.exe") or shutil.which("curl") or "curl"
TIMEOUT = "20"
BASE_ARGS = ["-sS", "--max-time", TIMEOUT]

OUTPUT_JSON = config.DATA_RAW / "transactions_from_api.json"
OUTPUT_HEADERS = config.DATA_RAW / "api_headers.txt"


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def api_alive(base_url: str, timeout: float = 3.0) -> bool:
    """Проверяет, что сервер отвечает на /api/health."""
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/health", timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False


def api_count(base_url: str) -> int | None:
    """Сколько операций сейчас в API (для проверки, что данные не испорчены)."""
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/health", timeout=5)
        return int(response.json().get("transactions"))
    except (requests.RequestException, ValueError, TypeError):
        return None


def run_curl(args: list[str]) -> tuple[int, str]:
    """Запускает curl и возвращает код возврата и текст ответа."""
    result = subprocess.run(
        [CURL, *args],
        capture_output=True,
        timeout=60,
        cwd=str(ROOT),  # относительные пути (-o data/raw/...) считаются от корня проекта
    )

    def decode(data: bytes) -> str:
        for encoding in ("utf-8", "cp1251", "cp866"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    text = decode(result.stdout)
    errors = decode(result.stderr).strip()
    if errors and result.returncode != 0:
        text += ("\n" if text else "") + errors
    return result.returncode, text


def format_command(args: list[str]) -> str:
    """Собирает команду в виде, удобном для копирования в PowerShell."""
    parts = ["curl.exe"]
    for arg in args:
        if arg.startswith("{"):
            parts.append("'" + arg + "'")          # JSON — в одинарных кавычках
        elif arg.startswith("http") or " " in arg:
            parts.append('"' + arg + '"')          # URL и значения с пробелом
        else:
            parts.append(arg)
    return " ".join(parts)


def split_response(text: str) -> tuple[str, str]:
    """Делит ответ curl -i на заголовки и тело."""
    for separator in ("\r\n\r\n", "\n\n"):
        if separator in text:
            head, body = text.split(separator, 1)
            return head, body
    return "", text


def status_line(headers: str) -> str:
    """Возвращает первую строку ответа, например 'HTTP/1.1 200 OK'."""
    return headers.splitlines()[0] if headers.strip() else "нет заголовков"


def clip(text: str, max_lines: int = 24, max_chars: int = 1600) -> str:
    """Обрезает длинный ответ, чтобы отчёт оставался читаемым."""
    text = text.strip("\n")
    lines = text.splitlines()
    shown = lines[:max_lines]
    body = "\n".join(shown)
    if len(body) > max_chars:
        body = body[:max_chars]

    truncated = len(lines) > max_lines or len(text) > max_chars
    if truncated:
        note = f"\n  ... (ответ обрезан: показано {len(body)} из {len(text)} символов"
        if len(lines) > max_lines:
            note += f"; строк {min(len(lines), max_lines)} из {len(lines)}"
        body += note + ")"
    return body


def indent(text: str, spaces: int = 2) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


def block(
    rep: report.Report,
    number: str,
    title: str,
    args: list[str],
    comment: str,
    max_lines: int = 24,
    max_chars: int = 1600,
) -> tuple[int, str, str]:
    """Один сценарий: печатает команду, выполняет её, печатает ответ и вывод."""
    rep.subheading(f"{number}. {title}")
    rep.write("Команда:")
    rep.write("  " + format_command(args))
    rep.write()
    rep.write("Ответ (то, что вернул сервер):")

    code, text = run_curl(args)
    rep.write(indent(clip(text, max_lines, max_chars)))
    rep.write()
    rep.write(f"Что показывает: {comment}")
    rep.write()
    return code, text, split_response(text)[1]


# ---------------------------------------------------------------------------
# Основной сценарий
# ---------------------------------------------------------------------------
def main(base_url: str = config.API_URL) -> int:
    base_url = base_url.rstrip("/")
    api = f"{base_url}{config.API_TRANSACTIONS_PATH}"

    if not api_alive(base_url):
        print(
            f"Сервер API по адресу {base_url} не отвечает.\n"
            f"Запустите его в отдельном терминале:\n"
            f"    python lab_2.py server\n"
            f"и повторите запуск: python lab_2.py curl"
        )
        return 2

    config.ensure_dirs()
    rep = report.Report(config.CURL_REPORT)

    before = api_count(base_url)

    rep.heading("ЛАБОРАТОРНАЯ РАБОТА II. ЭТАП A. "
                "ДИАГНОСТИКА И ТЕСТИРОВАНИЕ API СРЕДСТВАМИ curl")
    rep.write(f"Дата выполнения : {datetime.now():%Y-%m-%d %H:%M:%S}")
    rep.write(f"Сервер          : {base_url}")
    rep.write(f"curl            : {CURL}")
    rep.write(f"Рабочая папка   : {ROOT}")
    rep.write(f"Операций в API до начала тестов: {before}")
    rep.write()
    rep.write("Все команды выполнялись из корня проекта. В PowerShell имя curl —")
    rep.write("алиас Invoke-WebRequest, поэтому ниже явно указан curl.exe.")

    # --- 1. Версия и протоколы -------------------------------------------
    block(
        rep,
        "1",
        "Версия curl и поддерживаемые протоколы",
        ["--version"],
        "версию, дату сборки, библиотеку TLS и полный список протоколов, "
        "которые включены именно в эту сборку.",
        max_lines=10,
    )

    # --- 2. GET списка + заголовки ответа --------------------------------
    block(
        rep,
        "2",
        "GET списка ресурсов + вывод заголовков ответа (-i)",
        [*BASE_ARGS, "-i", f"{api}?limit=3"],
        "ключ -i добавляет к телу ответа заголовки: код 200, content-type, "
        "заголовок X-Total-Count (сколько всего записей подходит под фильтр).",
    )

    # --- 3. HEAD ----------------------------------------------------------
    block(
        rep,
        "3",
        "HEAD-запрос: только заголовки (-I)",
        [*BASE_ARGS, "-I", api],
        "тот же ресурс, но тело не передаётся — удобно для быстрой проверки "
        "доступности и кода ответа.",
        max_lines=12,
    )

    # --- 4. GET одного ресурса + свой заголовок --------------------------
    block(
        rep,
        "4",
        "GET одного ресурса + собственный HTTP-заголовок (-H)",
        [*BASE_ARGS, "-i", "-H", "X-Student: lab2-demo", f"{api}/1001"],
        "один ресурс по идентификатору; сервер вернул заголовок "
        "X-Echo-Student, то есть собственный заголовок действительно дошёл.",
    )

    # --- 5. Query-параметры ----------------------------------------------
    block(
        rep,
        "5",
        "Передача query-параметров: фильтр по org_id",
        [*BASE_ARGS, f"{api}?org_id=999"],
        "фильтрация выполняется на сервере. org_id=999 — это «чужая» операция, "
        "которой нет в справочнике организаций (пригодится на этапах D–F).",
        max_lines=16,
    )
    block(
        rep,
        "6",
        "Несколько query-параметров: валюта и ограничение количества",
        [*BASE_ARGS, f"{api}?currency=RUB&limit=2"],
        "параметры соединяются через &, сервер применяет их вместе.",
        max_lines=14,
    )

    # --- 7. Redirect ------------------------------------------------------
    block(
        rep,
        "7",
        "Redirect без следования и со следованием (-L)",
        [*BASE_ARGS, "-i", f"{base_url}/api/v1/transactions"],
        "старый адрес отвечает 307 и заголовком Location — без -L curl "
        "останавливается на редиректе.",
        max_lines=12,
    )
    block(
        rep,
        "8",
        "Следование redirect (-L)",
        [*BASE_ARGS, "-L", "-i", f"{base_url}/api/v1/transactions"],
        "с -L curl сам переходит по Location и возвращает уже данные. "
        "Код 307 сохраняет метод запроса.",
        max_lines=14,
    )

    # --- 9. Запись ответа в файл -----------------------------------------
    if OUTPUT_JSON.exists():
        OUTPUT_JSON.unlink()
    code, text, _ = block(
        rep,
        "9",
        "Запись ответа в файл (-o) и заголовков в отдельный файл (-D)",
        [
            *BASE_ARGS,
            "-D", str(OUTPUT_HEADERS.relative_to(ROOT)).replace("\\", "/"),
            "-o", str(OUTPUT_JSON.relative_to(ROOT)).replace("\\", "/"),
            "-w", "HTTP %{http_code}, получено %{size_download} байт",
            f"{api}?limit=1000",
        ],
        "тело ответа уходит в файл, а не на экран; -w печатает итоговый код "
        "и размер. Так же данные забираются в конвейер — файл потом читается pandas.",
        max_lines=12,
    )

    if OUTPUT_JSON.exists():
        payload = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
        rep.write(f"Проверка файла {OUTPUT_JSON.name}: {len(payload)} записей, "
                  f"{OUTPUT_JSON.stat().st_size} байт.")
        rep.write(f"Первые строки файла заголовков {OUTPUT_HEADERS.name}:")
        headers_text = OUTPUT_HEADERS.read_text(encoding="utf-8", errors="replace")
        rep.write(indent(clip(headers_text, max_lines=8), 2))
        rep.write()

    # --- 10. POST ---------------------------------------------------------
    post_body = json.dumps(
        {"org_id": 16, "date": "2026-10-21", "amount": 152000.5, "currency": "RUB"},
        ensure_ascii=False,
    )
    code, text, body = block(
        rep,
        "10",
        "POST: создание ресурса (JSON в теле через -d)",
        [
            *BASE_ARGS,
            "-i",
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", post_body,
            api,
        ],
        "сервер принял JSON и вернул 201 Created вместе с присвоенным "
        "transaction_id.",
    )

    try:
        created = json.loads(body)
        new_id = int(created["transaction_id"])
    except (ValueError, KeyError, TypeError):
        rep.write("Не удалось разобрать ответ POST — дальнейшие шаги пропущены.")
        rep.close()
        return 1

    rep.write(f"Созданная запись: transaction_id={new_id}. "
              f"Дальше меняем и удаляем именно её, чтобы не портить исходные данные.")
    rep.write()

    # --- 11. PUT ----------------------------------------------------------
    put_body = json.dumps(
        {"org_id": 16, "date": "2026-10-22", "amount": 160000.0, "currency": "RUB"},
        ensure_ascii=False,
    )
    block(
        rep,
        "11",
        "PUT: полная замена ресурса",
        [
            *BASE_ARGS,
            "-i",
            "-X", "PUT",
            "-H", "Content-Type: application/json",
            "-d", put_body,
            f"{api}/{new_id}",
        ],
        "PUT присылает объект целиком: изменились и дата, и сумма.",
    )

    # --- 12. PATCH --------------------------------------------------------
    block(
        rep,
        "12",
        "PATCH: частичное изменение (только одно поле)",
        [
            *BASE_ARGS,
            "-i",
            "-X", "PATCH",
            "-H", "Content-Type: application/json",
            "-d", '{"amount": 175000.0}',
            f"{api}/{new_id}",
        ],
        "PATCH меняет только присланные поля, остальные остаются как были.",
    )

    # --- 13. DELETE -------------------------------------------------------
    block(
        rep,
        "13",
        "DELETE: удаление ресурса",
        [*BASE_ARGS, "-i", "-X", "DELETE", f"{api}/{new_id}"],
        "сервер вернул 204 No Content — удалено, тела ответа нет.",
        max_lines=10,
    )

    # --- 14. Проверка, что запись удалена ---------------------------------
    block(
        rep,
        "14",
        "GET удалённой записи: проверка кода 404",
        [*BASE_ARGS, "-i", f"{api}/{new_id}"],
        "ресурса больше нет, сервер отвечает 404 и пояснением в JSON.",
        max_lines=10,
    )

    # --- 15. Ошибка валидации --------------------------------------------
    block(
        rep,
        "15",
        "Ошибка валидации: отрицательная сумма -> 422",
        [
            *BASE_ARGS,
            "-i",
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", '{"org_id": 16, "date": "2026-10-21", "amount": -5, "currency": "RUB"}',
            api,
        ],
        "сервер проверяет данные по схеме (amount > 0) и не создаёт запись.",
        max_lines=16,
    )

    # --- Итог -------------------------------------------------------------
    after = api_count(base_url)
    rep.heading("ИТОГ ЭТАПА A")
    rep.write("Проверены методы: GET (список), HEAD, GET (один ресурс), POST, PUT, PATCH, DELETE.")
    rep.write("Проверены параметры curl: -i, -I, -H, -d, -L, -o, -D, -w, query-параметры в URL.")
    rep.write(f"Число операций в API: до тестов {before}, после тестов {after} -> "
              f"{'исходные данные не изменились' if before == after else 'ДАННЫЕ ИЗМЕНИЛИСЬ'}.")
    rep.write()
    rep.write("Замечание: PUT/PATCH/DELETE выполнялись над специально созданной записью,")
    rep.write("поэтому набор данных для этапов C–G остался тем же.")
    rep.close()

    print(f"\nОтчёт сохранён: {config.CURL_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
