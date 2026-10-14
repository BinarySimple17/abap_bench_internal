"""Перенос закрытых сессий из docs/sessions.md в docs/sessions-archive.md.

Гигиена плана сессий по образцу беклога (harness/scripts/backlog_archive.py):
таблица в sessions.md содержит только живой план (⬜/◐); строки со статусом
«✅ …» переносятся в архив. Строка переносится как есть — детали остаются в
файле сессии docs/sessions/<ID>_session.md, хронология переходов —
Mermaid-диаграмма «История» в sessions.md. Секции архива вне таблицы скрипт
не трогает.

✅-строка в основной таблице — валидное состояние (окно между закрытием сессии
и переносом: make check не краснеет); чистоту обеспечивает --check.

Попутно переносимые сессии дописываются в Mermaid-диаграмму «История»: узел —
в субграф дня закрытия (дня нет — субграф создаётся и продлевает цепочку дней;
секции «История» нет — она создаётся: заголовок `## История` + `flowchart TB`).
Ряд длиннее 8 узлов не растягивается (масштаб рендера). Цвет узла = класс трека
(первая буква ID): TRACK_CLASS с дефолтом — любая буква-трек мапится безопасно.

Запуск (из корня репозитория или откуда угодно — пути резолвятся от скрипта):
    python harness/scripts/session_archive.py             # перенос
    python harness/scripts/session_archive.py --dry-run   # показать план без правок
    python harness/scripts/session_archive.py --check     # код 1, если в sessions.md
                                                          # есть ✅-строки или архив невалиден
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
DOCS = REPO_ROOT / "docs"
INDEX_PATH = DOCS / "sessions.md"
ARCHIVE_PATH = DOCS / "sessions-archive.md"

DONE_MARKER = "✅"
# распознавание строки таблицы — как в check_sessions.parse_rows:
# первая ячейка — ID сессии (любая латинская буква = трек + 2 цифры)
ROW_PATTERN = re.compile(r"^\|\s*([A-Z]\d{2})\s*\|")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# диаграмма «История»: субграф дня `subgraph dMMDD ["YYYY-MM-DD"]`, узловые ряды
# `A --> B --> C`, цепочка дней `d0830 --> ... --> d0907`
DAY_SUBGRAPH_RE = re.compile(r"subgraph (d\d{4}) ")
DAY_CHAIN_RE = re.compile(r"^\s*d\d{4}(?: --> d\d{4})*\s*$")
CHAIN_SEP = " --> "
# день с большим рядом рендерится непропорционально мелко (весь flowchart
# масштабируется под самый широкий субграф) — длиннее 8 узлов ряд не растягиваем
MAX_ROW_NODES = 8
# секция «История»: заголовок + mermaid-блок с `flowchart TB`
HISTORY_HEADING = "## История"
FLOWCHART_RE = re.compile(r"^flowchart TB\s*$")

ARCHIVE_SKELETON = """\
# Архив сессий — закрытые (✅)

Индекс закрытых сессий; сопровождается скриптом `harness/scripts/session_archive.py`
(переносит ✅-строки из таблицы `docs/sessions.md` — гигиена по образцу беклога).
Детали — в файле сессии `docs/sessions/<ID>_session.md`; хронология переходов —
Mermaid-диаграмма «История» в `docs/sessions.md`. Строка переносится как есть,
без потери информации.

| # | Файл | Этап | Владелец | Зависимости | Оценка | Приоритет | Статус |
|---|------|------|----------|-------------|--------|-----------|--------|
"""


def parse_rows(text: str) -> dict[str, str]:
    """{ID: исходная строка} — строки таблицы сессий (первая ячейка — ID)."""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        match = ROW_PATTERN.match(line)
        if match:
            rows[match.group(1)] = line
    return rows


def status_cell(line: str) -> str:
    """Последняя ячейка строки таблицы (как в check_sessions.parse_rows)."""
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return cells[-1] if cells else ""


def is_closed(line: str) -> bool:
    return DONE_MARKER in status_cell(line)


def archive_problems(index_rows: dict[str, str]) -> list[str]:
    """Инварианты архива: только ✅ с датой закрытия; без дублей основной таблицы."""
    if not ARCHIVE_PATH.is_file():
        return []
    problems: list[str] = []
    rows = parse_rows(ARCHIVE_PATH.read_text(encoding="utf-8"))
    for sid, line in sorted(rows.items()):
        status = status_cell(line)
        if sid in index_rows:
            problems.append(f"{sid}: строка и в sessions.md, и в архиве — оставь в одном месте")
        elif DONE_MARKER not in status:
            problems.append(f"{sid}: в архиве не закрытая строка ({status or '—'}) — архив только для ✅")
        elif not DATE_RE.search(status):
            problems.append(f"{sid}: ✅ в архиве без даты закрытия")
    return problems


def write_archive(moved: dict[str, str]) -> int:
    """Добавляет строки в таблицу архива (дедуп по ID, сортировка по ID),
    сохраняя остальной документ."""
    text = (ARCHIVE_PATH.read_text(encoding="utf-8")
            if ARCHIVE_PATH.is_file() else ARCHIVE_SKELETON)
    existing = parse_rows(text)
    added = 0
    for sid, line in moved.items():
        if sid not in existing:
            existing[sid] = line
            added += 1
    kept = [line for line in text.splitlines() if not ROW_PATTERN.match(line)]
    separator = next(i for i, line in enumerate(kept) if line.startswith("|---"))
    kept[separator + 1:separator + 1] = (existing[sid] for sid in sorted(existing))
    ARCHIVE_PATH.write_text("\n".join(kept).rstrip("\n") + "\n", encoding="utf-8")
    return added


def rewrite_index(text: str, moved_lines: set[str]) -> str:
    """Убирает перенесённые строки из таблицы sessions.md."""
    kept = [line for line in text.splitlines() if line not in moved_lines]
    return "\n".join(kept).rstrip("\n") + "\n"


def _ensure_history_section(lines: list[str]) -> int:
    """Индекс строки `flowchart TB` секции «История»; секция/диаграмма
    создаётся при отсутствии (заголовок `## История` + `flowchart TB`)."""
    heading_idx = next((i for i, ln in enumerate(lines) if ln.strip() == HISTORY_HEADING), None)
    if heading_idx is None:
        lines.extend(["", HISTORY_HEADING, "", "```mermaid", "flowchart TB", "```"])
        return len(lines) - 2
    section_end = next((i for i in range(heading_idx + 1, len(lines))
                        if lines[i].startswith("## ")), len(lines))
    flow_idx = next((i for i in range(heading_idx + 1, section_end)
                     if FLOWCHART_RE.match(lines[i].strip())), None)
    if flow_idx is None:
        # секция есть, диаграммы нет — добавим блок в начало секции
        lines[heading_idx + 1:heading_idx + 1] = ["", "```mermaid", "flowchart TB", "```"]
        flow_idx = heading_idx + 3
    return flow_idx


def _mermaid_end(lines: list[str], flow_idx: int) -> int:
    """Индекс закрывающей ограды ``` блока диаграммы (вставки — перед ней)."""
    return next((i for i in range(flow_idx + 1, len(lines)) if lines[i].strip() == "```"),
                len(lines))


def update_diagram(text: str, moved: dict[str, str]) -> tuple[str, list[str]]:
    """Дописывает закрытые сессии в Mermaid-диаграмму «История» sessions.md.

    Узел ставится в субграф дня закрытия (дата — из статуса «✅ YYYY-MM-DD»);
    дня нет — субграф создаётся и продлевает цепочку дней. Ряд длиннее
    MAX_ROW_NODES узлов не растягивается (масштаб рендера) — начинается новая
    строка. Узлы дописываются и в class-строки цветов трека. Возвращает
    (текст, добавленные ID).
    """
    updates = [(sid, m.group()) for sid, line in sorted(moved.items())
               if (m := DATE_RE.search(status_cell(line)))]
    if not updates:
        return text, []
    lines = text.splitlines()
    flow_idx = _ensure_history_section(lines)
    added: list[str] = []
    for sid, date in updates:
        day = "d" + date.replace("-", "")[4:]
        mermaid_end = _mermaid_end(lines, flow_idx)
        sub_idx = next((i for i in range(flow_idx + 1, mermaid_end)
                        if (m := DAY_SUBGRAPH_RE.search(lines[i])) and m.group(1) == day), None)
        if sub_idx is None:
            block = [
                f'    subgraph {day} ["{date}"]',
                "        direction LR",
                f"        {sid}",
                "    end",
            ]
            chain_idx = next((i for i in range(flow_idx + 1, mermaid_end)
                              if DAY_CHAIN_RE.match(lines[i])), None)
            if chain_idx is None:
                # пустая диаграмма: субграф + первый узел цепочки дней
                lines[flow_idx + 1:flow_idx + 1] = block + [day]
            else:
                lines[chain_idx:chain_idx] = block
                lines[chain_idx + 4] += CHAIN_SEP + day
        else:
            end_idx = next(i for i in range(sub_idx, mermaid_end) if lines[i].strip() == "end")
            block = lines[sub_idx:end_idx]
            if any(re.search(rf"\b{re.escape(sid)}\b", ln) for ln in block):
                continue   # сессия уже в диаграмме — идемпотентность
            row_idx = max(i for i in range(sub_idx, end_idx)
                          if lines[i].strip() not in ("", "end")
                          and not lines[i].strip().startswith(("direction", "subgraph")))
            if len(lines[row_idx].strip().split(CHAIN_SEP)) >= MAX_ROW_NODES:
                lines.insert(row_idx + 1, f"        {sid}")
            else:
                lines[row_idx] += CHAIN_SEP + sid
        added.append(sid)
    if added:
        update_class_lines(lines, added, flow_idx)
    return "\n".join(lines) + "\n", added


# цвет узла = трек сессии (первая буква ID) → имя класса из classDef sessions.md;
# дефолт common — любая буква-трек мапится безопасно (свой трек добавь сюда)
DEFAULT_TRACK_CLASS = "common"
TRACK_CLASS = {"V": "data", "E": "data", "B": "ctrl", "S": "common", "A": "common"}
_CLASS_LINE_RE = re.compile(r"^    class ([\w,]+) (\w+)$")   # `class X01,X02 common`
_CLASSDEF_STYLES = {
    "common": "fill:#a9d18e,stroke:#375623,color:#1e2f10,stroke-width:2px",
    "data": "fill:#9ecae1,stroke:#1f4e79,color:#0a2540,stroke-width:2px",
    "ctrl": "fill:#f5a8a2,stroke:#a12622,color:#5c130f,stroke-width:2px",
}


def update_class_lines(lines: list[str], added: list[str], flow_idx: int) -> None:
    """Дописывает добавленные узлы в class-строки диаграммы (урок B28:
    без этого новые узлы рендерятся бесцветными). Класс-строки/classDef для
    класса отсутствуют — создаются перед закрытием mermaid-блока."""
    mermaid_end = _mermaid_end(lines, flow_idx)
    for sid in added:
        klass = TRACK_CLASS.get(sid[:1].upper(), DEFAULT_TRACK_CLASS)
        idx = next((i for i in range(flow_idx + 1, mermaid_end)
                    if (m := _CLASS_LINE_RE.match(lines[i])) and m.group(2) == klass), None)
        if idx is None:
            insert = []
            if klass in _CLASSDEF_STYLES and not any(
                    f"classDef {klass} " in lines[i] for i in range(flow_idx + 1, mermaid_end)):
                insert.append(f"    classDef {klass} {_CLASSDEF_STYLES[klass]}")
            insert.append(f"    class {sid} {klass}")
            lines[mermaid_end:mermaid_end] = insert
            mermaid_end += len(insert)
            continue
        ids = _CLASS_LINE_RE.match(lines[idx]).group(1)
        if re.search(rf"\b{re.escape(sid)}\b", ids):
            continue   # уже в списке — идемпотентность
        lines[idx] = f"    class {ids},{sid} {klass}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="показать план переноса, файлы не менять")
    parser.add_argument("--check", action="store_true",
                        help="код 1, если в sessions.md есть ✅-строки или архив невалиден")
    args = parser.parse_args()

    if not INDEX_PATH.is_file():
        print(f"✗ нет {INDEX_PATH.relative_to(REPO_ROOT)} — возьми шаблон "
              f"harness/templates/sessions.md (bash harness/scripts/init-harness.sh)")
        return 1
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    rows = parse_rows(index_text)
    closed = {sid: line for sid, line in rows.items() if is_closed(line)}
    active = len(rows) - len(closed)

    problems = archive_problems(rows)
    for problem in problems:
        print(f"⚠️  {problem}")

    if args.check:
        if problems:
            return 1
        if closed:
            print("✗ в таблице sessions.md закрытые строки: " + ", ".join(sorted(closed)))
            return 1
        print(f"✓ таблица sessions.md чиста ({active} активных), архив валиден")
        return 0

    if not closed:
        print(f"переносить нечего: {active} активных, закрытых нет")
        return 0

    print("план переноса в sessions-archive.md:")
    for sid in sorted(closed):
        print(f"  {sid}")
    _, diagram_added = update_diagram(index_text, closed)
    if diagram_added:
        print(f"диаграмма «История»: добавлю {', '.join(diagram_added)}")
    print(f"итого: закрытых {len(closed)}, останется активных {active}")
    if args.dry_run:
        return 0

    new_text, diagram_added = update_diagram(index_text, closed)
    added = write_archive(closed)
    INDEX_PATH.write_text(rewrite_index(new_text, set(closed.values())), encoding="utf-8")
    print(f"готово: в архив добавлено {added} строк, в таблице осталось {active} активных"
          + (f", в диаграмму добавлено {len(diagram_added)}" if diagram_added else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
