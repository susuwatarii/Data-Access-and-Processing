"""ЭТАП C. Загрузка трёх источников в Python.

Три разных способа получить данные — три разных библиотеки:

* organizations.csv  -> pandas.read_csv()          (файл);
* cities             -> sqlite3 + pandas.read_sql() (база данных);
* transactions       -> requests.get()              (REST API).

Для каждого набора печатаем то, что требует задание: shape, dtypes, head(),
isna().sum(), число уникальных ключей и число дубликатов.

Модуль можно запускать отдельно (нужен работающий сервер):
    python -m src.loaders
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # запуск файлом: python src/loaders.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from src import config, report

TRANSACTION_COLUMNS = ["transaction_id", "org_id", "date", "amount", "currency"]


class ApiUnavailableError(RuntimeError):
    """Сервер API не отвечает — обычно просто не запущен."""


# ---------------------------------------------------------------------------
# Загрузчики
# ---------------------------------------------------------------------------
def load_organizations(path: Path = config.ORGANIZATIONS_CSV) -> pd.DataFrame:
    """Источник №1: CSV-файл с организациями.

    dtype намеренно не задаём: пусть pandas определит типы сама. Именно так
    на этапе D обнаруживается, что city_id из-за одного пустого значения
    стал float64, а city_id в SQLite — int64. Это и есть причина, по которой
    перед merge() ключи надо приводить к одному типу.
    """
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Не найден {path}. Создайте исходные данные: python lab_2.py init"
        )
    return pd.read_csv(path)


def load_cities(db_path: Path = config.REGIONS_DB, table: str = "cities") -> pd.DataFrame:
    """Источник №2: таблица cities из SQLite (регионы и население)."""
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"Не найдена база {db_path}. Создайте исходные данные: python lab_2.py init"
        )

    conn = sqlite3.connect(str(db_path))
    try:
        return pd.read_sql_query(f'SELECT * FROM "{table}" ORDER BY city_id', conn)
    finally:
        conn.close()


def load_transactions_api(
    base_url: str = config.API_URL,
    timeout: float = 10.0,
    limit: int = 1000,
) -> pd.DataFrame:
    """Источник №3: операции через REST API (GET /api/transactions)."""
    url = f"{base_url.rstrip('/')}{config.API_TRANSACTIONS_PATH}"
    params = {"limit": limit}

    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise ApiUnavailableError(
            f"Не удалось получить данные от API ({url}).\n"
            f"Причина: {exc}\n"
            f"Запустите сервер в отдельном терминале: python lab_2.py server"
        ) from exc

    if response.status_code != 200:
        raise ApiUnavailableError(
            f"API вернул HTTP {response.status_code} вместо 200: {response.text[:300]}"
        )

    payload: Any = response.json()
    if not isinstance(payload, list):
        raise ApiUnavailableError("Ожидался JSON-массив операций от /api/transactions")
    if not payload:
        raise ApiUnavailableError("API вернул пустой список операций")

    df = pd.DataFrame(payload)
    # Порядок столбцов как в задании (на случай, если сервер вернёт другой порядок).
    return df[[column for column in TRANSACTION_COLUMNS if column in df.columns]]


# ---------------------------------------------------------------------------
# Печать характеристик набора (этап C)
# ---------------------------------------------------------------------------
def summarize(
    df: pd.DataFrame,
    name: str,
    key: str,
    join_key: str | None = None,
    how: str = "",
) -> dict[str, Any]:
    """Печатает shape / dtypes / head / isna / уникальные ключи / дубликаты."""
    report.subheading(f"{name}  ({how})")

    report.log(
        f"   shape: {df.shape[0]} {report.plural(df.shape[0], 'строка', 'строки', 'строк')}"
        f" x {df.shape[1]} {report.plural(df.shape[1], 'столбец', 'столбца', 'столбцов')}"
    )

    dtypes = pd.DataFrame(
        {
            "столбец": df.columns,
            "dtype": [str(dtype) for dtype in df.dtypes],
        }
    )
    report.frame(dtypes, "   dtypes:")

    report.log("   head():")
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        report.log(_indent(df.head().to_string(index=False), 5))

    missing = df.isna().sum()
    missing = missing[missing > 0]
    if missing.empty:
        report.log("   isna().sum(): пропусков нет")
    else:
        report.log("   isna().sum():")
        report.log(_indent(missing.to_string(), 5))

    unique_keys = int(df[key].nunique(dropna=True))
    report.log(f"   уникальных значений {key}: {unique_keys}")

    duplicate_keys = int(df.duplicated(subset=[key]).sum())
    report.log(f"   дублей по ключу {key}: {duplicate_keys}")

    duplicate_rows = int(df.duplicated().sum())
    report.log(f"   полностью повторяющихся строк: {duplicate_rows}")

    if join_key is not None and join_key != key:
        report.log(f"   уникальных значений ключа связи {join_key}: "
                   f"{int(df[join_key].nunique(dropna=True))}")

    return {
        "источник": name,
        "строк": int(df.shape[0]),
        "столбцов": int(df.shape[1]),
        "ключ": key,
        "уникальных ключей": unique_keys,
        "дублей по ключу": duplicate_keys,
        "дублей строк": duplicate_rows,
        "пропусков": int(df.isna().sum().sum()),
    }


def _indent(text: str, spaces: int) -> str:
    """Сдвигает многострочный текст вправо — чтобы таблицы читались в отчёте."""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


def stage_c(
    orgs: pd.DataFrame | None = None,
    txs: pd.DataFrame | None = None,
    cities: pd.DataFrame | None = None,
    api_url: str = config.API_URL,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Этап C целиком: загружает и описывает три источника."""
    report.heading("ЭТАП C. ЗАГРУЗКА ИСТОЧНИКОВ В PYTHON")

    if orgs is None:
        orgs = load_organizations()
    if cities is None:
        cities = load_cities()
    if txs is None:
        txs = load_transactions_api(api_url)

    stats = [
        summarize(orgs, "organizations", key="org_id", how="CSV -> pandas.read_csv"),
        summarize(txs, "transactions", key="transaction_id", join_key="org_id",
                  how=f"REST API -> requests.get({api_url}{config.API_TRANSACTIONS_PATH})"),
        summarize(cities, "cities", key="city_id", how="SQLite -> pandas.read_sql_query"),
    ]

    report.subheading("Сводка по источникам")
    summary = pd.DataFrame(stats).set_index("источник")
    report.frame(summary, index=True)

    report.log()
    report.log("Вывод: три источника получены разными способами (файл, БД, API),")
    report.log("у них разные типы ключей и разное число строк — объединять их")
    report.log("«как есть» нельзя, сначала нужна проверка ключей (этап D).")

    return orgs, txs, cities


def main() -> None:
    """Отдельный запуск этапа C: python -m src.loaders"""
    try:
        stage_c()
    except (ApiUnavailableError, FileNotFoundError) as exc:
        report.log(f"\nОШИБКА: {exc}")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
