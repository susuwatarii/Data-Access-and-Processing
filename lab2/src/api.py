"""REST API на FastAPI — третий источник данных (операции).

Запуск:
    python lab_2.py server
    uvicorn src.api:app --host 127.0.0.1 --port 8000 --reload

Что реализовано по заданию:
    GET    /api/transactions              — список (с фильтрами и пагинацией)
    GET    /api/transactions/{id}         — одна операция
    POST   /api/transactions              — создать (201)
    PUT    /api/transactions/{id}         — заменить целиком
    PATCH  /api/transactions/{id}         — изменить часть полей
    DELETE /api/transactions/{id}         — удалить (204)
    GET    /api/v1/transactions           — 307-редирект на актуальный путь
                                            (нужен для демонстрации curl -L)
    GET    /api/health                    — проверка, что сервер жив

Данные лежат в JSON-файле (data/raw/transactions.json). Это именно источник
данных, а не аналитическое хранилище: дубликаты строк и «чужие» org_id
сохраняются как есть, потому что их поиск — часть этапов C и D.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from src import config


# ---------------------------------------------------------------------------
# Модели запросов (что клиент присылает в теле запроса)
# ---------------------------------------------------------------------------
class TransactionIn(BaseModel):
    """Полное представление операции — для POST и PUT."""

    org_id: int = Field(..., description="Идентификатор организации")
    date: dt.date = Field(..., description="Дата операции, формат YYYY-MM-DD")
    amount: float = Field(..., gt=0, description="Сумма, больше нуля")
    currency: str = Field(..., min_length=3, max_length=3, description="Код валюты, например RUB")

    def to_row(self) -> dict[str, Any]:
        """Превращает модель в словарь для хранения (дата — строкой ISO)."""
        return {
            "org_id": self.org_id,
            "date": self.date.isoformat(),
            "amount": round(float(self.amount), 2),
            "currency": self.currency.upper(),
        }


class TransactionPatch(BaseModel):
    """Частичное изменение — для PATCH. Все поля необязательные."""

    org_id: int | None = None
    date: dt.date | None = None
    amount: float | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


# ---------------------------------------------------------------------------
# Хранилище: список словарей в JSON-файле
# ---------------------------------------------------------------------------
class JsonTransactionStore:
    """Простое файловое хранилище операций.

    Читает JSON при старте, при каждом изменении перезаписывает файл целиком.
    Для учебного API этого достаточно; блокировка нужна, потому что FastAPI
    может обрабатывать запросы в разных потоках.
    """

    def __init__(self, path: Path = config.TRANSACTIONS_JSON) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._rows: list[dict[str, Any]] = []
        self.reload()

    # --- чтение ------------------------------------------------------------
    def reload(self) -> None:
        if not self.path.exists():
            raise RuntimeError(
                f"Не найден файл данных {self.path}.\n"
                f"Сначала создайте исходные данные: python lab_2.py init"
            )
        with self.path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(f"Ожидался JSON-массив операций в {self.path}")
        self._rows = data

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def get(self, transaction_id: int) -> dict[str, Any] | None:
        # transaction_id не гарантированно уникален (в данных есть дубль),
        # поэтому возвращаем первую найденную запись.
        for row in self._rows:
            if row["transaction_id"] == transaction_id:
                return dict(row)
        return None

    def count(self) -> int:
        return len(self._rows)

    # --- изменение ---------------------------------------------------------
    def add(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            row = {"transaction_id": self._next_id(), **payload}
            self._rows.append(row)
            self._save()
            return dict(row)

    def replace(self, transaction_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            for index, row in enumerate(self._rows):
                if row["transaction_id"] == transaction_id:
                    new_row = {"transaction_id": transaction_id, **payload}
                    self._rows[index] = new_row
                    self._save()
                    return dict(new_row)
        return None

    def patch(self, transaction_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            for index, row in enumerate(self._rows):
                if row["transaction_id"] == transaction_id:
                    new_row = {**row, **changes, "transaction_id": transaction_id}
                    self._rows[index] = new_row
                    self._save()
                    return dict(new_row)
        return None

    def delete(self, transaction_id: int) -> bool:
        with self._lock:
            for index, row in enumerate(self._rows):
                if row["transaction_id"] == transaction_id:
                    del self._rows[index]
                    self._save()
                    return True
        return False

    # --- внутреннее --------------------------------------------------------
    def _next_id(self) -> int:
        if not self._rows:
            return 1
        return max(int(row["transaction_id"]) for row in self._rows) + 1

    def _save(self) -> None:
        """Атомарная запись: сначала во временный файл, потом подмена."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)


# ---------------------------------------------------------------------------
# Приложение
# ---------------------------------------------------------------------------
def create_app(store_path: Path = config.TRANSACTIONS_JSON) -> FastAPI:
    """Фабрика приложения: удобно и для uvicorn, и для тестов."""
    store = JsonTransactionStore(store_path)

    app = FastAPI(
        title="Лабораторная работа II — учебный REST API операций",
        version="1.0",
        description="Источник данных №3 для аналитической витрины.",
    )

    # --- служебные ---------------------------------------------------------
    @app.get("/", tags=["service"], summary="Краткая справка по API")
    def root() -> dict[str, Any]:
        return {
            "service": "lab2-transactions-api",
            "transactions": store.count(),
            "endpoints": [
                "GET    /api/transactions",
                "GET    /api/transactions/{transaction_id}",
                "POST   /api/transactions",
                "PUT    /api/transactions/{transaction_id}",
                "PATCH  /api/transactions/{transaction_id}",
                "DELETE /api/transactions/{transaction_id}",
                "GET    /api/v1/transactions  -> 307 redirect",
                "GET    /docs  (Swagger UI)",
            ],
        }

    @app.get("/api/health", tags=["service"], summary="Проверка доступности")
    def health() -> dict[str, Any]:
        return {"status": "ok", "transactions": store.count()}

    # --- чтение ------------------------------------------------------------
    @app.get("/api/transactions", tags=["transactions"], summary="Список операций")
    def list_transactions(
        response: Response,
        org_id: int | None = Query(default=None, description="Фильтр по организации"),
        currency: str | None = Query(default=None, description="Фильтр по валюте, например RUB"),
        date_from: dt.date | None = Query(default=None, description="Дата с (включительно)"),
        date_to: dt.date | None = Query(default=None, description="Дата по (включительно)"),
        limit: int = Query(default=100, ge=1, le=1000, description="Сколько записей вернуть"),
        offset: int = Query(default=0, ge=0, description="Сколько записей пропустить"),
    ) -> list[dict[str, Any]]:
        rows = store.all()

        if org_id is not None:
            rows = [row for row in rows if row["org_id"] == org_id]
        if currency is not None:
            rows = [row for row in rows if row["currency"] == currency.upper()]
        if date_from is not None:
            rows = [row for row in rows if row["date"] >= date_from.isoformat()]
        if date_to is not None:
            rows = [row for row in rows if row["date"] <= date_to.isoformat()]

        response.headers["X-Total-Count"] = str(len(rows))
        return rows[offset : offset + limit]

    @app.get(
        "/api/transactions/{transaction_id}",
        tags=["transactions"],
        summary="Одна операция по идентификатору",
    )
    def get_transaction(
        transaction_id: int,
        response: Response,
        x_student: str | None = Header(default=None, description="Произвольный заголовок клиента"),
    ) -> dict[str, Any]:
        row = store.get(transaction_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Операция с transaction_id={transaction_id} не найдена",
            )
        if x_student:
            # Показываем, что собственный заголовок действительно дошёл до сервера.
            response.headers["X-Echo-Student"] = x_student
        return row

    # --- HEAD: нужен для демонстрации curl -I ------------------------------
    # FastAPI не добавляет HEAD к GET автоматически, поэтому объявляем явно.
    @app.head("/api/transactions", include_in_schema=False)
    def head_transactions(response: Response) -> Response:
        response.headers["X-Total-Count"] = str(store.count())
        return Response(status_code=status.HTTP_200_OK)

    @app.head("/api/transactions/{transaction_id}", include_in_schema=False)
    def head_transaction(transaction_id: int) -> Response:
        if store.get(transaction_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Операция с transaction_id={transaction_id} не найдена",
            )
        return Response(status_code=status.HTTP_200_OK)

    # --- изменение ---------------------------------------------------------
    @app.post(
        "/api/transactions",
        status_code=status.HTTP_201_CREATED,
        tags=["transactions"],
        summary="Создать операцию",
    )
    def create_transaction(payload: TransactionIn) -> dict[str, Any]:
        return store.add(payload.to_row())

    @app.put(
        "/api/transactions/{transaction_id}",
        tags=["transactions"],
        summary="Заменить операцию целиком",
    )
    def replace_transaction(transaction_id: int, payload: TransactionIn) -> dict[str, Any]:
        row = store.replace(transaction_id, payload.to_row())
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Операция с transaction_id={transaction_id} не найдена",
            )
        return row

    @app.patch(
        "/api/transactions/{transaction_id}",
        tags=["transactions"],
        summary="Изменить часть полей операции",
    )
    def patch_transaction(transaction_id: int, payload: TransactionPatch) -> dict[str, Any]:
        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "date" in changes:
            changes["date"] = changes["date"].isoformat()
        if "amount" in changes:
            changes["amount"] = round(float(changes["amount"]), 2)
        if "currency" in changes:
            changes["currency"] = changes["currency"].upper()

        row = store.patch(transaction_id, changes)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Операция с transaction_id={transaction_id} не найдена",
            )
        return row

    @app.delete(
        "/api/transactions/{transaction_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["transactions"],
        summary="Удалить операцию",
    )
    def delete_transaction(transaction_id: int) -> Response:
        if not store.delete(transaction_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Операция с transaction_id={transaction_id} не найдена",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # --- редирект для демонстрации curl -L ---------------------------------
    @app.get("/api/v1/transactions", include_in_schema=False)
    def legacy_transactions() -> RedirectResponse:
        """Старый адрес: 307 сохраняет метод и перенаправляет на новый путь."""
        return RedirectResponse(url=config.API_TRANSACTIONS_PATH, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return app


# uvicorn ищет именно эту переменную: uvicorn src.api:app
app = create_app()
