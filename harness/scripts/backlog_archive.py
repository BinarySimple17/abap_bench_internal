"""Перенос закрытых элементов беклога из backlog/README.md в backlog/archive.md.

Правило гигиены беклога (backlog/README.md, «Жизненный цикл» п.5): карта
активных элементов содержит только незакрытые элементы; строки с состоянием
«✅ …» переносятся в архив. Детали закрытия живут в файле BL-*.md и файле
сессии — архив хранит строку карты как навигацию (строка переносится как есть,
без потери информации).

--check дополнительно: счётчик «Последний занятый номер» обязан совпадать
с максимальным известным номером (README + архив); orphan (BL-файл без строки
в картах), missing-file (строка без файла items/), дубли (карта и архив
одновременно). Пустой беклог (счётчик BL-0, пустая карта) — валидный старт.

Запуск (из корня репозитория или откуда угодно — пути резолвятся от скрипта):
    python harness/scripts/backlog_archive.py             # перенос
    python harness/scripts/backlog_archive.py --dry-run   # показать план без правок
    python harness/scripts/backlog_archive.py --check     # код 1, если в README есть
                                                          # ✅-строки или расхождения
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Консоль Windows (cp866/cp1251 при пайпе): форсируем UTF-8, иначе кириллица ломается
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[2]   # harness/scripts/ → корень проекта
BACKLOG = REPO_ROOT / "backlog"
README_PATH = BACKLOG / "README.md"
ARCHIVE_PATH = BACKLOG / "archive.md"

CLOSED_MARKER = "✅"
# счётчик сквозной нумерации: строка в README, обновляется при каждом новом номере
COUNTER_RE = re.compile(r"Последний занятый номер: \*\*BL-(\d+)\*\*")
ROW_PATTERN = re.compile(r"^\| \[BL-(\d+)\]\(")
EXPECTED_COLUMNS = 5
POINTER_LINE = "**Закрытые элементы** — в [archive.md](archive.md)."

ARCHIVE_HEADER = """\
# Архив беклога — закрытые элементы

Индекс закрытых элементов беклога; сопровождается скриптом
`harness/scripts/backlog_archive.py` (переносит ✅-строки из карты активных
элементов в `backlog/README.md`). Детали закрытия — в файле `BL-<N>-*.md` и в
файле соответствующей сессии; здесь — только навигация.

| ID | Название | Тип | Приоритет | Состояние |
|---|---|---|---|---|
"""


def parse_rows(text: str) -> list[tuple[int, str, list[str]]]:
    """Строки карты: (BL-номер, исходная строка, ячейки). Нераспознанные строки пропускаются."""
    rows = []
    for line in text.splitlines():
        match = ROW_PATTERN.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != EXPECTED_COLUMNS:
            print(f"⚠️  строка BL-{match.group(1)}: {len(cells)} ячеек вместо {EXPECTED_COLUMNS} — пропущена")
            continue
        rows.append((int(match.group(1)), line, cells))
    return rows


def is_closed(cells: list[str]) -> bool:
    return cells[-1].startswith(CLOSED_MARKER)


def read_archive_rows() -> dict[int, str]:
    if not ARCHIVE_PATH.exists():
        return {}
    return {bl_id: line for bl_id, line, _ in parse_rows(ARCHIVE_PATH.read_text(encoding="utf-8"))}


def write_archive(moved: list[tuple[int, str]]) -> int:
    """Пишет архив (дедуп по ID, сортировка по номеру); возвращает число добавленных строк."""
    existing = read_archive_rows()
    added = 0
    for bl_id, line in moved:
        if bl_id not in existing:
            existing[bl_id] = line
            added += 1
    body = "\n".join(existing[bl_id] for bl_id in sorted(existing))
    ARCHIVE_PATH.write_text(ARCHIVE_HEADER + body + "\n", encoding="utf-8")
    return added


def rewrite_readme(text: str, closed_lines: set[str]) -> str:
    """Убирает закрытые строки из карты, добавляет указатель на архив."""
    kept = [line for line in text.splitlines() if line not in closed_lines]
    if POINTER_LINE not in text:
        last_active = max(i for i, line in enumerate(kept) if ROW_PATTERN.match(line))
        kept[last_active + 1 : last_active + 1] = ["", POINTER_LINE]
    return "\n".join(kept).rstrip("\n") + "\n"


def known_row_ids() -> set[int]:
    """ID из строк карт README и архива (если он есть)."""
    ids = {bl_id for bl_id, _, _ in parse_rows(README_PATH.read_text(encoding="utf-8"))}
    if ARCHIVE_PATH.exists():
        ids |= {bl_id for bl_id, _, _ in parse_rows(ARCHIVE_PATH.read_text(encoding="utf-8"))}
    return ids


def counter_problems() -> list[str]:
    """Счётчик «Последний занятый номер» в README обязан существовать и совпадать
    с максимальным известным номером (README + архив) — иначе номера теряются
    (прецедент: коллизия BL-71 при слиянии веток 2026-09-05, rabap-9000)."""
    match = COUNTER_RE.search(README_PATH.read_text(encoding="utf-8"))
    if not match:
        return ["в backlog/README.md нет строки «Последний занятый номер: **BL-N**»"]
    declared = int(match.group(1))
    known_max = max(known_row_ids(), default=0)
    if declared != known_max:
        return [f"счётчик номера BL-{declared} не совпадает с максимальным известным "
                f"BL-{known_max} (README + архив) — обнови строку счётчика"]
    return []


def orphan_warnings() -> list[str]:
    """BL-файлы без строки ни в README, ни в архиве — расхождение карты с папкой."""
    known_ids = known_row_ids()
    problems = []
    for path in sorted(BACKLOG.joinpath("items").glob("BL-*.md")):
        match = re.match(r"BL-(\d+)-", path.name)
        if match is None:
            continue   # имя вне конвенции BL-<N>-<имя>.md — не карта-элемент
        if int(match.group(1)) not in known_ids:
            problems.append(f"{path.name}: файл есть, а строки в картах нет")
    return problems


LINK_FILE_RE = re.compile(r"\]\(([^)]+\.md)\)")


def missing_file_problems() -> list[str]:
    """Карта → файл (обратное направление orphan_warnings): строка README/архива
    ссылается на отсутствующий файл items/ — содержимое элемента потеряно,
    строка ведёт в пустоту (двусторонняя сверка «ничего не теряется», B32)."""
    problems: list[str] = []
    for where, path in (("README", README_PATH), ("архиве", ARCHIVE_PATH)):
        if not path.exists():
            continue
        for bl_id, line, _ in parse_rows(path.read_text(encoding="utf-8")):
            match = LINK_FILE_RE.search(line)
            if not match:
                problems.append(f"BL-{bl_id}: строка в {where} без ссылки на файл items/")
            elif not (BACKLOG / match.group(1)).exists():
                problems.append(f"BL-{bl_id}: строка в {where} ссылается на "
                                f"отсутствующий файл {match.group(1)}")
    return problems


def duplicate_row_problems() -> list[str]:
    """Один BL в активной карте И в архиве — двусмысленность «активен или закрыт?»
    (прецедент B32: 6 дубликатов оставались в активной карте после закрытия)."""
    active = {bl_id for bl_id, _, _ in parse_rows(README_PATH.read_text(encoding="utf-8"))}
    return [
        f"BL-{bl_id}: строка и в активной карте, и в архиве — оставь в одном месте"
        for bl_id in sorted(active & set(read_archive_rows()))
    ]


def consistency_problems() -> list[str]:
    """Двусторонняя сверка «файлы ↔ карты ↔ архив» одним списком (для --check)."""
    return orphan_warnings() + missing_file_problems() + duplicate_row_problems()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="показать план переноса, файлы не менять")
    parser.add_argument("--check", action="store_true", help="код 1, если в README остались ✅-строки")
    args = parser.parse_args()

    if not README_PATH.is_file():
        print(f"✗ нет {README_PATH.relative_to(REPO_ROOT)} — возьми шаблон "
              f"harness/templates/backlog/README.md (bash harness/scripts/init-harness.sh)")
        return 1
    readme_text = README_PATH.read_text(encoding="utf-8")
    rows = parse_rows(readme_text)
    closed = [(bl_id, line) for bl_id, line, cells in rows if is_closed(cells)]
    active_count = len(rows) - len(closed)

    for warning in orphan_warnings():
        print(f"⚠️  {warning}")
    for problem in counter_problems():
        print(f"⚠️  {problem}")

    if args.check:
        # двусторонняя сверка «файлы ↔ карты ↔ архив» — ничего не теряется (B32)
        inconsistencies = consistency_problems()
        if counter_problems():
            return 1
        if closed:
            print(f"✗ в карте активных элементов {len(closed)} закрытых строк: "
                  + ", ".join(f"BL-{bl_id}" for bl_id, _ in closed))
            return 1
        if inconsistencies:
            print(f"✗ расхождения файлов и карт ({len(inconsistencies)}):")
            for problem in inconsistencies:
                print(f"  - {problem}")
            return 1
        print(f"✓ карта активных элементов чиста ({active_count} активных), "
              "файлы ↔ карты ↔ архив сходятся")
        return 0

    if not closed:
        print(f"переносить нечего: {active_count} активных, закрытых нет")
        return 0

    print("план переноса в archive.md:")
    for bl_id, _ in closed:
        print(f"  BL-{bl_id}")
    print(f"итого: закрытых {len(closed)}, останется активных {active_count}")
    if args.dry_run:
        return 0

    added = write_archive(closed)
    README_PATH.write_text(rewrite_readme(readme_text, {line for _, line in closed}), encoding="utf-8")
    print(f"готово: в архив добавлено {added} строк, в README осталось {active_count} активных")
    return 0


if __name__ == "__main__":
    sys.exit(main())
