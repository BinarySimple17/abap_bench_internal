#!/usr/bin/env python3
"""Гейты сессий — фиче-дисциплина (L07/L08) поверх docs/sessions.md.

Состояние фич живёт ТОЛЬКО в sessions: таблица индекса (⬜/◐/✅) + чекбоксы
файлов сессий. Параллельные трекеры (feature_list.json и т.п.) не ведутся.

Аудит (без аргументов; make check-sessions):
  - WIP=1: на трек (первая буква ID) не более одной ◐ в таблице;
  - каждый ✅ в таблице — с датой (ГГГГ-ММ-ДД);
  - архив docs/sessions-archive.md (если есть): только ✅ с датой, без дублей
    строк основной таблицы (перенос — harness/scripts/session_archive.py);
  - файл docs/sessions/*_session.md, не внесённый ни в таблицу, ни в архив,
    — orphan = FAIL (состояние фич живёт в индексе).
Гейт закрытия (--session ID; make verify-session S=ID) — перед постановкой ✅:
  - в файле сессии нет незакрытых чекбоксов «- [ ]» (Предусловия/Задачи/Критерии);
  - статус шапки файла согласован с таблицей/архивом: ✅ ⇔ «Статус: [x]» в файле.

Пустая таблица (без строк) — валидный стартовый случай. Файлы с именем вне
паттерна *_session.md (например _template.md) игнорируются.

Только stdlib. Любое нарушение — exit 1.
"""
import argparse
import re
import sys
from pathlib import Path

# Консоль Windows (cp866/cp1251 при пайпе): форсируем UTF-8, иначе кириллица ломается
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[2]   # harness/scripts/ → корень проекта
DOCS = REPO / 'docs'
INDEX = DOCS / 'sessions.md'
ARCHIVE = DOCS / 'sessions-archive.md'
SESSIONS_DIR = DOCS / 'sessions'
ACTIVE, DONE = '◐', '✅'
ID_RE = re.compile(r'[A-Z]\d{2}')            # любая латинская буква = трек, две цифры
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
LINK_RE = re.compile(r'\]\(([^)]+)\)')
CHECKBOX_RE = re.compile(r'^\s*-\s\[\s\]', re.M)


def parse_rows(path: Path) -> dict[str, tuple[Path | None, str]]:
    """{ID: (путь файла сессии, ячейка статуса)} из markdown-таблицы сессий."""
    rows: dict[str, tuple[Path | None, str]] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.split('|')]
        cells = cells[1:-1] if cells and cells[0] == '' else cells
        if len(cells) < 3 or not ID_RE.fullmatch(cells[0]):
            continue
        link = LINK_RE.search(cells[1])
        session_path = DOCS / link.group(1) if link else None
        rows[cells[0]] = (session_path, cells[-1])
    return rows


def parse_index() -> dict[str, tuple[Path | None, str]]:
    """{ID: (путь файла сессии, ячейка статуса)} из таблицы sessions.md."""
    return parse_rows(INDEX)


def audit(rows: dict[str, tuple[Path | None, str]]) -> list[str]:
    problems: list[str] = []
    wip: dict[str, list[str]] = {}
    for sid, (_, status) in sorted(rows.items()):
        track = sid[0]
        if ACTIVE in status:
            wip.setdefault(track, []).append(sid)
        if DONE in status and not DATE_RE.search(status):
            problems.append(f'{sid}: ✅ в таблице без даты — добавь дату закрытия')
    for track, ids in sorted(wip.items()):
        if len(ids) > 1:
            problems.append(f'WIP={len(ids)} на треке {track}: {", ".join(ids)} — '
                            'одновременно может быть в работе только одна сессия (WIP=1)')
    return problems


def audit_archive(index_ids: set[str]) -> list[str]:
    """Инварианты архива sessions-archive.md: только ✅ с датой, без дублей
    основной таблицы (перенос закрытых строк — harness/scripts/session_archive.py)."""
    if not ARCHIVE.is_file():
        return []
    problems: list[str] = []
    for sid, (_, status) in sorted(parse_rows(ARCHIVE).items()):
        if sid in index_ids:
            problems.append(f'{sid}: строка и в таблице, и в архиве — оставь в одном месте')
        elif ACTIVE in status:
            problems.append(f'{sid}: ◐ в архиве — архив только для закрытых сессий')
        elif DONE not in status:
            problems.append(f'{sid}: в архиве не закрытая строка ({status or "—"}) — архив только для ✅')
        elif not DATE_RE.search(status):
            problems.append(f'{sid}: ✅ в архиве без даты — добавь дату закрытия')
    return problems


def gate(sid: str, rows: dict[str, tuple[Path | None, str]],
         archive_rows: dict[str, tuple[Path | None, str]]) -> list[str]:
    if sid in rows:
        path, status = rows[sid]
        where = 'таблице docs/sessions.md'
    elif sid in archive_rows:
        path, status = archive_rows[sid]
        where = 'архиве docs/sessions-archive.md'
    else:
        return [f'{sid}: нет ни в таблице docs/sessions.md, ни в архиве']
    if path is None or not path.is_file():
        return [f'{sid}: файл сессии не найден по ссылке из {where}']
    problems: list[str] = []
    text = path.read_text(encoding='utf-8')
    open_boxes = [f'{i + 1}: {ln.strip()}'
                  for i, ln in enumerate(text.splitlines()) if CHECKBOX_RE.match(ln)]
    if open_boxes:
        problems.append(f'незакрытые чекбоксы ({len(open_boxes)}) — правило №1: '
                        '[x] ставится только по факту:\n  ' + '\n  '.join(open_boxes))
    header = next((ln for ln in text.splitlines()[:6] if 'Статус:' in ln), '')
    file_done = '[x]' in header
    table_done = DONE in status
    if file_done != table_done:
        problems.append(
            f'статусы расходятся: таблица/архив = {status or "—"}, файл = {header.split("Статус:")[-1].strip()}'
            ' — приведи шапку файла и таблицу в соответствие')
    return problems


def audit_orphans(index_ids: set[str], archive_ids: set[str]) -> list[str]:
    """Файл docs/sessions/*_session.md, не внесённый ни в таблицу, ни в архив,
    — гард молча пропускал (audit() обходит только строки таблицы).
    Регистрация сессии в docs/sessions.md — правило №1: состояние фич живёт в индексе."""
    known = index_ids | archive_ids
    problems: list[str] = []
    for path in sorted(SESSIONS_DIR.glob('*_session.md')):
        sid = path.stem.split('_')[0]
        if not ID_RE.fullmatch(sid):
            continue
        if sid not in known:
            problems.append(
                f'{sid}: файл {path.name} не внесён ни в таблицу docs/sessions.md, '
                'ни в архив — зарегистрируй сессию (⬜/◐ в таблице, ✅ строка — '
                'в архив через session_archive.py)')
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--session', help='гейт закрытия сессии, например X01')
    args = parser.parse_args()

    if not INDEX.is_file():
        print(f'FAIL: нет {INDEX.relative_to(REPO)} — возьми шаблон '
              f'harness/templates/sessions.md (bash harness/scripts/init-harness.sh)')
        return 1
    rows = parse_index()
    if args.session:
        archive_rows = parse_rows(ARCHIVE) if ARCHIVE.is_file() else {}
        problems = gate(args.session, rows, archive_rows)
        title = f'Гейт {args.session}'
    else:
        archive_ids = set(parse_rows(ARCHIVE)) if ARCHIVE.is_file() else set()
        problems = audit(rows) + audit_archive(set(rows)) + audit_orphans(set(rows), archive_ids)
        title = 'Аудит сессий'

    if problems:
        print(f'{title}: FAIL')
        for problem in problems:
            print(f'  - {problem}')
        return 1
    print(f'{title} ({len(rows)} сессий в таблице): PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
