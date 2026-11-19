"""Этап E: сводное сравнение способов получения данных."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

from src.formats import (
    CANONICAL_COLUMNS,
    PROCESSED_DIR,
    RAW_DIR,
    RESULTS_DIR,
    combine_sources,
    normalize_items,
    read_csv_items,
    read_json_items,
    read_xml_items,
    resolve_id_conflicts,
)


BASE_URL = "http://127.0.0.1:8000"
SUMMARY_PATH = RESULTS_DIR / "comparison.csv"
CONSISTENCY_PATH = RESULTS_DIR / "consistency_check.csv"
SELENIUM_METRICS_PATH = RESULTS_DIR / "selenium_metrics.json"


def _timed(loader: Callable[[], pd.DataFrame]) -> tuple[pd.DataFrame, float, str]:
    """Берёт функцию, которая получает данные.
        1. запускает таймер;
        2. получает данные;
        3. нормализует их;
        4. считает время;"""
    started = time.perf_counter()
    try:
        frame = loader()
        return normalize_items(frame), time.perf_counter() - started, ""
    except Exception as exc:
        return (
            pd.DataFrame(columns=CANONICAL_COLUMNS),
            time.perf_counter() - started,
            f"{type(exc).__name__}: {exc}",
        )


def _load_files_pipeline() -> pd.DataFrame:
    frames = {
        "csv": read_csv_items(RAW_DIR / "items.csv"),
        "json": read_json_items(RAW_DIR / "items.json"),
        "xml": read_xml_items(RAW_DIR / "items.xml"),
    }
    return resolve_id_conflicts(combine_sources(frames))


def _load_api() -> pd.DataFrame:
    response = requests.get(f"{BASE_URL}/api/items", timeout=10)
    response.raise_for_status()
    return pd.DataFrame(response.json())


def _load_selenium_result() -> pd.DataFrame:
    path = RESULTS_DIR / "selenium_all_items.csv"
    if not path.exists():
        raise FileNotFoundError("Сначала запустите python -m src.selenium_client")
    return pd.read_csv(path)


def _selenium_elapsed() -> float | None:
    """Берёт из selenium_metrics.json время,
    которое реально занял запуск Selenium.
    Простое чтение selenium_all_items.csv заняло бы доли секунды
    и не отражало бы реальную скорость Selenium."""
    if not SELENIUM_METRICS_PATH.exists():
        return None
    try:
        with SELENIUM_METRICS_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return float(payload["elapsed_seconds"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _canonical_for_compare(df: pd.DataFrame) -> pd.DataFrame:
    """Подготавливает таблицу именно для сравнения."""
    frame = normalize_items(df).copy()
    frame = frame.sort_values("id", na_position="last").reset_index(drop=True)
    frame["updated_at"] = frame["updated_at"].astype("string")
    return frame


def run_comparison() -> tuple[pd.DataFrame, pd.DataFrame]:
    loaders: dict[str, Callable[[], pd.DataFrame]] = {
        "CSV/XML/JSON": _load_files_pipeline,
        "REST API": _load_api,
        "Selenium": _load_selenium_result,
    }

    summaries = []
    loaded: dict[str, pd.DataFrame] = {}

    for name, loader in loaders.items():
        frame, elapsed, error = _timed(loader)
        loaded[name] = frame

        time_source = "measured during comparison"
        if name == "Selenium" and not error:
            recorded_elapsed = _selenium_elapsed()
            if recorded_elapsed is not None:
                elapsed = recorded_elapsed
                time_source = "recorded during browser run"

        summaries.append(
            {
                "method": name,
                "rows": len(frame),
                "unique_ids": int(frame["id"].nunique(dropna=True)) if "id" in frame else 0,
                "time_seconds": round(elapsed, 6),
                "time_source": time_source,
                "has_errors": bool(error),
                "error": error,
            }
        )

    summary_df = pd.DataFrame(summaries)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(SUMMARY_PATH, index=False, encoding="utf-8")

    reference = normalize_items(pd.read_csv(PROCESSED_DIR / "items_normalized.csv"))
    reference_cmp = _canonical_for_compare(reference)

    checks = []
    for name, frame in loaded.items():
        candidate = _canonical_for_compare(frame)

        exact_match = candidate.equals(reference_cmp)
        checks.append(
            {
                "method": name,
                "exact_match_with_canonical": exact_match,
                "note": (
                    "Канонический полный набор"
                    if exact_match
                    else "Источник требует объединения/разрешения конфликтов или содержит ошибку"
                ),
            }
        )

    consistency_df = pd.DataFrame(checks)
    consistency_df.to_csv(CONSISTENCY_PATH, index=False, encoding="utf-8")

    print("\nСводная таблица:")
    print(summary_df.to_string(index=False))
    print("\nПроверка против канонического набора:")
    print(consistency_df.to_string(index=False))

    return summary_df, consistency_df


if __name__ == "__main__":
    run_comparison()
