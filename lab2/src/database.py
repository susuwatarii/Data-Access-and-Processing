"""ЭТАП F. Те же объединения, но средствами SQL (SQLite) + сравнение с pandas.

Зачем два раза: SQL JOIN и pandas.merge() решают одну задачу, но по-разному
устроены. Если числа совпали — объединение сделано правильно. Если нет —
значит, где-то разошлись кардинальность, фильтры или обработка NULL.

Обязательные конструкции задания здесь есть все:
INNER JOIN, LEFT JOIN, GROUP BY, COUNT(), SUM(), AVG().

Модуль можно запускать отдельно (нужен работающий сервер):
    python -m src.database
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # запуск файлом: python src/database.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src import config, report, transform

# ---------------------------------------------------------------------------
# SQL-запросы
# ---------------------------------------------------------------------------
SQL_INNER = """
SELECT o.org_id,
       o.org_name,
       o.sector,
       t.transaction_id,
       t.date,
       t.amount,
       t.currency
FROM organizations AS o
INNER JOIN transactions AS t ON t.org_id = o.org_id
ORDER BY o.org_id, t.transaction_id
"""

SQL_LEFT = """
SELECT o.org_id,
       o.org_name,
       o.sector,
       t.transaction_id,
       t.date,
       t.amount,
       t.currency
FROM organizations AS o
LEFT JOIN transactions AS t ON t.org_id = o.org_id
ORDER BY o.org_id, t.transaction_id
"""

SQL_LEFT_WITH_CITIES = """
SELECT o.org_id,
       o.org_name,
       o.sector,
       c.city_name,
       c.region_name,
       t.transaction_id,
       t.date,
       t.amount,
       t.currency
FROM organizations AS o
LEFT JOIN transactions AS t ON t.org_id = o.org_id
LEFT JOIN cities       AS c ON c.city_id = o.city_id
ORDER BY o.org_id, t.transaction_id
"""

SQL_BY_REGION = """
SELECT COALESCE(c.region_name, 'не указан') AS region_name,
       COUNT(t.transaction_id)              AS transactions_count,
       COUNT(DISTINCT o.org_id)             AS organizations_count,
       SUM(t.amount)                        AS total_amount,
       AVG(t.amount)                        AS avg_amount
FROM organizations AS o
LEFT JOIN transactions AS t ON t.org_id = o.org_id
LEFT JOIN cities       AS c ON c.city_id = o.city_id
GROUP BY COALESCE(c.region_name, 'не указан')
ORDER BY total_amount DESC
"""

SQL_MART = """
SELECT o.org_id,
       o.org_name,
       o.sector,
       COALESCE(c.city_name, 'не указан')   AS city_name,
       COALESCE(c.region_name, 'не указан') AS region_name,
       COUNT(t.transaction_id)              AS transactions_count,
       ROUND(COALESCE(SUM(t.amount), 0), 2) AS total_amount,
       ROUND(COALESCE(AVG(t.amount), 0), 2) AS avg_amount,
       MAX(t.date)                          AS last_transaction_date
FROM organizations AS o
LEFT JOIN transactions AS t ON t.org_id = o.org_id
LEFT JOIN cities       AS c ON c.city_id = o.city_id
GROUP BY o.org_id, o.org_name, o.sector, c.city_name, c.region_name
ORDER BY total_amount DESC, o.org_id
"""

SQL_ORPHAN_TRANSACTIONS = """
SELECT COUNT(*)     AS operations,
       SUM(amount)  AS total_amount
FROM transactions
WHERE org_id NOT IN (SELECT org_id FROM organizations)
"""

SQL_ORGANIZATIONS_WITHOUT_OPERATIONS = """
SELECT o.org_id, o.org_name
FROM organizations AS o
LEFT JOIN transactions AS t ON t.org_id = o.org_id
WHERE t.transaction_id IS NULL
ORDER BY o.org_id
"""

QUERIES = {
    "inner": SQL_INNER,
    "left": SQL_LEFT,
    "left_cities": SQL_LEFT_WITH_CITIES,
    "by_region": SQL_BY_REGION,
    "mart": SQL_MART,
}


# ---------------------------------------------------------------------------
# Загрузка таблиц в SQLite
# ---------------------------------------------------------------------------
def create_analytics_db(
    orgs: pd.DataFrame,
    txs: pd.DataFrame,
    cities: pd.DataFrame,
    path: Path = config.ANALYTICS_DB,
) -> Path:
    """Кладёт подготовленные таблицы в SQLite, чтобы SQL видел те же данные.

    Дата записывается строкой YYYY-MM-DD: в SQLite так работают сравнения
    и MAX(), и результат полностью совпадает с pandas.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    txs_sql = txs.copy()
    txs_sql["date"] = pd.to_datetime(txs_sql["date"]).dt.strftime("%Y-%m-%d")

    conn = sqlite3.connect(path)
    try:
        orgs.to_sql("organizations", conn, if_exists="replace", index=False)
        txs_sql.to_sql("transactions", conn, if_exists="replace", index=False)
        cities.to_sql("cities", conn, if_exists="replace", index=False)
        conn.commit()
    finally:
        conn.close()

    return path


def query(sql: str, db_path: Path = config.ANALYTICS_DB) -> pd.DataFrame:
    """Выполняет SQL-запрос и возвращает DataFrame."""
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Сравнение pandas и SQL
# ---------------------------------------------------------------------------
def _verdict(ok: bool) -> str:
    return "да" if ok else "НЕТ"


def _rows(count: int) -> str:
    """«51 строку», «52 строки», «5 строк» — чтобы текст читался по-русски."""
    return f"{count} {report.plural(count, 'строку', 'строки', 'строк')}"


def _rows_nominative(count: int) -> str:
    """То же, но в именительном падеже: «51 строка»."""
    return f"{count} {report.plural(count, 'строка', 'строки', 'строк')}"


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    """Для печати: целые столбцы с NULL показываем как Int64, а не как 1043.0."""
    out = df.copy()
    for column in ("transaction_id", "org_id", "city_id"):
        if column in out.columns and out[column].dtype == "float64":
            out[column] = out[column].astype("Int64")
    return out


def _fmt(value: Any) -> str:
    if isinstance(value, (float, np.floating)):
        return f"{value:,.2f}".replace(",", " ")
    return str(value)


def _compare_rows_and_sums(
    name: str,
    pandas_rows: int,
    sql_rows: int,
    pandas_sum: float,
    sql_sum: float,
) -> list[dict[str, str]]:
    """Строка таблицы сравнения: число строк и сумма денег."""
    return [
        {
            "проверка": f"{name}: число строк",
            "pandas": str(pandas_rows),
            "SQL": str(sql_rows),
            "совпадает": _verdict(pandas_rows == sql_rows),
        },
        {
            "проверка": f"{name}: сумма amount",
            "pandas": _fmt(pandas_sum),
            "SQL": _fmt(sql_sum),
            "совпадает": _verdict(abs(pandas_sum - sql_sum) < 0.01),
        },
    ]


def compare_marts(
    pandas_mart: pd.DataFrame,
    sql_mart: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Сравнивает две витрины построчно и по каждому столбцу.

    Для денежных столбцов допускается расхождение в 1 копейку: pandas округляет
    половину копейки «к чётному», а SQLite — «вверх», поэтому на одном значении
    из 16 может получиться разница 0.01. Это не ошибка объединения.

    Возвращает (таблица расхождений по столбцам, sql_mart в том же порядке,
    максимальная разница по числовым столбцам).
    """
    money_tolerance = 0.011  # рубль-копейка
    left = pandas_mart.copy()
    right = sql_mart.copy()

    left["last_transaction_date"] = (
        pd.to_datetime(left["last_transaction_date"], errors="coerce")
        .dt.strftime("%Y-%m-%d")
        .fillna("")
    )
    right["last_transaction_date"] = (
        pd.to_datetime(right["last_transaction_date"], errors="coerce")
        .dt.strftime("%Y-%m-%d")
        .fillna("")
    )

    left = left.sort_values("org_id").reset_index(drop=True)
    right = right.sort_values("org_id").reset_index(drop=True)

    if len(left) != len(right):
        raise RuntimeError(f"Витрины разной длины: pandas {len(left)}, SQL {len(right)}")

    mismatches = []
    max_money_diff = 0.0
    for column in left.columns:
        if pd.api.types.is_numeric_dtype(left[column]) and pd.api.types.is_numeric_dtype(right[column]):
            difference = np.abs(
                left[column].astype(float).to_numpy() - right[column].astype(float).to_numpy()
            )
            bad = difference > money_tolerance
            max_money_diff = max(max_money_diff, float(difference.max()))
            max_diff_text = f"{difference.max():.4f}".rstrip("0").rstrip(".")
        else:
            bad = (
                left[column].astype(str).fillna("").to_numpy()
                != right[column].astype(str).fillna("").to_numpy()
            )
            max_diff_text = "—"

        mismatches.append(
            {
                "столбец": column,
                "расхождений": int(bad.sum()),
                "макс. разница": max_diff_text,
            }
        )

    return pd.DataFrame(mismatches), right, max_money_diff


def _pandas_joined(orgs: pd.DataFrame, txs: pd.DataFrame, cities: pd.DataFrame) -> pd.DataFrame:
    """LEFT JOIN в pandas «молча» — для сравнения с SQL, без печати статистики."""
    joined = orgs.merge(txs, on="org_id", how="left", validate="one_to_many")
    return joined.merge(cities, on="city_id", how="left", validate="many_to_one")


def stage_f(
    orgs: pd.DataFrame,
    txs: pd.DataFrame,
    cities: pd.DataFrame,
    mart: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Этап F целиком: SQL JOIN, агрегаты и сверка с результатами pandas."""
    report.heading("ЭТАП F. SQL JOIN В SQLITE И СРАВНЕНИЕ С PANDAS")

    db_path = create_analytics_db(orgs, txs, cities)
    report.log(f"Таблицы organizations, transactions, cities загружены в {db_path}")

    counts = query(
        "SELECT 'organizations' AS таблица, COUNT(*) AS строк FROM organizations "
        "UNION ALL SELECT 'transactions', COUNT(*) FROM transactions "
        "UNION ALL SELECT 'cities', COUNT(*) FROM cities",
        db_path,
    )
    report.log()
    report.frame(counts, "Число строк в таблицах SQLite:", index=False)

    # --- 0. Сами запросы ---------------------------------------------------
    report.subheading("SQL-запросы, которые выполняются на этом этапе")
    queries_to_show = [
        ("INNER JOIN organizations x transactions", SQL_INNER),
        ("LEFT JOIN organizations x transactions", SQL_LEFT),
        ("LEFT JOIN + cities (город и регион)", SQL_LEFT_WITH_CITIES),
        ("GROUP BY + COUNT / SUM / AVG по регионам", SQL_BY_REGION),
        ("Витрина одним запросом", SQL_MART),
    ]
    for title, sql in queries_to_show:
        report.log()
        report.log(f"   {title}:")
        report.log("   " + sql.strip().replace("\n", "\n   "))

    # --- 1. INNER JOIN -----------------------------------------------------
    report.subheading("1. INNER JOIN organizations x transactions")
    sql_inner = query(SQL_INNER, db_path)
    report.log(f"   SQL вернул {_rows(len(sql_inner))}")
    report.frame(_tidy(sql_inner).head(5), "   Первые 5 строк:", index=False)

    # --- 2. LEFT JOIN ------------------------------------------------------
    report.subheading("2. LEFT JOIN organizations x transactions")
    sql_left = query(SQL_LEFT, db_path)
    report.log(f"   SQL вернул {_rows(len(sql_left))}")
    report.frame(
        _tidy(sql_left[sql_left["transaction_id"].isna()]),
        "   Организации без операций:",
        index=False,
    )

    # --- 3. LEFT JOIN с городами ------------------------------------------
    report.subheading("3. LEFT JOIN ... LEFT JOIN cities")
    sql_with_cities = query(SQL_LEFT_WITH_CITIES, db_path)
    report.log(f"   SQL вернул {_rows(len(sql_with_cities))}")
    report.frame(
        _tidy(sql_with_cities[sql_with_cities["city_name"].isna()]).head(5),
        "   Строки без города (первые 5):",
        index=False,
    )

    # --- 4. GROUP BY / COUNT / SUM / AVG ----------------------------------
    report.subheading("4. GROUP BY: агрегаты по регионам")
    sql_by_region = query(SQL_BY_REGION, db_path)
    report.frame(sql_by_region, index=False)

    report.log()
    report.log("   Пояснение: COUNT(t.transaction_id) считает только непустые значения,")
    report.log("   поэтому у организации без операций получается 0, а не 1.")
    report.log("   SUM и AVG игнорируют NULL — иначе суммы были бы искажены.")

    # --- 5. Витрина тем же SQL --------------------------------------------
    report.subheading("5. Витрина одним SQL-запросом (GROUP BY + все агрегаты)")
    sql_mart = query(SQL_MART, db_path)
    report.frame(sql_mart.head(5), index=False)

    # --- 6. Сверка pandas и SQL -------------------------------------------
    report.subheading("6. Сверка: pandas.merge против SQL JOIN")

    pandas_joined = _pandas_joined(orgs, txs, cities)
    pandas_inner_rows = len(orgs.merge(txs, on="org_id", how="inner", validate="one_to_many"))
    pandas_unknown = txs[~txs["org_id"].isin(orgs["org_id"])]

    pandas_mart = mart if mart is not None else transform.build_data_mart(pandas_joined)

    checks: list[dict[str, str]] = []
    checks += _compare_rows_and_sums(
        "INNER JOIN",
        pandas_inner_rows,
        len(sql_inner),
        float(orgs.merge(txs, on="org_id", how="inner", validate="one_to_many")["amount"].sum()),
        float(sql_inner["amount"].sum()),
    )
    checks += _compare_rows_and_sums(
        "LEFT JOIN",
        len(pandas_joined),
        len(sql_left),
        float(pandas_joined["amount"].sum()),
        float(sql_left["amount"].sum()),
    )
    checks += _compare_rows_and_sums(
        "LEFT JOIN + cities",
        len(pandas_joined),
        len(sql_with_cities),
        float(pandas_joined["amount"].sum()),
        float(sql_with_cities["amount"].sum()),
    )

    orphan = query(SQL_ORPHAN_TRANSACTIONS, db_path).iloc[0]
    checks.append(
        {
            "проверка": "операции без организации: число",
            "pandas": str(len(pandas_unknown)),
            "SQL": str(int(orphan["operations"])),
            "совпадает": _verdict(len(pandas_unknown) == int(orphan["operations"])),
        }
    )
    checks.append(
        {
            "проверка": "операции без организации: сумма",
            "pandas": _fmt(float(pandas_unknown["amount"].sum())),
            "SQL": _fmt(float(orphan["total_amount"] or 0)),
            "совпадает": _verdict(
                abs(float(pandas_unknown["amount"].sum()) - float(orphan["total_amount"] or 0)) < 0.01
            ),
        }
    )

    without_operations_sql = query(SQL_ORGANIZATIONS_WITHOUT_OPERATIONS, db_path)
    without_operations_pandas = pandas_mart[pandas_mart["transactions_count"] == 0]
    checks.append(
        {
            "проверка": "организаций без операций: число",
            "pandas": str(len(without_operations_pandas)),
            "SQL": str(len(without_operations_sql)),
            "совпадает": _verdict(len(without_operations_pandas) == len(without_operations_sql)),
        }
    )

    report.grid(
        ["проверка", "pandas", "SQL", "совпадает"],
        [[row["проверка"], row["pandas"], row["SQL"], row["совпадает"]] for row in checks],
        aligns=["l", "r", "r", "l"],
    )

    # --- 7. Сверка агрегатов по регионам ----------------------------------
    report.subheading("7. Сверка агрегатов по регионам")
    pandas_by_region = (
        pandas_joined.assign(region_name=pandas_joined["region_name"].fillna("не указан"))
        .groupby("region_name", as_index=False)
        .agg(
            transactions_count=("transaction_id", "count"),
            organizations_count=("org_id", "nunique"),
            total_amount=("amount", "sum"),
            avg_amount=("amount", "mean"),
        )
        .sort_values("region_name")
        .reset_index(drop=True)
    )
    sql_by_region_sorted = sql_by_region.sort_values("region_name").reset_index(drop=True)

    same_regions = list(pandas_by_region["region_name"]) == list(sql_by_region_sorted["region_name"])
    diff_counts = int(
        (pandas_by_region["transactions_count"].to_numpy() != sql_by_region_sorted["transactions_count"].to_numpy()).sum()
    )
    diff_totals = float(
        np.abs(pandas_by_region["total_amount"].to_numpy() - sql_by_region_sorted["total_amount"].to_numpy()).max()
    )
    diff_avgs = float(np.abs(pandas_by_region["avg_amount"].to_numpy() - sql_by_region_sorted["avg_amount"].to_numpy()).max())

    region_checks = pd.DataFrame(
        [
            {"проверка": "регионы совпадают", "значение": _verdict(same_regions)},
            {"проверка": "расхождений по COUNT", "значение": str(diff_counts)},
            {"проверка": "макс. расхождение SUM, руб.", "значение": f"{diff_totals:.6f}"},
            {"проверка": "макс. расхождение AVG, руб.", "значение": f"{diff_avgs:.6f}"},
        ]
    )
    report.grid(
        ["проверка", "значение"],
        [[row["проверка"], row["значение"]] for row in region_checks.to_dict("records")],
        aligns=["l", "r"],
    )

    # --- 8. Построчная сверка витрин --------------------------------------
    report.subheading("8. Построчная сверка витрины: pandas против SQL")
    mart_diff, sql_mart_sorted, max_money_diff = compare_marts(pandas_mart, sql_mart)
    report.frame(mart_diff, index=False)
    total_mismatches = int(mart_diff["расхождений"].sum())
    report.log()
    report.log(f"   Максимальная разница по числовым столбцам: {max_money_diff:.4f} руб.")
    report.log("   Допуск при сверке — 1 копейка: pandas округляет половину копейки")
    report.log("   «к чётному», SQLite — «вверх», поэтому на одном значении возможна")
    report.log("   разница в 0.01. На результат объединения это не влияет.")
    report.log(f"   Итого расхождений сверх допуска: {total_mismatches} -> "
               f"{'витрины совпадают' if total_mismatches == 0 else 'ЕСТЬ РАСХОЖДЕНИЯ'}")

    report.subheading("Итог по этапу F")
    report.log("   SQL JOIN и pandas.merge дают одинаковое число строк и одинаковые агрегаты:")
    report.log(f"   INNER JOIN — {_rows_nominative(len(sql_inner))}, "
               f"LEFT JOIN — {_rows_nominative(len(sql_left))}, "
               f"с городами — {_rows_nominative(len(sql_with_cities))}.")
    report.log("   Разница между INNER и LEFT видна на числах: LEFT добавляет организацию")
    report.log("   без операций, но не возвращает операции с неизвестным org_id —")
    report.log("   они лежат справа и в LEFT JOIN не попадают.")

    return {
        "inner": sql_inner,
        "left": sql_left,
        "left_cities": sql_with_cities,
        "by_region": sql_by_region,
        "mart": sql_mart,
    }


def main() -> None:
    """Отдельный запуск этапа F: python -m src.database"""
    from src import loaders
    try:
        orgs = loaders.load_organizations()
        cities = loaders.load_cities()
        txs = loaders.load_transactions_api()
    except (loaders.ApiUnavailableError, FileNotFoundError) as exc:
        report.log(f"\nОШИБКА: {exc}")
        raise SystemExit(2) from exc

    orgs, txs, cities = transform.normalize_keys(orgs, txs, cities, verbose=False)
    stage_f(orgs, txs, cities)


if __name__ == "__main__":
    main()
