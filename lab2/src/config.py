"""Пути к файлам и общие настройки проекта.

Здесь нет никакой логики — только константы, чтобы остальные модули
не хардкодили пути к данным и результатам.
"""

from __future__ import annotations

from pathlib import Path

# Корень проекта = папка, в которой лежит lab_2.py (на уровень выше src/)
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_RAW = BASE_DIR / "data" / "raw"
DATA_PROCESSED = BASE_DIR / "data" / "processed"
RESULTS = BASE_DIR / "results"

# --- Исходные данные (создаются командой: python lab_2.py init) ------------
ORGANIZATIONS_CSV = DATA_RAW / "organizations.csv"  # источник №1: файл CSV
REGIONS_DB = DATA_RAW / "regions.db"                # источник №2: SQLite, таблица cities
TRANSACTIONS_JSON = DATA_RAW / "transactions.json"  # источник №3: "хранилище" REST API

# --- Результаты -----------------------------------------------------------
ANALYTICS_DB = DATA_PROCESSED / "lab2_analytics.db"  # БД, в которую грузим таблицы для SQL JOIN
MART_CSV = DATA_PROCESSED / "data_mart.csv"           # итоговая витрина в CSV
MART_PARQUET = DATA_PROCESSED / "data_mart.parquet"   # она же в Parquet

DASHBOARD_PNG = RESULTS / "dashboard.png"
CHART_REGIONS_PNG = RESULTS / "chart_regions.png"
CHART_ORGS_PNG = RESULTS / "chart_top_orgs.png"
CURL_REPORT = RESULTS / "curl_commands.txt"
PROTOCOL_REPORT = RESULTS / "protocol_comparison.md"
PIPELINE_REPORT = RESULTS / "pipeline_report.txt"

# --- Настройки учебного API ----------------------------------------------
API_HOST = "127.0.0.1"
API_PORT = 8000
API_URL = f"http://{API_HOST}:{API_PORT}"
API_TRANSACTIONS_PATH = "/api/transactions"


def ensure_dirs() -> None:
    """Создаёт папки data/raw, data/processed и results, если их ещё нет."""
    for path in (DATA_RAW, DATA_PROCESSED, RESULTS):
        path.mkdir(parents=True, exist_ok=True)
