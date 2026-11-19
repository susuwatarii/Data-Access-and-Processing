"""Этапы B/C: REST API через Requests и обработка сетевых ошибок."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests
from requests import Response
from requests.exceptions import ConnectionError, HTTPError, RequestException, Timeout

from src.formats import RESULTS_DIR


BASE_URL = "http://127.0.0.1:8000"
API_LOG_PATH = RESULTS_DIR / "api_log.csv"

LOG_COLUMNS = [
    "http_method",
    "url",
    "request_data",
    "status_code",
    "content_type",
    "elapsed_seconds",
    "response",
    "error_type",
]


def _safe_response_body(response: Response) -> Any:
    """ Достаёт тело ответа сервера"""
    if not response.content:
        return None
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type.lower():
        try:
            return response.json()
        except ValueError:
            return response.text
    return response.text


def _serialize(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, default=str)
    # превращает словарь/список и другие данные в строку
    # удобно для хранения внутри api_log.csv


def _append_log(row: dict[str, Any]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([row], columns=LOG_COLUMNS)
    frame.to_csv(
        API_LOG_PATH,
        mode="a",  # Режим добавления в конец файла. То есть старые строки не стираются.
        header=not API_LOG_PATH.exists(),
        index=False,
        encoding="utf-8",
    )


def _execute(
    method: str,
    url: str,
    request_data: Any,
    sender: Callable[[], Response],  # функция, которая реально выполнит запрос
    *,  # все параметры после * можно передавать только по имени, например expected_statuses={404}
    expected_statuses: set[int] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    response: Response | None = None
    error_type = ""
    """Выполняет любой HTTP-запрос, ловит ошибки, считает время и записывает всё в лог"""
    try:
        response = sender()
        # Успешность HTTP проверяется отдельно от возможности разобрать JSON.
        response.raise_for_status()
    except HTTPError as exc:
        error_type = type(exc).__name__
        if expected_statuses is None or response is None or response.status_code not in expected_statuses:
            pass
    except (ConnectionError, Timeout) as exc:
        error_type = type(exc).__name__
    except RequestException as exc:
        error_type = type(exc).__name__

    elapsed = time.perf_counter() - started

    status_code = response.status_code if response is not None else None
    content_type = response.headers.get("Content-Type", "") if response is not None else ""
    body = _safe_response_body(response) if response is not None else None

    row = {
        "http_method": method,
        "url": url,
        "request_data": _serialize(request_data),
        "status_code": status_code,
        "content_type": content_type,
        "elapsed_seconds": round(elapsed, 6),
        "response": _serialize(body),
        "error_type": error_type,
    }
    _append_log(row)
    return row


def get(path: str, *, params: dict[str, Any] | None = None, timeout: float = 10.0,
        expected_statuses: set[int] | None = None) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    return _execute(
        "GET",
        url,
        params,
        # Требуемый в задании шаблон: params + timeout + raise_for_status().
        lambda: requests.get(url, params=params, timeout=timeout),
        expected_statuses=expected_statuses,
    )


def post(path: str, payload: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    return _execute("POST", url, payload, lambda: requests.post(url, json=payload, timeout=timeout))


def put(path: str, payload: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    return _execute("PUT", url, payload, lambda: requests.put(url, json=payload, timeout=timeout))


def patch(path: str, payload: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    return _execute("PATCH", url, payload, lambda: requests.patch(url, json=payload, timeout=timeout))


def delete(path: str, timeout: float = 10.0) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    return _execute("DELETE", url, None, lambda: requests.delete(url, timeout=timeout))


def reset_log() -> None:
    """Удаляет старый файл лога перед новым запуском"""
    if API_LOG_PATH.exists():
        API_LOG_PATH.unlink()


def run_crud_demo() -> None:
    temporary_id = 10001

    new_item = {
        "id": temporary_id,
        "name": "Temporary item",
        "category": "test",
        "value": 10.0,
        "updated_at": "2026-09-23T12:00:00",
        "active": True,
    }
    post("/api/items", new_item)

    replaced_item = {
        "id": temporary_id,
        "name": "Temporary item replaced",
        "category": "test",
        "value": 20.0,
        "updated_at": "2026-09-23T12:30:00",
        "active": False,
    }
    put(f"/api/items/{temporary_id}", replaced_item)

    patch(f"/api/items/{temporary_id}", {"active": True})
    get(f"/api/items/{temporary_id}")
    delete(f"/api/items/{temporary_id}")
    get(f"/api/items/{temporary_id}", expected_statuses={404})


def run_error_demo() -> None:
    # 1) Несуществующий id -> HTTP 404.
    get("/api/items/999999", expected_statuses={404})

    # 2) Ошибка соединения: отдельный заведомо неиспользуемый локальный порт.
    url = "http://127.0.0.1:65534/api/items"
    _execute("GET", url, None, lambda: requests.get(url, timeout=1.0))

    # 3) Timeout: backend специально умеет отвечать с контролируемой задержкой.
    get("/api/delay", params={"seconds": 1.0}, timeout=0.05)


def run_stage_b_c() -> None:
    reset_log()

    print("Проверка GET списка...")
    get("/api/items", params=None, timeout=10)

    print("CRUD: POST -> PUT -> PATCH -> GET -> DELETE -> GET(404)...")
    run_crud_demo()

    print("Три сценария ошибок...")
    run_error_demo()

    print(f"Лог сохранён: {API_LOG_PATH}")


if __name__ == "__main__":
    run_stage_b_c()
