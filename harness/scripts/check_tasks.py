#!/usr/bin/env python3
"""Гейт формата задач tasks/*.task.txt — источник правды содержания бенчмарка.

Формат файла — PLAN.md §4.1: шапка мета-строк (@id, @source, @method,
@category, @active), затем секции ---PROMPT--- (обязательна),
---CANONICAL--- и ---TEST--- (опциональны). На каждый файл проверяется:
  - @id совпадает с именем файла (<id>.task.txt), id — [a-z][a-z0-9_]*;
  - обязательные мета-строки присутствуют; @active ∈ {true, false};
  - @method — имя ABAP-метода (нижний регистр, snake_case);
  - ---PROMPT--- непуста; непусты и присутствующие ---CANONICAL---/---TEST---;
  - ---CANONICAL---: класс переименован в lcl_solution (z_humaneval_* нет),
    есть пара CLASS lcl_solution DEFINITION ... ENDCLASS.;
  - ---TEST---: вызовы решения переписаны на lcl_solution=> (z_humaneval_*=> нет),
    есть тест-класс FOR TESTING.
Набор: @id уникальны по папке. Дословность PROMPT сверяется с исходным
датасетом (--source, дефолт F:/JAVA/LLM-Benchmark-ABAP-Code-Generation-main);
датасет недоступен — сверка пропускается с пометкой (промпты дословны —
PLAN.md §3, это условие сравнимости с исходным бенчмарком).

Только stdlib. Любое нарушение — exit 1.
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

REPO = Path(__file__).resolve().parents[2]   # harness/scripts/ → корень проекта
TASKS_DIR = REPO / "tasks"
DEFAULT_DATASET = Path("F:/JAVA/LLM-Benchmark-ABAP-Code-Generation-main")

SECTIONS = ("---PROMPT---", "---CANONICAL---", "---TEST---")
REQUIRED_META = ("id", "source", "method", "category", "active")
META_RE = re.compile(r"^@(\w+):\s*(.*?)\s*$")
METHOD_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TASK_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SOLUTION_CALL_RE = re.compile(r"\bz_humaneval_\w*\s*=>")


def parse_task(text: str) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """(мета, секции, проблемы структуры). Секция — текст до следующей секции."""
    meta: dict[str, str] = {}
    sections: dict[str, str] = {}
    problems: list[str] = []
    current: str | None = None
    buf: list[str] = []
    in_header = True
    for line in text.splitlines():
        marker = line.strip()
        if marker in SECTIONS:
            if current:
                sections[current] = "\n".join(buf).strip()
            current, buf, in_header = marker[3:-3], [], False
            continue
        if in_header:
            match = META_RE.match(line)
            if match:
                meta[match.group(1).lower()] = match.group(2)
            elif marker:
                problems.append(f"в шапке лишняя строка (мета — только «@ключ: значение»): {marker[:60]!r}")
        else:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return meta, sections, problems


def check_file(path: Path, dataset: Path | None) -> tuple[str, list[str]]:
    """(task_id, проблемы файла)."""
    problems: list[str] = []
    text = path.read_text(encoding="utf-8-sig")
    meta, sections, struct_problems = parse_task(text)
    problems += struct_problems

    task_id = path.name.removesuffix(".task.txt")   # не Path.stem: он срезает только .txt
    if not TASK_ID_RE.fullmatch(task_id):
        problems.append(f"имя файла {path.name!r} — ожидается <id>.task.txt, id = [a-z][a-z0-9_]*")
    missing = [name for name in REQUIRED_META if name not in meta]
    if missing:
        problems.append("нет обязательных мета-строк: " + ", ".join(f"@{name}" for name in missing))
    if meta.get("id") != task_id:
        problems.append(f"@id={meta.get('id', '—')!r} не совпадает с именем файла {task_id!r}")
    if meta.get("active", "").lower() not in ("true", "false"):
        problems.append(f"@active={meta.get('active', '—')!r} — ожидается true или false")
    method = meta.get("method", "")
    if method and not METHOD_RE.fullmatch(method):
        problems.append(f"@method={method!r} — не похоже на имя ABAP-метода (нижний регистр, snake_case)")

    if "PROMPT" not in sections:
        problems.append("нет секции ---PROMPT---")
    elif not sections["PROMPT"]:
        problems.append("секция ---PROMPT--- пуста")
    for name in ("CANONICAL", "TEST"):
        if name in sections and not sections[name]:
            problems.append(f"секция ---{name}--- пуста")

    canonical = sections.get("CANONICAL", "")
    if canonical:
        if "z_humaneval" in canonical:
            problems.append("---CANONICAL---: встречается z_humaneval — класс не переименован в lcl_solution")
        if not re.search(r"^CLASS\s+lcl_solution\s+DEFINITION", canonical, re.M) or "ENDCLASS." not in canonical:
            problems.append("---CANONICAL---: нет пары CLASS lcl_solution DEFINITION / ENDCLASS.")

    test = sections.get("TEST", "")
    if test:
        if SOLUTION_CALL_RE.search(test):
            problems.append("---TEST---: вызовы не переписаны на lcl_solution=> (встречается z_humaneval_*=>)")
        if "FOR TESTING" not in test:
            problems.append("---TEST---: нет тест-класса FOR TESTING")

    if dataset is not None and "PROMPT" in sections:
        num = re.fullmatch(r"humaneval_(\d+)", task_id)
        if num:
            source_prompt = dataset / "dataset" / "prompts" / f"{int(num.group(1))}.txt"
            if source_prompt.is_file():
                expected = source_prompt.read_text(encoding="utf-8-sig").strip()
                if sections["PROMPT"] != expected:
                    problems.append(f"PROMPT расходится с исходным датасетом ({source_prompt}) "
                                    "— промпт обязан быть дословным (PLAN.md §3)")
            else:
                problems.append(f"в датасете нет {source_prompt.name} — сверка PROMPT невозможна")
    return task_id, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_DATASET,
                        help="корень исходного датасета для сверки дословности PROMPT")
    args = parser.parse_args()

    dataset = args.source if args.source.is_dir() else None
    if dataset is None:
        print(f"ℹ  датасет не найден ({args.source}) — сверка дословности PROMPT пропущена")

    if not TASKS_DIR.is_dir():
        print(f"FAIL: нет папки {TASKS_DIR.relative_to(REPO)}")
        return 1
    files = sorted(TASKS_DIR.glob("*.task.txt"))
    if not files:
        print(f"FAIL: в {TASKS_DIR.relative_to(REPO)} нет *.task.txt")
        return 1

    ids: dict[str, str] = {}
    duplicates: list[str] = []
    failed = 0
    for path in files:
        task_id, problems = check_file(path, dataset)
        if task_id in ids:
            duplicates.append(f"{path.name}: @id {task_id!r} уже занят файлом {ids[task_id]}")
        else:
            ids[task_id] = path.name
        if problems:
            failed += 1
            print(f"{path.relative_to(REPO)}: {len(problems)}")
            for problem in problems:
                print(f"  - {problem}")
    for problem in duplicates:
        failed += 1
        print(problem)

    if failed:
        print(f"check-tasks: FAIL (проблемы в {failed} из {len(files)} файлов)")
        return 1
    checked = ", PROMPT сверены с датасетом" if dataset is not None else ""
    print(f"check-tasks: PASS ({len(files)} задач{checked})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
