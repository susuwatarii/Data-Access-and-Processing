"""ЭТАПЫ D, E, G. Проверка ключей, объединение в pandas и аналитическая витрина.

Порядок работы (именно в таком порядке, а не «сразу merge»):

    D. привести ключи к одному типу, проверить дубли, NULL, ключи только слева
       и только справа, определить ожидаемую кардинальность связи;
    E. объединить organizations + transactions (INNER и LEFT), затем LEFT JOIN
       с cities, контролируя результат через indicator=True и validate=...;
    G. собрать витрину: одна строка = одна организация, с агрегатами по операциям.

Ключевая мысль для защиты: merge() сам по себе не ошибается — он делает ровно
то, что ему сказали. Ошибки появляются, когда кардинальность связи не совпадает
с ожидаемой: если org_id в организациях не уникален, LEFT JOIN размножит строки,
и суммы удвоятся. Поэтому validate обязателен.

Модуль можно запускать отдельно (нужен работающий сервер):
    python -m src.transform
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # запуск файлом: python src/transform.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src import config, report

MART_COLUMNS = [
    "org_id",
    "org_name",
    "sector",
    "city_name",
    "region_name",
    "transactions_count",
    "total_amount",
    "avg_amount",
    "last_transaction_date",
]

NO_CITY_LABEL = "не указан"


# ---------------------------------------------------------------------------
# ЭТАП D. Очистка ключей
# ---------------------------------------------------------------------------
def _to_int(series: pd.Series) -> pd.Series:
    """Приводит ключ к целому типу Int64 (он умеет хранить <NA>)."""
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def normalize_keys(
    orgs: pd.DataFrame,
    txs: pd.DataFrame,
    cities: pd.DataFrame,
    verbose: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Приводит org_id и city_id к одинаковому типу во всех трёх наборах.

    Почему это обязательно: в organizations.csv одно пустое значение city_id
    превращает столбец в float64, а city_id в SQLite — целое int64.
    pandas.merge() на разных типах падает с ошибкой, поэтому приводим оба
    ключа к Int64 (целое число + поддержка пропуска).
    """
    before = [
        ("organizations", "org_id", str(orgs["org_id"].dtype)),
        ("organizations", "city_id", str(orgs["city_id"].dtype)),
        ("transactions", "transaction_id", str(txs["transaction_id"].dtype)),
        ("transactions", "org_id", str(txs["org_id"].dtype)),
        ("cities", "city_id", str(cities["city_id"].dtype)),
    ]

    orgs_clean = orgs.copy()
    orgs_clean["org_id"] = _to_int(orgs_clean["org_id"])
    orgs_clean["city_id"] = _to_int(orgs_clean["city_id"])

    txs_clean = txs.copy()
    txs_clean["transaction_id"] = _to_int(txs_clean["transaction_id"])
    txs_clean["org_id"] = _to_int(txs_clean["org_id"])
    txs_clean["amount"] = pd.to_numeric(txs_clean["amount"], errors="coerce").astype("float64")
    txs_clean["date"] = pd.to_datetime(txs_clean["date"], errors="coerce")

    cities_clean = cities.copy()
    cities_clean["city_id"] = _to_int(cities_clean["city_id"])
    cities_clean["population"] = _to_int(cities_clean["population"])

    after = [
        ("organizations", "org_id", str(orgs_clean["org_id"].dtype)),
        ("organizations", "city_id", str(orgs_clean["city_id"].dtype)),
        ("transactions", "transaction_id", str(txs_clean["transaction_id"].dtype)),
        ("transactions", "org_id", str(txs_clean["org_id"].dtype)),
        ("cities", "city_id", str(cities_clean["city_id"].dtype)),
    ]

    if verbose:
        report.subheading("1. Приведение ключей к одному типу")
        table = pd.DataFrame(before, columns=["таблица", "ключ", "было"])
        table["стало"] = [row[2] for row in after]
        report.frame(table)
        report.log()
        report.log("   Int64 выбран потому, что он остаётся целым, но допускает <NA>:")
        report.log("   пустой city_id у организации 15 не превращается в 14.0/NaN-float.")
        report.log("   Кроме ключей, дата приведена к datetime64, сумма — к float64.")

    return orgs_clean, txs_clean, cities_clean


def check_duplicate_keys(items: list[tuple[str, pd.DataFrame, str]]) -> None:
    """Проверяет, что ключ в каждой таблице уникален (иначе связь станет N:N)."""
    for name, df, key in items:
        duplicates = int(df.duplicated(subset=[key]).sum())
        if duplicates == 0:
            report.log(f"   {name}.{key}: дублей нет (строк {len(df)}, ключей {df[key].nunique()})")
        else:
            report.log(f"   {name}.{key}: ДУБЛЕЙ {duplicates}")
            report.frame(df[df.duplicated(subset=[key], keep=False)].sort_values(key).head(5))


def check_missing_keys(items: list[tuple[str, pd.DataFrame, str]]) -> None:
    """Проверяет NULL в ключах: такие строки не найдут пару при JOIN."""
    for name, df, key in items:
        missing = int(df[key].isna().sum())
        if missing == 0:
            report.log(f"   {name}.{key}: пропусков нет")
        else:
            report.log(f"   {name}.{key}: пропусков {missing} (в JOIN останутся без пары)")
            report.frame(df[df[key].isna()].head(5))


def compare_key_sets(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_key: str,
    right_key: str,
    left_name: str,
    right_name: str,
) -> dict[str, Any]:
    """Ищет ключи, которые есть только слева и только справа."""
    left_values = set(left[left_key].dropna().tolist())
    right_values = set(right[right_key].dropna().tolist())

    only_left = sorted(left_values - right_values)
    only_right = sorted(right_values - left_values)
    both = sorted(left_values & right_values)

    def _preview(values: list[Any], limit: int = 10) -> str:
        shown = ", ".join(str(value) for value in values[:limit])
        if len(values) > limit:
            shown += f", ... (всего {len(values)})"
        return shown if shown else "—"

    report.log(f"   {left_name}.{left_key} всего: {len(left_values)}; "
               f"{right_name}.{right_key} всего: {len(right_values)}")
    report.log(f"   совпадают: {len(both)}")
    report.log(f"   только слева  ({left_name}): {len(only_left)} -> {_preview(only_left)}")
    report.log(f"   только справа ({right_name}): {len(only_right)} -> {_preview(only_right)}")

    return {
        "both": both,
        "only_left": only_left,
        "only_right": only_right,
    }


def check_cardinality(
    orgs: pd.DataFrame,
    txs: pd.DataFrame,
    cities: pd.DataFrame,
) -> pd.DataFrame:
    """Определяет ожидаемый тип связи между таблицами и что подавать в validate."""
    orgs_unique = orgs["org_id"].is_unique
    cities_unique = cities["city_id"].is_unique
    txns_per_org = txs.groupby("org_id").size()

    report.log(f"   organizations: {len(orgs)} "
               f"{report.plural(len(orgs), 'строка', 'строки', 'строк')}, "
               f"{orgs['org_id'].nunique()} уникальных org_id -> "
               f"{'одна строка на организацию' if orgs_unique else 'КЛЮЧ НЕ УНИКАЛЕН'}")
    report.log(f"   transactions: {len(txs)} "
               f"{report.plural(len(txs), 'строка', 'строки', 'строк')}, "
               f"{txs['org_id'].nunique()} уникальных org_id, "
               f"в среднем {len(txs) / max(txs['org_id'].nunique(), 1):.1f} операции на организацию")
    report.log(f"   cities: {len(cities)} "
               f"{report.plural(len(cities), 'строка', 'строки', 'строк')}, "
               f"{cities['city_id'].nunique()} уникальных city_id -> "
               f"{'справочник, ключ уникален' if cities_unique else 'КЛЮЧ НЕ УНИКАЛЕН'}")
    report.log()
    report.log(f"   максимум операций на одну организацию: {int(txns_per_org.max())}")

    table = pd.DataFrame(
        [
            {
                "левая таблица": "organizations",
                "правая таблица": "transactions",
                "связь": "1:N (у одной организации много операций)",
                "validate": 'one_to_many',
            },
            {
                "левая таблица": "transactions",
                "правая таблица": "cities",
                "связь": "N:1 (у многих операций один город)",
                "validate": 'many_to_one',
            },
            {
                "левая таблица": "organizations",
                "правая таблица": "cities",
                "связь": "N:1 (в городе много организаций)",
                "validate": 'many_to_one',
            },
        ]
    )
    report.frame(table)
    report.log()
    report.log("   Почему не подходят остальные варианты:")
    report.log("   - 1:1 — была бы, если бы у операции была ровно одна организация,")
    report.log("     а у организации — ровно одна операция; здесь у организации их несколько;")
    report.log("   - N:N — появилась бы, если бы org_id в справочнике перестал быть")
    report.log("     уникальным (дубль организации) или если бы связь шла через")
    report.log("     промежуточную таблицу; тогда строки размножились бы.")
    report.log()
    report.log("   ВАЖНО: связь organizations -> transactions является 1:N только")
    report.log("   потому, что org_id в organizations уникален. Если в справочник")
    report.log("   попадёт дубль организации, связь станет N:N и строки удвоятся.")
    return table


def show_duplicate_effect(orgs: pd.DataFrame, txs: pd.DataFrame) -> None:
    """Показывает, что произойдёт, если не проверить кардинальность.

    Берём справочник организаций и намеренно дублируем в нём одну строку,
    затем объединяем — без validate и с validate. Это ответ на вопрос
    «почему после JOIN появляются дубликаты».
    """
    broken = pd.concat([orgs, orgs.iloc[[0]]], ignore_index=True)
    baseline = len(orgs.merge(txs, on="org_id", how="left"))
    naive = len(broken.merge(txs, on="org_id", how="left"))

    report.log(f"   без проверки: дубль одной организации в справочнике "
               f"({len(orgs)} -> {len(broken)} строк) дал {naive} "
               f"{report.plural(naive, 'строку', 'строки', 'строк')} вместо {baseline}")
    report.log("   причина: у дублирующей организации столько же операций, сколько у исходной,")
    report.log("   поэтому каждая её операция попала в результат дважды и суммы удвоились.")

    try:
        broken.merge(txs, on="org_id", how="left", validate="one_to_many")
    except pd.errors.MergeError as exc:
        message = " ".join(str(exc).split())  # убираем переводы строк из текста ошибки
        report.log(f"   с validate='one_to_many': pandas останавливает объединение — {message}")


def stage_d(
    orgs: pd.DataFrame,
    txs: pd.DataFrame,
    cities: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Этап D целиком. Возвращает очищенные наборы для следующих этапов."""
    report.heading("ЭТАП D. ОЧИСТКА КЛЮЧЕЙ")

    orgs_clean, txs_clean, cities_clean = normalize_keys(orgs, txs, cities, verbose=True)

    report.subheading("2. Проверка дублей ключей")
    check_duplicate_keys(
        [
            ("organizations", orgs_clean, "org_id"),
            ("transactions", txs_clean, "transaction_id"),
            ("cities", cities_clean, "city_id"),
        ]
    )

    report.subheading("3. Проверка NULL в ключах")
    check_missing_keys(
        [
            ("organizations", orgs_clean, "org_id"),
            ("organizations", orgs_clean, "city_id"),
            ("transactions", txs_clean, "org_id"),
            ("cities", cities_clean, "city_id"),
        ]
    )

    report.subheading("4. Ключи, которые есть только слева / только справа")
    report.log("4.1 organizations.org_id <-> transactions.org_id")
    org_tx = compare_key_sets(orgs_clean, txs_clean, "org_id", "org_id", "organizations", "transactions")

    report.log()
    report.log("4.2 cities.city_id <-> organizations.city_id (город без организации)")
    city_org = compare_key_sets(cities_clean, orgs_clean, "city_id", "city_id", "cities", "organizations")

    report.log()
    report.log("4.3 cities.city_id <-> transactions.org_id напрямую сравнивать нельзя:")
    report.log("    в transactions хранится ключ организации, а не города. Город")
    report.log("    подтягивается только через organizations (это важно для этапа E).")

    report.log()
    orphan_transactions = txs_clean[~txs_clean["org_id"].isin(orgs_clean["org_id"])]
    orgs_without_transactions = orgs_clean[~orgs_clean["org_id"].isin(txs_clean["org_id"])]
    cities_without_orgs = cities_clean[~cities_clean["city_id"].isin(orgs_clean["city_id"].dropna())]
    orphan_sum = f"{orphan_transactions['amount'].sum():,.2f}".replace(",", " ")

    report.log("   Итог по этапу D:")
    report.log(f"   - операций с неизвестным org_id: {len(orphan_transactions)} "
               f"(org_id {sorted(orphan_transactions['org_id'].unique().tolist())}, "
               f"{orphan_sum} руб.) — теряются при INNER JOIN;")
    report.log(f"   - организаций без операций: {len(orgs_without_transactions)} "
               f"(org_id {orgs_without_transactions['org_id'].tolist()}) — "
               f"теряются при INNER JOIN;")
    report.log(f"   - городов без организаций: {len(cities_without_orgs)} "
               f"(city_id {cities_without_orgs['city_id'].tolist()}: "
               f"{', '.join(cities_without_orgs['city_name'].tolist())});")
    report.log(f"   - город не указан у {int(orgs_clean['city_id'].isna().sum())} организации "
               f"— при LEFT JOIN города она получит city_name = NaN.")

    report.subheading("5. Ожидаемая кардинальность связи")
    check_cardinality(orgs_clean, txs_clean, cities_clean)

    report.subheading("6. Что будет, если кардинальность не проверять")
    show_duplicate_effect(orgs_clean, txs_clean)

    return orgs_clean, txs_clean, cities_clean


# ---------------------------------------------------------------------------
# ЭТАП E. Объединение средствами pandas
# ---------------------------------------------------------------------------
def merge_orgs_transactions(
    orgs: pd.DataFrame,
    txs: pd.DataFrame,
    how: str = "inner",
) -> pd.DataFrame:
    """organizations + transactions.

    validate="one_to_many" означает: слева ключ уникален, справа может
    повторяться. Если в организациях появится дубль, pandas выбросит
    MergeError — и это лучше, чем незаметно удвоить суммы.
    """
    return orgs.merge(
        txs,
        on="org_id",
        how=how,
        indicator="_merge",
        validate="one_to_many",
    )


def merge_with_cities(joined: pd.DataFrame, cities: pd.DataFrame) -> pd.DataFrame:
    """К объединённому набору подтягиваем город и регион: много операций -> один город."""
    return joined.merge(
        cities,
        on="city_id",
        how="left",
        indicator="_merge_city",
        validate="many_to_one",
    )


def join_stats(
    joined: pd.DataFrame,
    rows_before: int,
    amount_before: float,
    indicator: str = "_merge",
) -> dict[str, Any]:
    """Считает, сколько строк было/стало и как распределились matched/left_only/right_only."""
    counts = joined[indicator].value_counts()
    return {
        "строк до": rows_before,
        "строк после": len(joined),
        "matched": int(counts.get("both", 0)),
        "left_only": int(counts.get("left_only", 0)),
        "right_only": int(counts.get("right_only", 0)),
        "сумма до": round(float(amount_before), 2),
        "сумма после": round(float(joined["amount"].sum()), 2),
    }


def print_join_stats(title: str, stats: dict[str, Any]) -> None:
    """Печатает статистику объединения в виде таблицы «показатель — значение».

    Значения приводим к строкам сразу: иначе pandas сделает столбец float,
    и число строк будет выглядеть как "53.00".
    """
    report.subheading(title)
    rows = []
    for key, value in stats.items():
        if isinstance(value, float):
            text = f"{value:,.2f}".replace(",", " ")
        else:
            text = str(value)
        rows.append([key, text])
    report.grid(["показатель", "значение"], rows, aligns=["l", "r"])


def stage_e(
    orgs: pd.DataFrame,
    txs: pd.DataFrame,
    cities: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Этап E целиком: INNER, LEFT по организациям и LEFT JOIN с городами."""
    report.heading("ЭТАП E. ОБЪЕДИНЕНИЕ СРЕДСТВАМИ PANDAS")

    orgs_clean, txs_clean, cities_clean = normalize_keys(orgs, txs, cities, verbose=False)
    report.log("Ключи приведены к Int64 (подробности — этап D).")
    report.log("Контроль происхождения строк: в каждом merge() включён indicator=True —")
    report.log("pandas добавляет столбец _merge со значениями both / left_only / right_only,")
    report.log("именно по нему считается статистика ниже.")

    # --- 1. INNER JOIN ----------------------------------------------------
    inner = merge_orgs_transactions(orgs_clean, txs_clean, how="inner")
    stats_inner = join_stats(inner, len(txs_clean), txs_clean["amount"].sum())
    print_join_stats(
        "1. organizations INNER JOIN transactions (validate='one_to_many')", stats_inner
    )
    orphan = txs_clean[~txs_clean["org_id"].isin(orgs_clean["org_id"])]
    orphan_sum = f"{orphan['amount'].sum():,.2f}".replace(",", " ")
    report.log(f"   Потеряно {len(orphan)} {report.plural(len(orphan), 'операция', 'операции', 'операций')} "
               f"без организации на сумму {orphan_sum} руб.")
    report.log("   INNER оставляет только те операции, для которых нашлась организация.")

    # --- 2. LEFT JOIN -----------------------------------------------------
    left = merge_orgs_transactions(orgs_clean, txs_clean, how="left")
    stats_left = join_stats(left, len(txs_clean), txs_clean["amount"].sum())
    print_join_stats(
        "2. organizations LEFT JOIN transactions (validate='one_to_many')", stats_left
    )
    lost_money = f"{float(txs_clean['amount'].sum()) - float(left['amount'].sum()):,.2f}".replace(",", " ")
    report.log(f"   Строк больше, чем в INNER, на {len(left) - len(inner)} — "
               f"это организация без операций (amount = NaN).")
    report.log(f"   right_only = {stats_left['right_only']}: в LEFT JOIN строки правой таблицы "
               f"без пары не появляются. Поэтому {len(orphan)} операции с неизвестным org_id")
    report.log(f"   здесь не видны, и сумма amount меньше исходной на {lost_money} руб.")
    report.log("   Строка организации без операций (amount = NaN) денег не добавляет.")

    # --- 3. LEFT JOIN с городами -----------------------------------------
    with_cities = merge_with_cities(left, cities_clean)
    stats_city = join_stats(with_cities, len(left), left["amount"].sum(), indicator="_merge_city")
    print_join_stats(
        "3. (organizations LEFT JOIN transactions) LEFT JOIN cities "
        "(validate='many_to_one')",
        stats_city,
    )
    report.log(f"   left_only = {stats_city['left_only']}: строки, которым не нашёлся город")
    report.log("   (у организации 15 пустой city_id, поэтому город и регион = NaN).")
    report.log(f"   Строк стало {len(with_cities)} — столько же, сколько было: "
               f"справочник городов не размножает строки, потому что city_id уникален.")
    report.log("   Сумма amount не изменилась: JOIN с городами только добавляет столбцы, но не фильтрует строки.")

    # --- 4. Контрольный FULL OUTER JOIN ----------------------------------
    outer = merge_orgs_transactions(orgs_clean, txs_clean, how="outer")
    stats_outer = join_stats(outer, len(txs_clean), txs_clean["amount"].sum())
    print_join_stats("4. Контроль: FULL OUTER JOIN (обе стороны сразу)", stats_outer)
    report.log(f"   right_only = {stats_outer['right_only']} — это и есть операции с неизвестным org_id;")
    report.log(f"   left_only = {stats_outer['left_only']} — организация без операций.")
    report.log("   Именно здесь одновременно видны обе проблемы исходных данных.")

    report.subheading("Сравнение четырёх объединений")
    no_city_rows = int(with_cities["_merge_city"].eq("left_only").sum())
    comparison = pd.DataFrame(
        [
            {
                "объединение": "INNER organizations + transactions",
                "строк": len(inner),
                "что видно": f"потеряны {len(orphan)} операции с неизвестным org_id",
            },
            {
                "объединение": "LEFT organizations + transactions",
                "строк": len(left),
                "что видно": "+1 строка организации без операций (amount = NaN)",
            },
            {
                "объединение": "+ LEFT cities",
                "строк": len(with_cities),
                "что видно": f"{no_city_rows} строки без города (city_name = NaN)",
            },
            {
                "объединение": "FULL OUTER (контроль)",
                "строк": len(outer),
                "что видно": "видны обе проблемы сразу: left_only + right_only",
            },
        ]
    )
    report.frame(comparison, index=False)

    return {"inner": inner, "left": left, "with_cities": with_cities}


# ---------------------------------------------------------------------------
# ЭТАП G. Аналитическая витрина
# ---------------------------------------------------------------------------
def _money(value: float) -> str:
    """Сумма в рублях с пробелами между тысячами: 9 319 614.06."""
    return f"{value:,.2f}".replace(",", " ")


def build_data_mart(joined: pd.DataFrame) -> pd.DataFrame:
    """Собирает витрину: одна строка = одна организация.

    База — результат LEFT JOIN, поэтому организация без операций остаётся
    в витрине с count = 0 и суммой 0 (иначе такие организации «исчезают»
    из отчёта, и это выглядит как ошибка данных).
    """
    mart = (
        joined.groupby("org_id", as_index=False, dropna=False)
        .agg(
            org_name=("org_name", "first"),
            sector=("sector", "first"),
            city_name=("city_name", "first"),
            region_name=("region_name", "first"),
            transactions_count=("transaction_id", "count"),
            total_amount=("amount", "sum"),
            avg_amount=("amount", "mean"),
            last_transaction_date=("date", "max"),
        )
    )

    mart["transactions_count"] = mart["transactions_count"].astype("int64")
    mart["total_amount"] = mart["total_amount"].fillna(0.0).round(2)
    mart["avg_amount"] = mart["avg_amount"].fillna(0.0).round(2)
    mart["city_name"] = mart["city_name"].fillna(NO_CITY_LABEL)
    mart["region_name"] = mart["region_name"].fillna(NO_CITY_LABEL)

    mart = mart[MART_COLUMNS]
    return mart.sort_values(
        ["total_amount", "org_id"], ascending=[False, True]
    ).reset_index(drop=True)


def save_data_mart(
    mart: pd.DataFrame,
    csv_path: Path = config.MART_CSV,
    parquet_path: Path = config.MART_PARQUET,
) -> tuple[Path, Path]:
    """Сохраняет витрину в CSV и Parquet и проверяет, что файлы читаются обратно."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # utf-8-sig: BOM в начале файла, чтобы Excel открывал русский текст корректно.
    # Power BI, Tableau и pandas читают такой CSV без проблем.
    mart.to_csv(csv_path, index=False, date_format="%Y-%m-%d", encoding="utf-8-sig")
    mart.to_parquet(parquet_path, index=False)

    csv_back = pd.read_csv(csv_path, encoding="utf-8-sig")
    parquet_back = pd.read_parquet(parquet_path)

    for path, restored in ((csv_path, csv_back), (parquet_path, parquet_back)):
        report.log(f"   {path.name}: {len(restored)} строк, "
                   f"{path.stat().st_size / 1024:.1f} КБ, столбцов {restored.shape[1]}")

    if len(csv_back) != len(mart) or len(parquet_back) != len(mart):
        raise RuntimeError("Файлы витрины прочитались с другим числом строк")

    return csv_path, parquet_path


def stage_g(
    joined_with_cities: pd.DataFrame,
    txs: pd.DataFrame,
    orgs: pd.DataFrame,
) -> pd.DataFrame:
    """Этап G целиком: собрать, проверить и сохранить витрину."""
    report.heading("ЭТАП G. ПОСТРОЕНИЕ АНАЛИТИЧЕСКОЙ ВИТРИНЫ")

    mart = build_data_mart(joined_with_cities)

    report.log(f"   Витрина: {len(mart)} строк (по одной на организацию), "
               f"{mart.shape[1]} столбцов.")
    report.log("   Столбцы: " + ", ".join(mart.columns))
    report.log()
    report.log("   Первые 10 строк (отсортировано по сумме операций):")
    report.frame(mart.head(10), index=False)

    # --- проверки витрины --------------------------------------------------
    report.subheading("Проверки витрины")
    report.log(f"  1. Строк в витрине: {len(mart)}; организаций в справочнике: {len(orgs)} "
               f"-> {'совпадает' if len(mart) == len(orgs) else 'НЕ СОВПАДАЕТ'}")

    no_operations = mart[mart["transactions_count"] == 0]
    report.log(f"  2. Организаций без операций в витрине: {len(no_operations)} "
               f"-> {', '.join(no_operations['org_name'].tolist()) or 'нет'}")
    report.log(f"     у таких организаций total_amount = 0, last_transaction_date пустая "
               f"(пропущено {int(no_operations['last_transaction_date'].isna().sum())})")

    no_city = mart[mart["city_name"] == NO_CITY_LABEL]
    report.log(f"  3. Организаций без города: {len(no_city)} "
               f"-> {', '.join(no_city['org_name'].tolist()) or 'нет'}")

    # --- сверка денег ------------------------------------------------------
    known = txs[txs["org_id"].isin(orgs["org_id"])]
    unknown = txs[~txs["org_id"].isin(orgs["org_id"])]
    mart_sum = float(mart["total_amount"].sum())
    known_sum = float(known["amount"].sum())
    unknown_sum = float(unknown["amount"].sum())
    total_sum = float(txs["amount"].sum())

    report.subheading("Сверка сумм (сколько денег потерялось при объединении)")
    report.log(f"  всего в transactions:             {_money(total_sum):>15}")
    report.log(f"  попало в витрину (известные org): {_money(mart_sum):>15}")
    report.log(f"  не попало (org_id {sorted(unknown['org_id'].unique().tolist())}):       "
               f"{_money(unknown_sum):>15}  ({len(unknown)} "
               f"{report.plural(len(unknown), 'операция', 'операции', 'операций')})")
    report.log(f"  проверка: витрина + неизвестные = {_money(mart_sum + unknown_sum)} "
               f"против {_money(total_sum)} -> "
               f"{'сходится' if abs(mart_sum + unknown_sum - total_sum) < 0.01 else 'НЕ СХОДИТСЯ'}")
    report.log(f"  операций в витрине: {int(mart['transactions_count'].sum())} из {len(txs)} "
               f"(разница {len(txs) - int(mart['transactions_count'].sum())} — строки без организации)")

    # --- валюты ------------------------------------------------------------
    currencies = (
        txs.groupby("currency", as_index=False)
        .agg(операций=("transaction_id", "count"), сумма=("amount", "sum"))
        .sort_values("сумма", ascending=False)
        .round(2)
    )
    report.subheading("Разрез по валютам (важно для трактовки сумм)")
    report.frame(currencies, index=False)
    report.log("  Суммы в витрине сложены номинально: рубли, доллары и евро не приводятся")
    report.log("  к одной валюте, потому что в заданной схеме витрины нет курса. Для анализа")
    report.log("  по валютам нужен отдельный разрез (таблица выше).")

    # --- сохранение --------------------------------------------------------
    report.subheading("Сохранение")
    save_data_mart(mart)

    parquet_back = pd.read_parquet(config.MART_PARQUET)
    report.log()
    report.log("  Типы столбцов в Parquet (важно для Power BI / Tableau):")
    report.log("  " + ", ".join(f"{col}={dtype}" for col, dtype in parquet_back.dtypes.items()))

    return mart


# ---------------------------------------------------------------------------
# Отдельный запуск: python -m src.transform
# ---------------------------------------------------------------------------
def main() -> None:
    """Прогоняет D, E и G на реальных данных (нужен запущенный сервер)."""
    from src import loaders

    try:
        orgs = loaders.load_organizations()
        cities = loaders.load_cities()
        txs = loaders.load_transactions_api()
    except (loaders.ApiUnavailableError, FileNotFoundError) as exc:
        report.log(f"\nОШИБКА: {exc}")
        raise SystemExit(2) from exc

    orgs_clean, txs_clean, cities_clean = stage_d(orgs, txs, cities)
    joined = stage_e(orgs_clean, txs_clean, cities_clean)
    stage_g(joined["with_cities"], txs_clean, orgs_clean)


if __name__ == "__main__":
    main()
