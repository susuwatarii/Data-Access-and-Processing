"""ЭТАП H. Визуализация витрины: два обязательных графика и один дашборд.

Графики строятся по готовой витрине data/processed/data_mart.csv — то есть
по тому же файлу, который загружается в Power BI / Tableau. Поэтому картинка
и BI-отчёт всегда показывают одни и те же числа.

Запуск отдельно:
    python lab_2.py viz
    python -m src.visualize
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # запуск файлом: python src/visualize.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib

matplotlib.use("Agg")  # без графического окна: сохраняем файл

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src import config, report  # noqa: E402

# Единая палитра, чтобы графики выглядели как один дашборд
COLOR_MAIN = "#2F5D8A"
COLOR_ACCENT = "#C4622D"
COLOR_MUTED = "#9AA5B1"  # для строки «не указан»: это не настоящий регион
COLOR_GRID = "#D9D9D9"
COLOR_TEXT = "#1F2933"


def load_mart(path: Path = config.MART_CSV) -> pd.DataFrame:
    """Читает витрину из CSV (после этапа G)."""
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Не найдена витрина {path}. Сначала постройте её: python lab_2.py pipeline"
        )
    return pd.read_csv(path, encoding="utf-8-sig", parse_dates=["last_transaction_date"])


def _millions(value: float) -> float:
    return value / 1_000_000


def _draw_regions(ax: plt.Axes, mart: pd.DataFrame) -> pd.DataFrame:
    """График 1: общая сумма операций по регионам."""
    by_region = (
        mart.groupby("region_name", as_index=False)["total_amount"]
        .sum()
        .sort_values("total_amount", ascending=True)
    )

    bars = ax.barh(
        by_region["region_name"],
        [_millions(value) for value in by_region["total_amount"]],
        color=[COLOR_MUTED if name == "не указан" else COLOR_MAIN for name in by_region["region_name"]],
        height=0.62,
    )
    max_value = float(by_region["total_amount"].max())
    for bar, value in zip(bars, by_region["total_amount"]):
        ax.text(
            _millions(value) + max_value / 1_000_000 * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"{value:,.0f} руб.".replace(",", " "),
            va="center",
            fontsize=10,
            color=COLOR_TEXT,
        )

    ax.set_title("Общая сумма операций по регионам", fontsize=14, color=COLOR_TEXT, pad=14)
    ax.set_xlabel("Сумма операций, млн руб.", fontsize=10, color=COLOR_TEXT)
    ax.grid(axis="x", color=COLOR_GRID, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLOR_GRID)
    ax.tick_params(colors=COLOR_TEXT, labelsize=10)

    return by_region


def _draw_top_orgs(ax: plt.Axes, mart: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """График 2: ТОП организаций по общей сумме операций."""
    top = mart.nlargest(top_n, "total_amount").sort_values("total_amount", ascending=True)

    bars = ax.barh(
        top["org_name"],
        [_millions(value) for value in top["total_amount"]],
        color=COLOR_ACCENT,
        height=0.62,
    )
    max_value = float(top["total_amount"].max())
    for bar, value in zip(bars, top["total_amount"]):
        ax.text(
            _millions(value) + max_value / 1_000_000 * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"{value:,.0f} руб.".replace(",", " "),
            va="center",
            fontsize=9.5,
            color=COLOR_TEXT,
        )

    ax.set_title(f"ТОП-{top_n} организаций по сумме операций", fontsize=14, color=COLOR_TEXT, pad=14)
    ax.set_xlabel("Сумма операций, млн руб.", fontsize=10, color=COLOR_TEXT)
    ax.grid(axis="x", color=COLOR_GRID, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLOR_GRID)
    ax.tick_params(colors=COLOR_TEXT, labelsize=9.5)

    return top


def build_dashboard(mart: pd.DataFrame | None = None) -> Path:
    """Строит дашборд из двух панелей и сохраняет results/dashboard.png."""
    if mart is None:
        mart = load_mart()

    config.RESULTS.mkdir(parents=True, exist_ok=True)

    plt.rcParams["font.family"] = "DejaVu Sans"  # в этом шрифте есть кириллица
    fig, axes = plt.subplots(1, 2, figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor("white")

    by_region = _draw_regions(axes[0], mart)
    top_orgs = _draw_top_orgs(axes[1], mart)

    total = float(mart["total_amount"].sum())
    operations = int(mart["transactions_count"].sum())
    without_operations = int((mart["transactions_count"] == 0).sum())

    fig.suptitle(
        "Аналитическая витрина: операции организаций, 2026 год",
        fontsize=17,
        color=COLOR_TEXT,
        y=0.97,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.915,
        f"{len(mart)} организаций, {len(by_region)} регионов, "
        f"{operations} операций, {total / 1_000_000:.1f} млн руб. "
        f"(организаций без операций: {without_operations})",
        ha="center",
        fontsize=11,
        color="#52606D",
    )
    fig.text(
        0.5,
        0.03,
        "Источник: data/processed/data_mart.csv. Суммы номинальные: "
        "валютные операции не пересчитаны в рубли.",
        ha="center",
        fontsize=9,
        color="#7B8794",
    )

    fig.tight_layout(rect=(0.02, 0.06, 0.98, 0.9))
    fig.savefig(config.DASHBOARD_PNG, facecolor="white")
    plt.close(fig)

    # Отдельные картинки для отчёта (те же данные, по одной панели).
    for path, drawer, values in (
        (config.CHART_REGIONS_PNG, _draw_regions, by_region),
        (config.CHART_ORGS_PNG, _draw_top_orgs, top_orgs),
    ):
        single, ax = plt.subplots(figsize=(11, 6), dpi=120)
        single.patch.set_facecolor("white")
        drawer(ax, mart)
        single.tight_layout()
        single.savefig(path, facecolor="white")
        plt.close(single)

    # --- вывод чисел, чтобы график можно было объяснить без картинки -------
    report.heading("ЭТАП H. ВИЗУАЛИЗАЦИЯ И BI")
    total_text = f"{total:,.2f}".replace(",", " ")
    report.log(f"   Витрина: {len(mart)} строк, сумма {total_text} руб.")
    report.log(f"   График 1: сумма операций по регионам ({len(by_region)} регионов)")
    report.frame(by_region.sort_values("total_amount", ascending=False), index=False)

    leader = by_region.iloc[-1]
    share = float(leader["total_amount"]) / total * 100 if total else 0.0
    leader_sum = f"{float(leader['total_amount']):,.0f}".replace(",", " ")
    report.log(f"   Лидер по сумме: {leader['region_name']} — "
               f"{leader_sum} руб. ({share:.1f}% от общей суммы)")

    report.log()
    report.log(f"   График 2: ТОП-{len(top_orgs)} организаций по сумме операций")
    # Таблица печатается построчно через report.grid, а не через DataFrame.to_string:
    # так ширина строки зависит только от данных и гарантированно влезает в консоль.
    top_rows = [
        [
            row["org_name"],
            row["region_name"],
            str(int(row["transactions_count"])),
            f"{int(round(float(row['total_amount']))):,}".replace(",", " "),
        ]
        for row in top_orgs.sort_values("total_amount", ascending=False).to_dict("records")
    ]
    report.grid(
        ["организация", "регион", "операций", "сумма, руб."],
        top_rows,
        aligns=["l", "l", "r", "r"],
    )
    best = top_orgs.iloc[-1]
    best_sum = f"{float(best['total_amount']):,.0f}".replace(",", " ")
    report.log(f"   Лидер: {best['org_name']} — {best_sum} руб.")
    report.log(f"   Организаций без операций в витрине: {without_operations} "
               f"(на графике ТОП они не видны — у них сумма 0).")

    report.log()
    report.log("   Сохранено:")
    for path in (config.DASHBOARD_PNG, config.CHART_REGIONS_PNG, config.CHART_ORGS_PNG):
        report.log(f"   {path.name}: {path.stat().st_size / 1024:.1f} КБ")
    report.log()
    report.log("   Для BI: файл data/processed/data_mart.csv импортируется в Power BI /")
    report.log("   Tableau / Qlik как плоская таблица (одна строка = одна организация).")

    return config.DASHBOARD_PNG


def main() -> None:
    """Отдельный запуск этапа H: python -m src.visualize"""
    try:
        build_dashboard()
    except FileNotFoundError as exc:
        report.log(f"\nОШИБКА: {exc}")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
