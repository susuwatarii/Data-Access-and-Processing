"""Этап D: получение данных с динамической страницы через Selenium."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from typing import Any

import pandas as pd

from src.formats import RESULTS_DIR, normalize_items


DYNAMIC_URL = "http://127.0.0.1:8000/dynamic"
FULL_OUTPUT = RESULTS_DIR / "selenium_all_items.csv"
FILTERED_OUTPUT = RESULTS_DIR / "selenium_items.csv"
METRICS_OUTPUT = RESULTS_DIR / "selenium_metrics.json"


def _table_to_dataframe(driver: Any) -> pd.DataFrame:
    # Импорты оставлены внутри функции: этапы A/B можно запускать даже до
    # установки Selenium.
    from selenium.webdriver.common.by import By

    headers = [element.text.strip() for element in driver.find_elements(By.CSS_SELECTOR, "#items-table thead th")]
    rows: list[list[str]] = []
    for row in driver.find_elements(By.CSS_SELECTOR, "#items-body tr"):
        cells = [cell.text.strip() for cell in row.find_elements(By.TAG_NAME, "td")]
        rows.append(cells)
    return pd.DataFrame(rows, columns=headers)


def _detect_browser_binary(explicit_binary: str | None = None) -> str | None:
    """Найти Chrome/Chromium без жёстко заданного пути.

    Приоритет: аргумент -> CHROME_BIN -> распространённые имена исполняемых файлов.
    Если ничего не найдено, Selenium сам попытается определить браузер.
    """
    if explicit_binary:
        return explicit_binary

    env_binary = os.environ.get("CHROME_BIN")
    if env_binary:
        return env_binary

    for executable in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(executable)
        if found:
            return found
    return None


def run_selenium(
    *,
    headless: bool = True,
    filter_category: str = "electronics",
    browser_binary: str | None = None,
    driver_path: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait

    options = webdriver.ChromeOptions()  # driver в Selenium - это объект, через который Python управляет браузером
    detected_binary = _detect_browser_binary(browser_binary)
    if detected_binary:
        options.binary_location = detected_binary

    if headless:  # запускать ли браузер в фоновом режиме
        options.add_argument("--headless=new")  # запуск без окна браузера
    options.add_argument("--no-sandbox")  # отключает песочницу Chrome ради совместимости запуска
    options.add_argument("--disable-dev-shm-usage")  # уменьшает использование общей памяти
    options.add_argument("--window-size=1400,1000")  # задаёт размер окна браузера

    started = time.perf_counter()
    if driver_path:  # Если путь к драйверу передали вручную
        driver = webdriver.Chrome(service=Service(executable_path=driver_path), options=options)
    else:
        driver = webdriver.Chrome(options=options)

    try:
        wait = WebDriverWait(driver, 10)
        driver.get(DYNAMIC_URL)

        load_button = wait.until(EC.element_to_be_clickable((By.ID, "load-btn")))
        load_button.click()

        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#items-body tr")) > 0)
        full_df = normalize_items(_table_to_dataframe(driver))

        category_select = wait.until(EC.element_to_be_clickable((By.ID, "category-filter")))
        select = Select(category_select)
        available_values = [option.get_attribute("value") for option in select.options]
        if filter_category not in available_values:
            raise ValueError(
                f"Категория {filter_category!r} отсутствует. Доступно: {available_values}"
            )

        select.select_by_value(filter_category)
        wait.until(
            lambda d: (
                len(d.find_elements(By.CSS_SELECTOR, "#items-body tr")) > 0
                and all(
                    cell.text.strip().lower() == filter_category.lower()
                    for cell in d.find_elements(By.CSS_SELECTOR, "#items-body tr td:nth-child(3)")
                )
            )
        )
        filtered_df = normalize_items(_table_to_dataframe(driver))

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        full_df.to_csv(FULL_OUTPUT, index=False, encoding="utf-8")
        filtered_df.to_csv(FILTERED_OUTPUT, index=False, encoding="utf-8")

        elapsed = time.perf_counter() - started
        metrics = {
            "elapsed_seconds": round(elapsed, 6),
            "full_rows": int(len(full_df)),
            "filtered_rows": int(len(filtered_df)),
            "filter_category": filter_category,
            "browser_binary": detected_binary,
            "driver_path": driver_path,
            "headless": headless,
        }
        with METRICS_OUTPUT.open("w", encoding="utf-8") as file:
            json.dump(metrics, file, ensure_ascii=False, indent=2)  # записывает Python-объект прямо в JSON-файл

        return full_df, filtered_df, elapsed
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="Показать окно браузера")
    parser.add_argument("--category", default="electronics", help="Категория для демонстрации фильтра")
    parser.add_argument(
        "--browser-binary",
        default=None,
        help="Путь к Chrome/Chromium, если автоопределение не сработало",
    )
    parser.add_argument(
        "--driver-path",
        default=None,
        help="Путь к ChromeDriver, если Selenium Manager недоступен",
    )
    args = parser.parse_args()

    full_df, filtered_df, elapsed = run_selenium(
        headless=not args.headed,
        filter_category=args.category,
        browser_binary=args.browser_binary,
        driver_path=args.driver_path,
    )

    print(f"Все строки: {len(full_df)} -> {FULL_OUTPUT}")
    print(f"После фильтра: {len(filtered_df)} -> {FILTERED_OUTPUT}")
    print(f"Время Selenium: {elapsed:.4f} с")


if __name__ == "__main__":
    main()
