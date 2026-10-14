# Makefile — единый интерфейс для любого AI-агента (abap_bench_internal).
# Канонический домен этого Makefile — корень проекта (копия — harness/Makefile,
# bash harness/scripts/init-harness.sh кладёт её в корень, если там ещё нет своего Makefile).
#
# Специфика проекта: локального SAP-рантайма нет; ABAP-код появится в src/ как
# выгрузка abapGit (FOLDER_LOGIC=FULL) — гейт по нему abaplint (abaplint.json,
# syntax.version v754 = NW 7.54, ADR-003). Задачи бенчмарка (tasks/*.task.txt) —
# не ABAP, их гейт — check_tasks.py (формат + дословность PROMPT). Всё, что
# требует SAP-системы (создание ZLLBM_*-объектов, активация, импорт, прогон),
# фиксируется в отчёте сессии как «проверить в системе». Скрипты гейтов живут
# единственной копией в harness/scripts/ — не копируй их.

PY ?= python
HARNESS_SCRIPTS := harness/scripts

.PHONY: setup lint lint-all check-tasks check check-sessions verify-session session-archive backlog-archive build-tasks help

## setup: Установка Node-зависимостей линтера (@abaplint/cli) — один раз
setup:
	npm install

## lint: Гейт — abaplint с гейт-конфигом abaplint.json (блокирующий; без файлов в src/ — пропуск)
lint:
	@if find src -type f -print -quit 2>/dev/null | grep -q .; then \
		npx abaplint; \
	else \
		echo "lint: no files in src/ - nothing to check (gate skipped)"; \
	fi

## lint-all: Широкий линт (abaplint-all.json: стилистика/нейминг) — только репорт, не блокирует
lint-all:
	@if find src -type f -print -quit 2>/dev/null | grep -q .; then \
		-@npx abaplint -c abaplint-all.json; \
	else \
		echo "lint-all: no files in src/ - report skipped"; \
	fi

## check-tasks: Гейт формата задач tasks/*.task.txt (мета, секции, контракт, дословность PROMPT)
check-tasks:
	$(PY) $(HARNESS_SCRIPTS)/check_tasks.py

## check: Полная проверка (lint-гейт + гейт задач + машинные гейты харнесса)
check: lint check-tasks
	$(PY) $(HARNESS_SCRIPTS)/check_sessions.py
	$(PY) $(HARNESS_SCRIPTS)/backlog_archive.py --check
	$(PY) $(HARNESS_SCRIPTS)/session_archive.py --check

## check-sessions: Аудит сессий без полного check
check-sessions:
	$(PY) $(HARNESS_SCRIPTS)/check_sessions.py

## verify-session: Гейт закрытия сессии — lint + задачи + чекбоксы/статусы (make verify-session S=M01)
# рецепт lint продублирован: $(MAKE) не переносит путь GnuWin32 с пробелами/скобками
verify-session:
	@if [ -z "$(S)" ]; then echo "Usage: make verify-session S=M01"; exit 1; fi
	@if find src -type f -print -quit 2>/dev/null | grep -q .; then \
		npx abaplint; \
	else \
		echo "lint: no files in src/ - nothing to check (gate skipped)"; \
	fi
	$(PY) $(HARNESS_SCRIPTS)/check_tasks.py
	$(PY) $(HARNESS_SCRIPTS)/check_sessions.py --session $(S)

## session-archive: Перенос ✅-строк сессий в архив (make session-archive ARGS="--dry-run")
session-archive:
	$(PY) $(HARNESS_SCRIPTS)/session_archive.py $(ARGS)

## backlog-archive: Перенос закрытых элементов беклога в архив (make backlog-archive ARGS="--dry-run")
backlog-archive:
	$(PY) $(HARNESS_SCRIPTS)/backlog_archive.py $(ARGS)

## build-tasks: Перегенерация задач из исходного датасета (tools/build_tasks.py)
build-tasks:
	$(PY) tools/build_tasks.py

## help: Показать все таргеты
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## //'

# Default target
.DEFAULT_GOAL := help
