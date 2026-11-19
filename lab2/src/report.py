"""Единый вывод: текст печатается в консоль и одновременно пишется в отчёт.

Зачем это нужно: все этапы печатают много промежуточных чисел, и их удобно
потом приложить к отчёту по лабораторной. Поэтому каждый этап пишет через
report.log(), а не через print().
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# В консоли Windows не всякий символ есть в кодировке (cp866/cp1251),
# поэтому не падаем, а заменяем неподдерживаемые символы на '?'.
try:
    sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
except (AttributeError, ValueError):  # pragma: no cover - старые версии Python
    pass


class Report:
    """Приёмник текста: консоль + (необязательно) файл."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._file = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # utf-8-sig добавляет BOM: тогда «Блокнот» и Word на Windows
            # сразу видят русский текст в правильной кодировке.
            self._file = self.path.open("w", encoding="utf-8-sig", newline="\n")

    # --- базовые операции --------------------------------------------------
    def write(self, text: str = "") -> None:
        print(text)
        if self._file is not None:
            self._file.write(text + "\n")

    def heading(self, text: str, char: str = "=") -> None:
        """Крупный заголовок этапа."""
        self.write()
        self.write(char * 78)
        self.write(text)
        self.write(char * 78)

    def subheading(self, text: str) -> None:
        """Подзаголовок внутри этапа."""
        self.write()
        self.write(text)
        self.write("-" * len(text))

    def frame(
        self,
        df: pd.DataFrame,
        title: str | None = None,
        index: bool = False,
        justify: str | None = None,
    ) -> None:
        """Печатает DataFrame в виде текстовой таблицы.

        justify='left' удобен для таблиц «показатель — значение»: подписи
        не разъезжаются, когда длина названий разная.
        """
        if title:
            self.write(title)
        if justify is None:
            self.write(df.to_string(index=index))
        else:
            self.write(df.to_string(index=index, justify=justify))

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


# Глобальный отчёт. По умолчанию печатает только в консоль.
REPORT = Report()


def start(path: Path | None) -> Report:
    """Начинает новый отчёт (файл перезаписывается)."""
    global REPORT
    REPORT.close()
    REPORT = Report(path)
    return REPORT


def log(text: str = "") -> None:
    REPORT.write(text)


def heading(text: str, char: str = "=") -> None:
    REPORT.heading(text, char)


def subheading(text: str) -> None:
    REPORT.subheading(text)


def frame(
    df: pd.DataFrame,
    title: str | None = None,
    index: bool = False,
    justify: str | None = None,
) -> None:
    REPORT.frame(df, title=title, index=index, justify=justify)


def grid(
    headers: list[str],
    rows: list[list[str]],
    indent: int = 3,
    aligns: list[str] | None = None,
) -> None:
    """Печатает простую текстовую таблицу с выравниванием по столбцам.

    Нужна для таблиц вида «показатель — значение»: обычный DataFrame
    выравнивает числа вправо, и подписи разной длины разъезжаются.
    """
    aligns = aligns or ["l"] * len(headers)
    cells = [[str(cell) for cell in row] for row in rows]

    widths = [len(header) for header in headers]
    for row in cells:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    pad = " " * indent

    def render(row: list[str]) -> str:
        parts = [
            cell.ljust(widths[index]) if aligns[index] == "l" else cell.rjust(widths[index])
            for index, cell in enumerate(row)
        ]
        return (pad + "  ".join(parts)).rstrip()

    log(render(headers))
    log(pad + "  ".join("-" * width for width in widths))
    for row in cells:
        log(render(row))


def plural(number: int, one: str, few: str, many: str) -> str:
    """Выбирает форму слова для числа: 1 строка / 2 строки / 5 строк."""
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def close() -> None:
    REPORT.close()
