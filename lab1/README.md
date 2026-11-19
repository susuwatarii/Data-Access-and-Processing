# Лабораторная работа №1 — форматы данных, REST API и динамическая страница

Проект получает один логический набор объектов из CSV, JSON, XML, REST API и динамической веб-страницы, приводит данные к общей схеме и сравнивает способы получения.

## Структура

```text
lab_1/
├── README.md
├── requirements.txt
├── backend/
│   └── app.py
├── data/
│   ├── raw/
│   │   ├── items.csv
│   │   ├── items.json
│   │   └── items.xml
│   └── processed/
│       ├── items_normalized.csv
│       ├── items_normalized.json
│       └── items_normalized.xml
├── results/
│   ├── api_log.csv
│   ├── id_conflicts.csv
│   ├── selenium_items.csv          # появится после Selenium
│   ├── selenium_all_items.csv      # полный набор для сравнения
│   ├── selenium_metrics.json       # реальное время браузерного запуска
│   ├── comparison.csv              # итоговая таблица
│   └── consistency_check.csv
└── src/
    ├── formats.py
    ├── api_client.py
    ├── selenium_client.py
    ├── compare_results.py
    └── run_all.py
 
```

## Единая схема

- `id` — integer;
- `name` — string;
- `category` — string;
- `value` — float;
- `updated_at` — datetime;
- `active` — boolean.

В исходных файлах специально присутствуют учебные проблемы: пустая категория, повторяющийся `id`, разные регистры/пробелы категорий, числа строками, десятичная запятая и несколько форматов дат.

## Правило разрешения конфликтов id

Если один `id` встречается в нескольких источниках, выбирается запись с самым новым `updated_at`. Если даты совпадают, применяется фиксированный приоритет `JSON > XML > CSV`.

Для `id=3` версии намеренно различаются по `value` и `updated_at`, поэтому правило можно реально продемонстрировать. `results/id_conflicts.csv` отдельно показывает обычные совпадения ID между источниками (`_variant_count = 1`) и реальные конфликты (`_has_conflict = True`), а `_selected` отмечает выбранную версию.

## Установка

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Установка зависимостей:

```bash
pip install -r requirements.txt
```

Для Selenium нужен установленный Chrome/Chromium. Современный Selenium обычно подбирает драйвер через Selenium Manager. Если среда запрещает загрузку драйвера, ChromeDriver надо установить отдельно и добавить в `PATH`.

## Сквозной запуск одной командой

После установки зависимостей можно выполнить всю лабораторную последовательно:

```bash
python -m src.run_all
```

Для демонстрации с видимым браузером:

```bash
python -m src.run_all --headed
```

Если на конкретной машине Selenium временно недоступен, этапы A–C и проверку остальных частей можно прогнать так:

```bash
python -m src.run_all --skip-selenium
```

Скрипт сам запускает локальный FastAPI backend на время проверки и завершает его после выполнения.

## Этап A — CSV / JSON / XML

```bash
python -m src.formats
```

Скрипт:

1. читает CSV через `pandas`;
2. разбирает JSON стандартным `json`;
3. разбирает XML через `xml.etree.ElementTree`;
4. выводит количество записей, столбцы, типы, пропуски и повторяющиеся `id`;
5. выполняет `normalize_items(df)`;
6. объединяет источники и разрешает конфликты `id`;
7. сохраняет нормализованные CSV/JSON/XML.

## Этап B/C — REST API и ошибки

Сначала запустить backend в отдельном терминале:

```bash
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Затем:

```bash
python -m src.api_client
```

Клиент выполняет:

- GET списка;
- GET с query-параметром `category` через `params`;
- POST временного объекта;
- PUT полной версии объекта;
- PATCH одного поля;
- GET изменённого объекта;
- DELETE;
- повторный GET и ожидаемый 404;
- отдельный GET несуществующего `id`;
- воспроизводимый `ConnectionError`;
- воспроизводимый `Timeout` через `/api/delay`.

Каждый запрос записывается в `results/api_log.csv`: метод, URL, параметры/тело, `status_code`, `Content-Type`, время, ответ и тип ошибки.


netstat -ano | findstr :8000

taskkill /PID 12345 /F

## Этап D — Selenium

Backend должен продолжать работать.

Headless-режим:

```bash
python -m src.selenium_client
```

С видимым окном браузера:

```bash
python -m src.selenium_client --headed
```

Другая категория:

```bash
python -m src.selenium_client --category furniture
```

Если Chrome/Chromium не определяется автоматически, путь можно указать явно:

```bash
python -m src.selenium_client --browser-binary /path/to/chrome
```

Также поддерживается переменная окружения `CHROME_BIN`. Если Selenium Manager не может получить драйвер из сети, можно передать уже установленный ChromeDriver явно:

```bash
python -m src.selenium_client --driver-path /path/to/chromedriver
```

Selenium:

1. открывает `/dynamic`;
2. ждёт кнопку через `WebDriverWait`;
3. нажимает «Загрузить данные»;
4. ждёт строки таблицы;
5. сохраняет полный набор в `results/selenium_all_items.csv`;
6. применяет фильтр категории;
7. считывает отображаемые строки;
8. сохраняет их в обязательный `results/selenium_items.csv`;
9. сохраняет фактическое время браузерного запуска в `results/selenium_metrics.json`.

`time.sleep()` для ожиданий не используется. Итоговое сравнение берёт время Selenium именно из браузерного запуска, а не измеряет чтение уже готового CSV.

## Этап E — сравнение

После запуска Selenium:

```bash
python -m src.compare_results
```

Создаются:

- `results/comparison.csv` — способ, количество записей, уникальные id, время, наличие ошибок;
- `results/consistency_check.csv` — проверка совпадения полного результата с канонической витриной.


## Финальная проверка перед сдачей

После реального запуска Selenium выполните:

```bash
python -m src.check_submission
```

Проверка контролирует наличие всех обязательных файлов, пяти HTTP-методов, трёх демонстрационных ошибок и непустого `selenium_items.csv`. До реального запуска Selenium она намеренно завершится с сообщением о недостающем файле.

Развёрнутая заготовка текста отчёта и ответов для защиты находится в `REPORT.md`.
