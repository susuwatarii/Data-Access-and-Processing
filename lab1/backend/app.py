"""Локальный учебный backend для лабораторной работы №1."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.formats import CANONICAL_COLUMNS, PROCESSED_DIR, normalize_items


app = FastAPI(title="Lab 1 Items API", version="1.0.0")
# адрес сервера задаётся при запуске FastAPI через Uvicorn (веб-сервер)
# берёт уже готовый результат предыдущего этапа data/processed/items_normalized.csv


class Item(BaseModel):
    id: int = Field(gt=0)
    name: str
    category: str | None = None # = None означает значение по умолчанию
    value: float
    updated_at: datetime
    active: bool


class ItemPatch(BaseModel):
    name: str | None = None  # =None - каждое поле в PATCH необязательное
    category: str | None = None
    value: float | None = None
    updated_at: datetime | None = None
    active: bool | None = None


def _load_initial_items() -> dict[int, dict[str, Any]]:
    path = PROCESSED_DIR / "items_normalized.csv"
    if not path.exists():
        raise RuntimeError(
            "Нет data/processed/items_normalized.csv. Сначала запустите: python -m src.formats"
        )

    df = normalize_items(pd.read_csv(path))
    records: dict[int, dict[str, Any]] = {}
    for row in df.to_dict(orient="records"):
        item_id = int(row["id"])
        updated = row["updated_at"]
        records[item_id] = {
            "id": item_id,
            "name": str(row["name"]),
            "category": None if pd.isna(row["category"]) else str(row["category"]),
            "value": float(row["value"]),
            "updated_at": updated.to_pydatetime() if isinstance(updated, pd.Timestamp) else updated,
            "active": bool(row["active"]),
        }
    return records


ITEMS = _load_initial_items()


@app.get("/api/items", response_model=list[Item])
def get_items(category: str | None = Query(default=None)) -> list[dict[str, Any]]:
    # Query(default=None) — FastAPI должен брать этот параметр из query-строки URL
    items = list(ITEMS.values())
    if category is not None:
        normalized_category = category.strip().lower()
        items = [
            item
            for item in items
            if (item.get("category") or "").strip().lower() == normalized_category
        ]
    return sorted(items, key=lambda item: item["id"])


@app.get("/api/items/{item_id}", response_model=Item)
def get_item(item_id: int) -> dict[str, Any]:
    item = ITEMS.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item


@app.post("/api/items", response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(item: Item) -> dict[str, Any]:
    if item.id in ITEMS:
        raise HTTPException(status_code=409, detail=f"Item {item.id} already exists")
    ITEMS[item.id] = item.model_dump()  # model_dump превращает объект Pydantic-модели item в обычный Python-словарь
    return ITEMS[item.id]


@app.put("/api/items/{item_id}", response_model=Item)
def replace_item(item_id: int, item: Item) -> dict[str, Any]:
    if item_id not in ITEMS:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    if item.id != item_id:
        raise HTTPException(status_code=400, detail="Path id and body id must match")
    ITEMS[item_id] = item.model_dump()
    return ITEMS[item_id]


@app.patch("/api/items/{item_id}", response_model=Item)
def patch_item(item_id: int, patch: ItemPatch) -> dict[str, Any]:
    if item_id not in ITEMS:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

    updates = patch.model_dump(exclude_unset=True)
    ITEMS[item_id].update(updates)
    return ITEMS[item_id]


@app.delete("/api/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int) -> Response:
    if item_id not in ITEMS:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    del ITEMS[item_id]
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/delay")
async def delayed_response(seconds: float = Query(default=2.0, ge=0.0, le=10.0)) -> dict[str, float]:
    """Контролируемая задержка для воспроизводимой демонстрации timeout."""
    await asyncio.sleep(seconds)
    return {"slept_seconds": seconds}


DYNAMIC_HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Lab 1 — Dynamic Items</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 1000px; margin: 40px auto; padding: 0 16px; }
    .controls { display: flex; gap: 12px; margin-bottom: 18px; align-items: center; }
    button, select { padding: 8px 12px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
    th { background: #f2f2f2; }
    #status { margin: 12px 0; }
  </style>
</head>
<body>
  <h1>Динамическая таблица объектов</h1>
  <p>Строки таблицы отсутствуют в исходном HTML и создаются JavaScript после запроса к REST API.</p>

  <div class="controls">
    <button id="load-btn" type="button">Загрузить данные</button>
    <label for="category-filter">Категория:</label>
    <select id="category-filter" disabled>
      <option value="all">Все</option>
    </select>
  </div>

  <div id="status">Данные ещё не загружены.</div>

  <table id="items-table">
    <thead>
      <tr>
        <th>id</th><th>name</th><th>category</th><th>value</th><th>updated_at</th><th>active</th>
      </tr>
    </thead>
    <tbody id="items-body"></tbody>
  </table>

<script>
  let allItems = [];
  const body = document.getElementById('items-body');
  const statusBox = document.getElementById('status');
  const filter = document.getElementById('category-filter');

  function render(items) {
    body.innerHTML = '';
    for (const item of items) {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${item.id}</td>
        <td>${item.name}</td>
        <td>${item.category ?? ''}</td>
        <td>${item.value}</td>
        <td>${item.updated_at}</td>
        <td>${item.active}</td>`;
      body.appendChild(row);
    }
    statusBox.textContent = `Показано строк: ${items.length}`;
  }

  function fillCategories(items) {
    const categories = [...new Set(items.map(x => x.category).filter(Boolean))].sort();
    filter.innerHTML = '<option value="all">Все</option>';
    for (const category of categories) {
      const option = document.createElement('option');
      option.value = category;
      option.textContent = category;
      filter.appendChild(option);
    }
    filter.disabled = false;
  }

  document.getElementById('load-btn').addEventListener('click', async () => {
    statusBox.textContent = 'Загрузка...';
    const response = await fetch('/api/items');
    if (!response.ok) {
      statusBox.textContent = `Ошибка HTTP: ${response.status}`;
      return;
    }
    allItems = await response.json();
    fillCategories(allItems);
    render(allItems);
  });

  filter.addEventListener('change', () => {
    const value = filter.value;
    const filtered = value === 'all' ? allItems : allItems.filter(x => x.category === value);
    render(filtered);
  });
</script>
</body>
</html>
"""


# Эндпоинт, который отдаёт HTML-страницу
@app.get("/dynamic", response_class=HTMLResponse)
def dynamic_page() -> str:
    return DYNAMIC_HTML
