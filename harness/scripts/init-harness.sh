#!/usr/bin/env bash
# init-harness.sh — развёртка harness в проекте
# Копирует шаблоны из harness/templates в корень проекта, создаёт папки,
# дополняет .gitignore. Идемпотентен: существующие файлы не перезаписывает (SKIP).
# AGENTS.md не копируется: точка входа агента у проекта своя — в корне.
#
# Скрипты гейтов в scripts/ корня НЕ копируются: единственная копия живёт
# в harness/scripts/ и вызывается через make-таргеты (см. Makefile).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="$(cd "$SCRIPT_DIR/../templates" && pwd)"
MAKEFILE_SRC="$(cd "$SCRIPT_DIR/.." && pwd)/Makefile"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Harness Init ==="
echo "Project root: $PROJECT_ROOT"
echo "Templates:    $TEMPLATES_DIR"
echo ""

copy_template() {
  local src="$TEMPLATES_DIR/$1"
  local dst="$PROJECT_ROOT/$2"
  if [ ! -f "$src" ]; then
    echo "  WARN: шаблон не найден: $1"
  elif [ -f "$dst" ]; then
    echo "  SKIP (exists): $2"
  else
    cp "$src" "$dst"
    echo "  COPY: $2"
  fi
}

# 1. Папки
echo "--- Directories ---"
for dir in docs/sessions docs/adr backlog/items; do
  if [ ! -d "$PROJECT_ROOT/$dir" ]; then
    mkdir -p "$PROJECT_ROOT/$dir"
    echo "  MKDIR: $dir/"
  else
    echo "  SKIP (exists): $dir/"
  fi
done

# 2. Документы (только если не существуют)
echo ""
echo "--- Docs ---"
copy_template "sessions.md"          "docs/sessions.md"
copy_template "session-template.md"  "docs/sessions/_template.md"
copy_template "adr/README.md"        "docs/adr/README.md"
copy_template "adr/ADR-template.md"  "docs/adr/_template.md"
copy_template "backlog/README.md"    "backlog/README.md"
copy_template "backlog/archive.md"   "backlog/archive.md"

# 3. Makefile
echo ""
echo "--- Makefile ---"
if [ -f "$MAKEFILE_SRC" ] && [ ! -f "$PROJECT_ROOT/Makefile" ]; then
  cp "$MAKEFILE_SRC" "$PROJECT_ROOT/Makefile"
  echo "  COPY: Makefile"
elif [ -f "$PROJECT_ROOT/Makefile" ]; then
  echo "  SKIP (exists): Makefile (объедини вручную: таргеты харнесса — check-tasks/check/verify-session/check-sessions/session-archive/backlog-archive/build-tasks)"
else
  echo "  WARN: Makefile не найден в harness/"
fi

# 4. .gitignore
echo ""
echo "--- .gitignore ---"
GITIGNORE="$PROJECT_ROOT/.gitignore"
ENTRIES=(
  "session-progress.md"
  "session-handoff.md"
  ".agent/"
  ".zcode/"
  "__pycache__/"
  "*.pyc"
)
if [ ! -f "$GITIGNORE" ]; then
  printf "%s\n" "${ENTRIES[@]}" > "$GITIGNORE"
  echo "  CREATE: .gitignore"
else
  for entry in "${ENTRIES[@]}"; do
    if ! grep -qxF "$entry" "$GITIGNORE" 2>/dev/null; then
      echo "$entry" >> "$GITIGNORE"
      echo "  APPEND: $entry"
    else
      echo "  SKIP (exists): $entry"
    fi
  done
fi

# 5. Скрипты харнесса
echo ""
echo "--- Harness scripts ---"
echo "  Скрипты гейтов в scripts/ корня НЕ копируются — единственная копия живёт в harness/scripts/:"
echo "    check_tasks.py (формат задач tasks/*.task.txt + дословность PROMPT по датасету)"
echo "    check_sessions.py (фиче-дисциплина + гейт закрытия сессии)"
echo "    session_archive.py (перенос ✅-строк в архив + диаграмма «История»)"
echo "    backlog_archive.py (гигиена беклога)"
echo "  Вызов — через make-таргеты: check / check-tasks / verify-session / session-archive / backlog-archive."

echo ""
echo "=== Harness init complete ==="
echo ""
echo "Next steps:"
echo "  1. AGENTS.md в корне — точка входа агента: сверяй рутины (Verification, Clock-In/Clock-Out)"
echo "  2. Треки и сессии — в docs/sessions.md (формат строки — в файле)"
echo "  3. make check"
