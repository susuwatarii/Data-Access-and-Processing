#!/usr/bin/env python
"""Лабораторная работа II. Точка входа для всех этапов.

    python lab_2.py init        — создать исходные данные (CSV, SQLite, JSON для API)
    python lab_2.py server      — запустить REST API (uvicorn + FastAPI)
    python lab_2.py curl        — этап A: прогнать curl-сценарий и сохранить отчёт
    python lab_2.py protocols   — этап B: таблица протоколов по факту curl --version
    python lab_2.py pipeline    — этапы C–G: загрузка, проверка ключей, merge, SQL, витрина
    python lab_2.py viz         — этап H: графики и дашборд
    python lab_2.py all         — init + protocols + curl + pipeline + viz одной командой

Отдельный этап (если преподаватель просит показать кусок отдельно):

    python lab_2.py step C
    python lab_2.py step D
    python lab_2.py step E
    python lab_2.py step F
    python lab_2.py step G

Каждый модуль запускается и сам по себе: python -m src.loaders, -m src.transform,
-m src.database, -m src.visualize, -m src.protocols, -m src.seed_data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # запуск из любой папки: python C:\\...\\lab_2.py
    sys.path.insert(0, str(ROOT))

from src import config, report, seed_data  # noqa: E402

STEPS = {
    "C": "загрузка источников: CSV, SQLite, REST API",
    "D": "очистка ключей и проверка кардинальности",
    "E": "объединение средствами pandas",
    "F": "SQL JOIN и сравнение с pandas",
    "G": "аналитическая витрина",
}


# ---------------------------------------------------------------------------
# Команды
# ---------------------------------------------------------------------------
def cmd_init(_: argparse.Namespace) -> int:
    """Создаёт три источника данных."""
    seed_data.create_sources()
    return 0


def cmd_server(args: argparse.Namespace) -> int:
    """Поднимает учебный API на uvicorn."""
    import uvicorn

    print("=" * 78)
    print("Учебный REST API (FastAPI + uvicorn)")
    print(f"  список операций : http://{config.API_HOST}:{args.port}{config.API_TRANSACTIONS_PATH}")
    print(f"  Swagger UI      : http://{config.API_HOST}:{args.port}/docs")
    print(f"  проверка        : http://{config.API_HOST}:{args.port}/api/health")
    print("Остановить: Ctrl+C")
    print("=" * 78)

    uvicorn.run(
        "src.api:app",
        host=config.API_HOST,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def cmd_curl(args: argparse.Namespace) -> int:
    """Этап A: curl-сценарий по запущенному серверу."""
    from scripts.curl_demo import main as curl_main

    return curl_main(base_url=args.api_url)


def cmd_protocols(_: argparse.Namespace) -> int:
    """Этап B: сравнительная таблица протоколов."""
    from src import protocols

    protocols.write_protocol_table()
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    """Этапы C–G (или один выбранный этап)."""
    if args.step:
        return run_single_step(args.step.upper(), args.api_url)
    return run_pipeline(args.api_url)


def cmd_viz(_: argparse.Namespace) -> int:
    """Этап H: графики по готовой витрине."""
    from src import visualize

    visualize.build_dashboard()
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    """Всё сразу: данные, протоколы, этап A (curl), конвейер C–H."""
    from scripts.curl_demo import main as curl_main
    from src import protocols

    seed_data.create_sources()
    protocols.write_protocol_table()

    print()
    print("Этап A: curl-сценарий по запущенному API...")
    curl_code = curl_main(base_url=args.api_url)
    if curl_code != 0:
        print("\nЭтап A не выполнен (см. сообщение выше). Продолжаю остальные этапы.")

    return run_pipeline(args.api_url, with_viz=True)


# ---------------------------------------------------------------------------
# Конвейер
# ---------------------------------------------------------------------------
def run_pipeline(api_url: str = config.API_URL, with_viz: bool = False) -> int:
    """Полный проход C -> D -> E -> F -> G (+ H). Пишет results/pipeline_report.txt."""
    from src import database, loaders, transform

    report.start(config.PIPELINE_REPORT)
    try:
        orgs = loaders.load_organizations()
        cities = loaders.load_cities()
        txs = loaders.load_transactions_api(api_url)

        orgs, txs, cities = loaders.stage_c(orgs, txs, cities, api_url=api_url)

        orgs, txs, cities = transform.stage_d(orgs, txs, cities)
        joined = transform.stage_e(orgs, txs, cities)
        database.stage_f(orgs, txs, cities)
        mart = transform.stage_g(joined["with_cities"], txs, orgs)

        if with_viz:
            from src import visualize

            visualize.build_dashboard(mart)
    except (loaders.ApiUnavailableError, FileNotFoundError) as exc:
        report.log(f"\nОШИБКА: {exc}")
        return 2
    finally:
        report.close()

    print(f"\nОтчёт по этапам {'C–H' if with_viz else 'C–G'}: {config.PIPELINE_REPORT}")
    print(f"Витрина: {config.MART_CSV} и {config.MART_PARQUET}")
    if not with_viz:
        print("Графики: python lab_2.py viz")
    return 0


def run_single_step(step: str, api_url: str = config.API_URL) -> int:
    """Запускает один этап отдельно — на случай вопроса «покажите только это»."""
    from src import database, loaders, transform

    if step not in STEPS:
        print(f"Неизвестный этап: {step}. Допустимо: {', '.join(STEPS)}")
        return 1

    report.start(config.RESULTS / f"step_{step}_report.txt")
    print(f"Отдельный запуск этапа {step}: {STEPS[step]}")
    try:
        orgs = loaders.load_organizations()
        cities = loaders.load_cities()
        txs = loaders.load_transactions_api(api_url)

        if step == "C":
            loaders.stage_c(orgs, txs, cities, api_url=api_url)

        elif step == "D":
            transform.stage_d(orgs, txs, cities)

        elif step == "E":
            prepared = transform.normalize_keys(orgs, txs, cities, verbose=False)
            transform.stage_e(*prepared)

        elif step == "F":
            orgs_n, txs_n, cities_n = transform.normalize_keys(orgs, txs, cities, verbose=False)
            database.stage_f(orgs_n, txs_n, cities_n)

        elif step == "G":
            orgs_n, txs_n, cities_n = transform.normalize_keys(orgs, txs, cities, verbose=False)
            joined = transform.merge_with_cities(
                transform.merge_orgs_transactions(orgs_n, txs_n, how="left"), cities_n
            )
            transform.stage_g(joined, txs_n, orgs_n)

    except (loaders.ApiUnavailableError, FileNotFoundError) as exc:
        report.log(f"\nОШИБКА: {exc}")
        return 2
    finally:
        report.close()

    print(f"\nОтчёт по этапу {step}: {config.RESULTS / f'step_{step}_report.txt'}")
    return 0


# ---------------------------------------------------------------------------
# Разбор аргументов
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Лабораторная работа II: curl, SQL JOIN и объединение данных.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Пример полного запуска:\n"
            "  1) python lab_2.py init\n"
            "  2) python lab_2.py server        (в отдельном терминале)\n"
            "  3) python lab_2.py all"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="создать исходные данные")

    server = subparsers.add_parser("server", help="запустить REST API")
    server.add_argument("--port", type=int, default=config.API_PORT, help="порт (по умолчанию 8000)")
    server.add_argument("--reload", action="store_true", help="автоперезапуск при изменении кода")

    curl = subparsers.add_parser("curl", help="этап A: curl-сценарий")
    curl.add_argument("--api-url", default=config.API_URL, help="адрес API")

    subparsers.add_parser("protocols", help="этап B: таблица протоколов")

    pipeline = subparsers.add_parser("pipeline", help="этапы C-G")
    pipeline.add_argument("--api-url", default=config.API_URL, help="адрес API")
    pipeline.add_argument("--step", choices=[s.lower() for s in STEPS] + list(STEPS), help="выполнить только один этап")

    subparsers.add_parser("viz", help="этап H: графики")

    all_cmd = subparsers.add_parser("all", help="всё сразу: init + protocols + curl + pipeline + viz")
    all_cmd.add_argument("--api-url", default=config.API_URL, help="адрес API")

    step = subparsers.add_parser("step", help="один этап отдельно (C, D, E, F, G)")
    step.add_argument("letter", choices=list(STEPS) + [s.lower() for s in STEPS], help="буква этапа")
    step.add_argument("--api-url", default=config.API_URL, help="адрес API")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "server":
            return cmd_server(args)
        if args.command == "curl":
            return cmd_curl(args)
        if args.command == "protocols":
            return cmd_protocols(args)
        if args.command == "pipeline":
            return cmd_pipeline(args)
        if args.command == "viz":
            return cmd_viz(args)
        if args.command == "all":
            return cmd_all(args)
        if args.command == "step":
            return run_single_step(args.letter.upper(), args.api_url)
    except ModuleNotFoundError as exc:
        print(f"\nНе установлена зависимость: {exc.name}.")
        print("Установите всё необходимое: python -m pip install -r requirements.txt")
        return 2
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
        return 130

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
