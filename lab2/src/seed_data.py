"""Генерация исходных данных для лабораторной работы.

Три источника, как требует задание:

1. data/raw/organizations.csv      — организации (CSV);
2. data/raw/regions.db             — SQLite, таблица cities (города и регионы);
3. data/raw/transactions.json      — хранилище учебного REST API (операции).

В данные НАМЕРЕННО добавлены проблемы, чтобы разница между INNER JOIN
и LEFT JOIN была видна на числах:

* организация без операций          — org_id = 14 (ООО «Томск-Прибор»);
* операции с неизвестным org_id     — org_id = 999 (2 строки);
* город без организации             — city_id = 6 (Самара) и 12 (Сочи);
* одна повторяющаяся строка         — дубль операции transaction_id = 1005;
* (дополнительно) организация без города — org_id = 15, пустой city_id.
  Без неё нечего было бы показать в проверке на NULL (этап D).

Все данные детерминированные: random.Random(42) даёт один и тот же набор
при каждом запуске, поэтому цифры в отчёте не меняются от запуска к запуску.
"""

from __future__ import annotations

import csv
import json
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

if __package__ in (None, ""):  # запуск файлом: python src/seed_data.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, report

# --- Справочник городов (таблица cities в regions.db) ---------------------
CITIES: list[tuple[int, str, str, int]] = [
    (1, "Санкт-Петербург", "Северо-Западный", 5_601_000),
    (2, "Мурманск", "Северо-Западный", 270_000),
    (3, "Москва", "Центральный", 13_100_000),
    (4, "Тула", "Центральный", 461_000),
    (5, "Казань", "Приволжский", 1_290_000),
    (6, "Самара", "Приволжский", 1_160_000),
    (7, "Екатеринбург", "Уральский", 1_540_000),
    (8, "Челябинск", "Уральский", 1_180_000),
    (9, "Новосибирск", "Сибирский", 1_630_000),
    (10, "Красноярск", "Сибирский", 1_190_000),
    (11, "Ростов-на-Дону", "Южный", 1_140_000),
    (12, "Сочи", "Южный", 470_000),
]

# --- Организации (organizations.csv) -------------------------------------
# city_id = None означает «город не указан» (в CSV попадёт пустая строка).
ORGANIZATIONS: list[tuple[int, str, int | None, str]] = [
    (1, "ООО «Северный Ветер»", 1, "Розничная торговля"),
    (2, "АО «Балтийский Порт»", 1, "Логистика"),
    (3, "ООО «Столица-Строй»", 3, "Строительство"),
    (4, "ПАО «Тула-Металл»", 4, "Металлургия"),
    (5, "ООО «Волга-Агро»", 5, "Сельское хозяйство"),
    (6, "ООО «Урал-Маш»", 7, "Машиностроение"),
    (7, "АО «Челяб-Энерго»", 8, "Энергетика"),
    (8, "ООО «Сибирь-Логистик»", 9, "Логистика"),
    (9, "ООО «Красноярск-Лес»", 10, "Лесная промышленность"),
    (10, "ООО «Дон-Трейд»", 11, "Розничная торговля"),
    (11, "ООО «Нева-Софт»", 1, "ИТ-услуги"),
    (12, "ООО «Кама-Хим»", 5, "Химическая промышленность"),
    (13, "АО «Юг-Агро»", 11, "Сельское хозяйство"),
    (14, "ООО «Томск-Прибор»", 9, "Приборостроение"),          # без операций
    (15, "ООО «Северо-Запад-Ресурс»", None, "Добыча ресурсов"),  # без города
    (16, "ООО «Мурман-Трал»", 2, "Рыболовство"),
]

# Организации, у которых есть операции (14-я специально пропущена).
ORGS_WITH_TRANSACTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16]

UNKNOWN_ORG_ID = 999        # «чужая» операция, которой нет в organizations
DUPLICATE_TRANSACTION_ID = 1005  # эту операцию продублируем целиком


def build_transactions(seed: int = 42) -> list[dict]:
    """Собирает список операций (то, что будет отдавать REST API).

    Суммы распределены логнормально — как реальные платежи: много мелких
    и несколько крупных. Валюта в основном рублёвая, но есть валютные
    контракты (об этом будет отдельное замечание на этапе G).
    """
    rng = random.Random(seed)
    start = date(2026, 1, 1)
    rows: list[dict] = []
    transaction_id = 1001

    for org_id in ORGS_WITH_TRANSACTIONS:
        for _ in range(rng.randint(2, 5)):
            op_date = start + timedelta(days=rng.randint(0, 292))  # до 20.10.2026
            amount = round(rng.lognormvariate(11.5, 0.9), 2)
            amount = round(min(max(amount, 5_000), 4_000_000), 2)
            currency = rng.choices(["RUB", "USD", "EUR"], weights=[86, 10, 4])[0]
            rows.append(
                {
                    "transaction_id": transaction_id,
                    "org_id": org_id,
                    "date": op_date.isoformat(),
                    "amount": amount,
                    "currency": currency,
                }
            )
            transaction_id += 1

    # Проблема 1: одна и та же операция выгружена дважды (полный дубль строки).
    duplicate = next(r for r in rows if r["transaction_id"] == DUPLICATE_TRANSACTION_ID)
    rows.insert(rows.index(duplicate) + 1, dict(duplicate))

    # Проблема 2: операции с org_id, которого нет в справочнике организаций.
    rows.append(
        {
            "transaction_id": transaction_id,
            "org_id": UNKNOWN_ORG_ID,
            "date": "2026-09-15",
            "amount": 480_000.00,
            "currency": "RUB",
        }
    )
    rows.append(
        {
            "transaction_id": transaction_id + 1,
            "org_id": UNKNOWN_ORG_ID,
            "date": "2026-10-02",
            "amount": 125_000.00,
            "currency": "RUB",
        }
    )

    rows.sort(key=lambda r: (r["date"], r["transaction_id"]))
    return rows


def write_organizations_csv(path: Path = config.ORGANIZATIONS_CSV) -> Path:
    """Пишет organizations.csv. Пустой city_id остаётся пустым полем."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["org_id", "org_name", "city_id", "sector"])
        for org_id, org_name, city_id, sector in ORGANIZATIONS:
            writer.writerow([org_id, org_name, "" if city_id is None else city_id, sector])
    return path


def write_regions_db(path: Path = config.REGIONS_DB) -> Path:
    """Создаёт SQLite-базу regions.db с таблицей cities."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE cities (
                city_id     INTEGER PRIMARY KEY,
                city_name   TEXT    NOT NULL,
                region_name TEXT    NOT NULL,
                population  INTEGER
            )
            """
        )
        conn.executemany("INSERT INTO cities VALUES (?, ?, ?, ?)", CITIES)
        conn.commit()
    finally:
        conn.close()
    return path


def write_transactions_json(rows: list[dict], path: Path = config.TRANSACTIONS_JSON) -> Path:
    """Складывает операции в JSON-файл — это хранилище учебного API."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def create_sources() -> dict[str, Path]:
    """Создаёт все три источника и печатает сводку по проблемным данным."""
    config.ensure_dirs()
    rows = build_transactions()

    paths = {
        "organizations": write_organizations_csv(),
        "regions": write_regions_db(),
        "transactions": write_transactions_json(rows),
    }

    report.heading("ИСХОДНЫЕ ДАННЫЕ СОЗДАНЫ")
    report.log(f"organizations.csv : {len(ORGANIZATIONS)} организаций")
    report.log(f"regions.db        : {len(CITIES)} городов, таблица cities")
    report.log(f"transactions.json : {len(rows)} операций")

    report.subheading("Проблемные данные, добавленные намеренно")
    problems = [
        "организация без операций: org_id=14 (ООО «Томск-Прибор»)",
        f"операции с неизвестным org_id: {UNKNOWN_ORG_ID} "
        f"({sum(1 for r in rows if r['org_id'] == UNKNOWN_ORG_ID)} строки)",
        "города без организаций: city_id=6 (Самара) и 12 (Сочи)",
        f"повторяющаяся строка: полный дубль transaction_id={DUPLICATE_TRANSACTION_ID}",
        "организация без города: org_id=15, пустой city_id (нужно для проверки NULL)",
    ]
    for number, text in enumerate(problems, start=1):
        report.log(f"  {number}. {text}")

    report.log()
    for name, path in paths.items():
        report.log(f"  {name:<14} -> {path}")

    return paths


if __name__ == "__main__":
    # Можно запускать отдельно: python -m src.seed_data
    create_sources()
