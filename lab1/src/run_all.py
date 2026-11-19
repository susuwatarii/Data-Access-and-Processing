"""Сквозной запуск лабораторной №1.

Команда запускает этап A, временно поднимает локальный FastAPI backend,
выполняет REST CRUD и ошибки, затем Selenium и итоговое сравнение.

Использование:
    python -m src.run_all
    python -m src.run_all --headed
    python -m src.run_all --skip-selenium
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import requests

from src.api_client import run_stage_b_c
from src.compare_results import run_comparison
from src.formats import PROJECT_ROOT, run_stage_a


BASE_URL = "http://127.0.0.1:8000"


def _wait_for_backend(process: subprocess.Popen[bytes], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Backend завершился с кодом {process.returncode}")
        try:
            response = requests.get(f"{BASE_URL}/api/items", timeout=0.5)
            response.raise_for_status()
            return
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(0.15)

    raise RuntimeError(f"Backend не запустился за {timeout} с: {last_error}")


def _start_backend() -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--log-level",
        "warning",
    ]
    process = subprocess.Popen(command, cwd=PROJECT_ROOT)
    _wait_for_backend(process)
    return process


def _stop_backend(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Сквозной запуск лабораторной №1")
    parser.add_argument("--skip-selenium", action="store_true", help="Не запускать Selenium")
    parser.add_argument("--headed", action="store_true", help="Показывать окно Chromium/Chrome")
    parser.add_argument("--category", default="electronics", help="Категория для Selenium-фильтра")
    parser.add_argument(
        "--browser-binary",
        default=None,
        help="Путь к Chrome/Chromium для Selenium",
    )
    parser.add_argument(
        "--driver-path",
        default=None,
        help="Путь к ChromeDriver, если Selenium Manager недоступен",
    )
    args = parser.parse_args()

    print("\n[1/5] Этап A: форматы и нормализация")
    run_stage_a()

    backend: subprocess.Popen[bytes] | None = None
    try:
        print("\n[2/5] Запуск локального backend")
        backend = _start_backend()
        print(f"Backend доступен: {BASE_URL}")

        print("\n[3/5] Этапы B/C: REST CRUD и обработка ошибок")
        run_stage_b_c()

        if args.skip_selenium:
            print("\n[4/5] Selenium пропущен по --skip-selenium")
        else:
            print("\n[4/5] Этап D: Selenium")
            try:
                from src.selenium_client import run_selenium

                full_df, filtered_df, elapsed = run_selenium(
                    headless=not args.headed,
                    filter_category=args.category,
                    browser_binary=args.browser_binary,
                    driver_path=args.driver_path,
                )
                print(
                    f"Selenium: полный набор={len(full_df)}, после фильтра={len(filtered_df)}, "
                    f"время={elapsed:.4f} с"
                )
            except ModuleNotFoundError as exc:
                if exc.name == "selenium":
                    print(
                        "Selenium не установлен. Выполните pip install -r requirements.txt "
                        "и запустите команду ещё раз."
                    )
                else:
                    raise

        print("\n[5/5] Этап E: сравнение")
        run_comparison()
    finally:
        if backend is not None:
            _stop_backend(backend)

    print("\nГотово. Результаты находятся в каталоге results/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
