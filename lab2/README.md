# Лабораторная работа II — curl, SQL JOIN и объединение данных из нескольких источников

Проект собирает данные из трёх разных источников, проверяет ключи, объединяет их
средствами pandas и SQL, сравнивает результаты и строит аналитическую витрину
с графиками.

| Источник | Как получаем | Что внутри |
|---|---|---|
| `data/raw/organizations.csv` | файл, `pandas.read_csv` | организации: `org_id`, `org_name`, `city_id`, `sector` |
| `data/raw/regions.db` | SQLite, `pandas.read_sql_query` | таблица `cities`: `city_id`, `city_name`, `region_name`, `population` |
| `data/raw/transactions.json` | REST API (FastAPI + uvicorn), `requests.get` | операции: `transaction_id`, `org_id`, `date`, `amount`, `currency` |

## Требования

- Python 3.10+ (проверено на 3.13).
- `curl` в PATH (в Windows 10/11 уже есть). В PowerShell слово `curl` — алиас
  `Invoke-WebRequest`, поэтому в командах ниже используется `curl.exe`.
- Свободный порт 8000 (или запуск с другим портом, см. «Если что-то не работает»).

## Установка

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Быстрый старт

Терминал 1 — сервер API (оставить работать):

```powershell
python lab_2.py server
```

Терминал 2 — всё остальное одной командой:

```powershell
python lab_2.py all
```

`all` создаёт исходные данные, таблицу протоколов, прогоняет этап A (curl-сценарий),
этапы C–G и строит графики. Готовые файлы появятся в `results/` и `data/processed/`
(см. таблицу ниже).

## Запуск по этапам

| Этап | Команда | Что делает | Результат |
|---|---|---|---|
| — | `python lab_2.py init` | создаёт три источника данных | `data/raw/*` |
| A | `python lab_2.py curl` | 15 curl-запросов к API: версия, GET (список и один), HEAD, POST, PUT, PATCH, DELETE, `-i`, `-H`, `-d`, `-L`, `-o`, `-D`, `-w`, query-параметры | `results/curl_commands.txt` |
| B | `python lab_2.py protocols` | таблица HTTP/FTP/SMTP по фактическому `curl --version` | `results/protocol_comparison.md` |
| C–G | `python lab_2.py pipeline` | загрузка источников, проверка ключей, `pandas.merge`, SQL JOIN, витрина | `results/pipeline_report.txt`, `data/processed/*` |
| H | `python lab_2.py viz` | два графика и дашборд по витрине | `results/dashboard.png` |

Порядок важен только в одном: `pipeline` и `curl` требуют запущенного сервера,
а `viz` — уже построенной витрины.

## Отдельный запуск этапа (если просят показать кусок отдельно)

```powershell
python lab_2.py step C      # только загрузка источников
python lab_2.py step D      # только проверка ключей
python lab_2.py step E      # только объединения в pandas
python lab_2.py step F      # только SQL JOIN и сверка с pandas
python lab_2.py step G      # только витрина
```

Каждый такой запуск пишет свой отчёт `results/step_<буква>_report.txt` и не портит
общий `pipeline_report.txt`.

Любой модуль запускается и сам по себе — из корня проекта:

```powershell
python src/seed_data.py      # пересоздать исходные данные
python src/loaders.py        # этап C
python src/transform.py      # этапы D, E, G
python src/database.py       # этап F
python src/visualize.py      # этап H
python src/protocols.py      # этап B
```

То же самое можно записать через модуль: `python -m src.transform` (нужен
запуск из корня проекта). Если преподаватель просит показать отдельный кусок
кода — удобнее всего эти команды и `python lab_2.py step <буква>`.

## Где смотреть результаты

| Файл | Что внутри |
|---|---|
| `results/curl_commands.txt` | команда и ответ для каждого curl-запроса, версия и протоколы сборки |
| `results/protocol_comparison.md` | сравнительная таблица HTTP/FTP/SMTP и поддержка в вашей сборке curl |
| `results/pipeline_report.txt` | полный протокол этапов C–G: shape, dtypes, `isna`, дубликаты, статистика каждого JOIN, сверка pandas и SQL |
| `results/dashboard.png` | дашборд: сумма по регионам + ТОП-10 организаций |
| `results/chart_regions.png`, `results/chart_top_orgs.png` | те же графики по отдельности |
| `data/processed/data_mart.csv` | витрина для BI (Power BI / Tableau / Qlik) |
| `data/processed/data_mart.parquet` | та же витрина в Parquet (типы сохраняются) |
| `data/processed/lab2_analytics.db` | SQLite с таблицами `organizations`, `transactions`, `cities` для этапа F |
| `data/raw/transactions_from_api.json`, `data/raw/api_headers.txt` | что сохранили `curl -o` и `curl -D` на этапе A |

Витрина: одна строка = одна организация, столбцы
`org_id, org_name, sector, city_name, region_name, transactions_count,
total_amount, avg_amount, last_transaction_date`.

## Структура проекта

```
lab_2_project/
├── lab_2.py              точка входа: init / server / curl / protocols / pipeline / viz / all / step
├── requirements.txt
├── README.md
├── src/
│   ├── config.py         пути и настройки
│   ├── report.py         вывод в консоль и в файл отчёта
│   ├── seed_data.py      генерация исходных данных (детерминированная, seed 42)
│   ├── api.py            REST API на FastAPI: /api/transactions + POST/PUT/PATCH/DELETE
│   ├── loaders.py        этап C: три источника
│   ├── transform.py      этапы D, E, G: ключи, pandas.merge, витрина
│   ├── database.py       этап F: SQL JOIN в SQLite и сверка с pandas
│   ├── visualize.py      этап H: графики и дашборд
│   └── protocols.py      этап B: таблица протоколов
├── scripts/
│   └── curl_demo.py      этап A: прогон curl-запросов
├── data/
│   ├── raw/              исходные данные (создаются init)
│   └── processed/        витрина и БД для SQL
└── results/              отчёты, таблица протоколов, графики
```

## API: что реализовано

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/transactions` | список операций, фильтры `org_id`, `currency`, `date_from`, `date_to`, `limit`, `offset` |
| GET | `/api/transactions/{id}` | одна операция |
| POST | `/api/transactions` | создать (201) |
| PUT | `/api/transactions/{id}` | заменить целиком |
| PATCH | `/api/transactions/{id}` | изменить часть полей |
| DELETE | `/api/transactions/{id}` | удалить (204) |
| GET | `/api/v1/transactions` | 307-редирект на актуальный путь (для `curl -L`) |
| GET | `/api/health` | проверка доступности |
| GET | `/docs` | Swagger UI |

Данные API хранит в JSON-файле, поэтому изменения из POST/PUT/PATCH/DELETE
сохраняются до следующего `python lab_2.py init`.

## Данные намеренно содержат проблемы

Так требует задание: на них видно разницу между INNER и LEFT JOIN.

1. организация без операций — `org_id=14` (ООО «Томск-Прибор»);
2. операции с неизвестным `org_id` — `org_id=999`, 2 строки на 605 000 руб.;
3. города без организаций — `city_id=6` (Самара) и `city_id=12` (Сочи);
4. полностью повторяющаяся строка — дубль `transaction_id=1005`;
5. организация без города — `org_id=15` с пустым `city_id` (нужно для проверки NULL).

Что из этого следует: INNER JOIN даёт 51 строку (2 операции с `org_id=999`
теряются), LEFT JOIN — 52 строки (добавляется организация без операций), а
`FULL OUTER JOIN` — 54 строки, где видны обе проблемы сразу. Все эти числа
печатаются в `results/pipeline_report.txt` вместе со сверкой pandas и SQL.

## Если что-то не работает

- **`Не удалось получить данные от API`** — не запущен сервер. В отдельном
  терминале: `python lab_2.py server`.
- **Порт 8000 занят** — запустите на другом порту и передайте адрес:
  `python lab_2.py server --port 8010`, затем
  `python lab_2.py pipeline --api-url http://127.0.0.1:8010`.
  Для curl: `python lab_2.py curl --api-url http://127.0.0.1:8010`.
- **`curl` в PowerShell ведёт себя странно** — это алиас `Invoke-WebRequest`.
  Используйте `curl.exe` (именно так и записано в `results/curl_commands.txt`).
- **`Не установлена зависимость ...`** — `python -m pip install -r requirements.txt`.
- **Нужно начать с чистых данных** — `python lab_2.py init` перезапишет
  `organizations.csv`, `regions.db` и `transactions.json` исходным набором.
