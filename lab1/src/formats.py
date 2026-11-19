"""Этап A лабораторной работы №1: чтение, профилирование и нормализация данных.

Модуль читает один логический набор объектов из CSV, JSON и XML,
приводит данные к единой схеме, разрешает конфликты по id и сохраняет
канонический набор в трех форматах.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RESULTS_DIR = PROJECT_ROOT / "results"

CANONICAL_COLUMNS = ["id", "name", "category", "value", "updated_at", "active"]
SOURCE_PRIORITY = {"csv": 1, "xml": 2, "json": 3}


# ---------- Чтение исходных форматов ----------

def read_csv_items(path: Path) -> pd.DataFrame:
    """Прочитать CSV через pandas.

    В учебном CSV встречается десятичная запятая внутри кавычек, поэтому
    сначала читаем значения как строки/объекты, а типизацию делаем централизованно
    в normalize_items().
    """
    return pd.read_csv(path)


def read_json_items(path: Path) -> pd.DataFrame:
    """Прочитать JSON через стандартный модуль json и Python-структуры."""
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, dict) and "items" in payload:
        records = payload["items"]
    elif isinstance(payload, list):
        records = payload
    else:
        raise ValueError("JSON должен содержать список объектов или ключ 'items'.")

    if not isinstance(records, list):
        raise ValueError("Поле 'items' в JSON должно быть списком.")

    return pd.DataFrame(records)


def read_xml_items(path: Path) -> pd.DataFrame:
    """Прочитать XML через xml.etree.ElementTree."""
    tree = ET.parse(path)
    root = tree.getroot()

    records: list[dict[str, Any]] = []
    for item in root.findall("item"):
        record = {child.tag: child.text for child in item}
        records.append(record)

    return pd.DataFrame(records)


# ---------- Профилирование ----------

def profile_dataframe(df: pd.DataFrame, source_name: str) -> dict[str, Any]:
    """Вернуть показатели качества, требуемые заданием."""
    duplicate_ids = 0
    if "id" in df.columns:
        duplicate_ids = int(df["id"].duplicated(keep=False).sum())

    return {
        "source": source_name,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "dtypes": {column: str(dtype) for column, dtype in df.dtypes.items()},
        "missing": {column: int(count) for column, count in df.isna().sum().items()},
        "duplicate_id_rows": duplicate_ids,
    }


def print_profile(profile: dict[str, Any]) -> None:
    print(f"\n=== {profile['source'].upper()} ===")
    print(f"Количество записей: {profile['rows']}")
    print(f"Столбцы: {profile['columns']}")
    print(f"Типы данных: {profile['dtypes']}")
    print(f"Пропуски: {profile['missing']}")
    print(f"Строки с повторяющимся id: {profile['duplicate_id_rows']}")


# ---------- Нормализация ----------

def _normalize_number(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None

    text = str(value).strip()
    if not text:
        return None

    # Поддерживаем учебный вариант "45,50" как десятичное число.
    if "," in text and "." not in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def _normalize_bool(value: Any) -> bool | pd._libs.missing.NAType:
    if value is None or value is pd.NA:
        return pd.NA
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        if value == 1:
            return True
        if value == 0:
            return False

    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "да"}:
        return True
    if text in {"false", "0", "no", "n", "нет"}:
        return False
    return pd.NA


def _parse_datetime(value: Any) -> pd.Timestamp | pd.NaT:
    if value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value)):
        return pd.NaT

    text = str(value).strip()
    if not text:
        return pd.NaT

    formats = (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y/%m/%d",
    )
    for fmt in formats:
        try:
            return pd.Timestamp(datetime.strptime(text, fmt))
        except ValueError:
            continue

    # Последняя попытка для корректной, но не перечисленной выше даты.
    try:
        return pd.to_datetime(text, errors="raise")
    except (ValueError, TypeError):
        return pd.NaT


def normalize_items(df: pd.DataFrame) -> pd.DataFrame:
    """Привести DataFrame к единой схеме лабораторной работы.

    - гарантирует наличие канонических столбцов;
    - приводит id, value, updated_at и active к заданным типам;
    - очищает name/category и унифицирует category;
    - удаляет полные дубликаты.
    """
    normalized = df.copy()
    normalized.columns = [str(column).strip().lower() for column in normalized.columns]

    for column in CANONICAL_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA

    normalized = normalized[CANONICAL_COLUMNS]

    normalized["id"] = pd.to_numeric(normalized["id"], errors="coerce").astype("Int64")
    normalized["value"] = normalized["value"].map(_normalize_number).astype("Float64")
    normalized["updated_at"] = normalized["updated_at"].map(_parse_datetime)
    normalized["active"] = normalized["active"].map(_normalize_bool).astype("boolean")

    normalized["name"] = normalized["name"].astype("string").str.strip()
    normalized["name"] = normalized["name"].replace("", pd.NA)

    normalized["category"] = normalized["category"].astype("string").str.strip().str.lower()
    normalized["category"] = normalized["category"].replace("", pd.NA)

    normalized = normalized.drop_duplicates().reset_index(drop=True)
    return normalized


# ---------- Объединение и разрешение конфликтов ----------

def combine_sources(source_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Нормализовать источники и объединить их в общий DataFrame."""
    frames: list[pd.DataFrame] = []
    for source_name, frame in source_frames.items():
        normalized = normalize_items(frame)
        normalized["_source"] = source_name
        frames.append(normalized)

    if not frames:
        return pd.DataFrame(columns=CANONICAL_COLUMNS + ["_source"])

    return pd.concat(frames, ignore_index=True)


def build_conflict_report(combined: pd.DataFrame) -> pd.DataFrame:
    """Вернуть все строки для id, встречающихся более одного раза."""
    if combined.empty:
        return combined.copy()

    duplicated_mask = combined["id"].notna() & combined["id"].duplicated(keep=False)
    report = combined.loc[duplicated_mask].copy()
    return report.sort_values(["id", "updated_at", "_source"], na_position="last")


def resolve_id_conflicts(combined: pd.DataFrame) -> pd.DataFrame:
    """Разрешить повторяющиеся id по детерминированному правилу.

    Правило:
    1. Для одинакового id выбирается запись с самым новым updated_at.
    2. При одинаковой дате используется приоритет JSON > XML > CSV.
    3. Строки без id сохраняются отдельно, т.к. их нельзя корректно объединить по ключу.
    """
    if combined.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    work = combined.copy()
    work["_source_priority"] = work["_source"].map(SOURCE_PRIORITY).fillna(0)  # Добавляем приоритет источника

    with_id = work[work["id"].notna()].copy()
    without_id = work[work["id"].isna()].copy()

    with_id = with_id.sort_values(
        by=["id", "updated_at", "_source_priority"],
        ascending=[True, False, False],
        na_position="last",
    )
    with_id = with_id.drop_duplicates(subset=["id"], keep="first")

    resolved = pd.concat([with_id, without_id], ignore_index=True)
    resolved = resolved.sort_values("id", na_position="last").reset_index(drop=True)
    return resolved[CANONICAL_COLUMNS]


# ---------- Сохранение ----------

def _python_value(value: Any) -> Any:
    """ Cпециальные типы pandas в обычные типы Python"""
    if value is pd.NA or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Превращает весь DataFrame в список обычных Python-словарей"""
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        records.append({column: _python_value(row[column]) for column in df.columns})
    return records


def save_as_xml(df: pd.DataFrame, path: Path) -> None:
    root = ET.Element("items")
    for record in dataframe_to_records(df):
        item_element = ET.SubElement(root, "item")
        for key in CANONICAL_COLUMNS:
            child = ET.SubElement(item_element, key)
            value = record.get(key)
            if value is None:
                child.text = ""
            elif isinstance(value, bool):
                child.text = "true" if value else "false"
            else:
                child.text = str(value)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def save_processed(df: pd.DataFrame) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = PROCESSED_DIR / "items_normalized.csv"
    json_path = PROCESSED_DIR / "items_normalized.json"
    xml_path = PROCESSED_DIR / "items_normalized.xml"

    # Для CSV используем единый ISO-формат даты.
    csv_df = df.copy()
    csv_df["updated_at"] = csv_df["updated_at"].map(
        lambda value: value.isoformat() if pd.notna(value) else ""
    )
    csv_df.to_csv(csv_path, index=False, encoding="utf-8")

    with json_path.open("w", encoding="utf-8") as file:
        json.dump({"items": dataframe_to_records(df)}, file, ensure_ascii=False, indent=2)

    save_as_xml(df, xml_path)


# ---------- Сквозной запуск этапа A ----------

def run_stage_a() -> pd.DataFrame:
    csv_df = read_csv_items(RAW_DIR / "items.csv")
    json_df = read_json_items(RAW_DIR / "items.json")
    xml_df = read_xml_items(RAW_DIR / "items.xml")

    source_frames = {"csv": csv_df, "json": json_df, "xml": xml_df}

    print("ПРОФИЛИРОВАНИЕ ИСХОДНЫХ ДАННЫХ")
    for source_name, frame in source_frames.items():
        print_profile(profile_dataframe(frame, source_name))

    combined = combine_sources(source_frames)
    conflicts = build_conflict_report(combined)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    conflicts.to_csv(RESULTS_DIR / "id_conflicts.csv", index=False, encoding="utf-8")

    normalized = resolve_id_conflicts(combined)
    save_processed(normalized)

    print("\n=== РЕЗУЛЬТАТ НОРМАЛИЗАЦИИ ===")
    print(normalized.to_string(index=False))
    print(f"\nУникальность id: {normalized['id'].dropna().is_unique}")
    print(f"Сохранено записей: {len(normalized)}")
    print(f"Конфликты до разрешения: {len(conflicts)} строк")
    print("Правило конфликта: новый updated_at; при равенстве JSON > XML > CSV.")

    return normalized


if __name__ == "__main__":
    run_stage_a()
