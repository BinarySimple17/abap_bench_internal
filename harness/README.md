# Harness — агентная инфраструктура проекта (abap_bench_internal)

Папка — развёрнутый экземпляр портативного харнесса для AI-агентов
(источник — `F:/JAVA/zvvvv-abab-vectors/harness/`; адаптации описаны в
[ADR-001](../docs/adr/ADR-001-agent-harness.md),
[ADR-002](../docs/adr/ADR-002-abaplint-gate.md),
[ADR-003](../docs/adr/ADR-003-nw-754.md)). Agent-agnostic: работает с
любым CLI-агентом — ядро (`AGENTS.md` в корне + `Makefile`) от инструмента не
зависит. Точка входа агента — `AGENTS.md` в корне репозитория.

## Состав комплекта

| Файл | Назначение |
|---|---|
| `Makefile` | канонический Makefile харнесса; копия — в корне проекта (init кладёт её, только если корневого ещё нет) |
| `scripts/check_tasks.py` | гейт формата задач `tasks/*.task.txt`: мета, секции, контракт `lcl_solution`, уникальность `@id`, дословность PROMPT по датасету |
| `scripts/check_sessions.py` | фиче-дисциплина (WIP=1, статусы, даты) + гейт закрытия сессии (`--session ID`) |
| `scripts/session_archive.py` | перенос ✅-строк сессий в архив + Mermaid-диаграмма «История» |
| `scripts/backlog_archive.py` | гигиена беклога: перенос закрытых элементов в архив, двусторонняя сверка «файлы ↔ карты ↔ архив» |
| `scripts/init-harness.sh` | идемпотентная развёртка шаблонов в проект (AGENTS.md не трогает — точка входа у проекта своя) |
| `templates/sessions.md` | шаблон `docs/sessions.md`: «Текущее состояние» + «История» + таблица сессий |
| `templates/session-template.md` | каркас файла сессии (→ `docs/sessions/_template.md`) |
| `templates/adr/README.md`, `templates/adr/ADR-template.md` | правила ADR + реестр и каркас ADR (→ `docs/adr/`) |
| `templates/backlog/README.md`, `templates/backlog/archive.md` | беклог и его архив (→ `backlog/`) |

Скрипты гейтов живут **единственной копией** в `harness/scripts/` — в корень не
копируются, вызываются через make-таргеты.

## Команды

```bash
make check                  # lint-гейт + гейт задач + машинные гейты харнесса — репозиторий консистентен
make lint                   # только abaplint-гейт (abaplint.json)
make lint-all               # широкий линт (abaplint-all.json) — репорт, не блокирует
make check-tasks            # только гейт формата задач
make check-sessions         # аудит сессий без полного check
make verify-session S=M01   # гейт закрытия сессии
make session-archive        # перенос ✅-строк сессий в архив (ARGS="--dry-run")
make backlog-archive        # перенос закрытых элементов беклога (ARGS="--dry-run")
make build-tasks            # перегенерация задач из исходного датасета
make setup                  # npm install (@abaplint/cli) — один раз
```

Зависимости: python stdlib (гейты, `PY` переопределяется) и `@abaplint/cli`
(только локальная верификация ABAP, `make setup`).

## Машинные гейты

### `make lint` / `make lint-all` — abaplint (ABAP в `src/`)

Конфиги перенесены у zvvvv-abab-vectors дословно; `syntax.version = v754` —
целевой релиз NW 7.54 ([ADR-003](../docs/adr/ADR-003-nw-754.md)). `abaplint.json`
— блокирующий гейт (parser, семантика, `xml_consistency`, naming), входит в
`make check` и `make verify-session`; `abaplint-all.json` — широкий репорт
(все правила по умолчанию, не блокирует). Пока в `src/` нет файлов, гейт
пропускается с сообщением — abaplint падает с «No files found» на пустой
папке, а baseline должен оставаться зелёным до первой выгрузки abapGit.
Ограничение: abaplint не отсекает все конструкции 7.55+ (проверено: `FINAL(...)`
не ловится) и не знает DDIC целевой системы — авторитетная верификация только
в SAP ([ADR-002](../docs/adr/ADR-002-abaplint-gate.md)).

### `check_tasks.py` — формат задач (`make check-tasks`)

Для каждого `tasks/*.task.txt` (формат — PLAN.md §4.1): `@id` = имени файла;
обязательные мета-строки (`@id`, `@source`, `@method`, `@category`, `@active`);
`@active ∈ {true,false}`; `@method` — snake_case-имя ABAP-метода; `---PROMPT---`
непуста, опциональные `---CANONICAL---`/`---TEST---` непусты; в CANONICAL класс
переименован в `lcl_solution`; в TEST вызовы переписаны на `lcl_solution=>`.
`@id` уникальны по папке. Если доступен исходный датасет (`--source`, дефолт
`F:/JAVA/LLM-Benchmark-ABAP-Code-Generation-main`) — PROMPT сверяется дословно
(промпты дословны — PLAN.md §3); нет датасета — сверка пропускается с пометкой.

### `check_sessions.py` — фиче-дисциплина (`make check-sessions`)

- WIP=1: не более одной ◐ на трек (первая буква ID `[A-Z]\d{2}`) в таблице `docs/sessions.md`;
- каждый ✅ в таблице — с датой ГГГГ-ММ-ДД;
- архив `docs/sessions-archive.md` (если есть): только ✅ с датой, без дублей таблицы;
- файл `docs/sessions/*_session.md`, не внесённый ни в таблицу, ни в архив — orphan = FAIL;
- пустая таблица — валидный старт; `_template.md` игнорируется.

Гейт закрытия `--session ID` (`make verify-session S=ID`): в файле сессии нет
незакрытых чекбоксов `- [ ]`; шапка (`Статус:` в первых 6 строках, маркер `[x]`)
согласована со статусом в таблице/архиве. Любое нарушение — exit 1.

### `session_archive.py` / `backlog_archive.py` — архивы

- перенос ✅-строк из `docs/sessions.md` в `docs/sessions-archive.md` дословно
  (дедуп, сортировка) + узлы в Mermaid «История» (субграф дня, ≤ 8 узлов в ряду,
  цвет = класс трека); `--dry-run` — план без правок; `--check` — exit 1, если
  в основной таблице остались ✅-строки или архив невалиден; идемпотентен;
- беклог: перенос закрытых элементов из `backlog/README.md` в `backlog/archive.md`;
  `--check` — счётчик «Последний занятый номер» = max по README+архиву, orphan,
  missing-file, дубли «карта + архив»; пустой беклог (BL-0) — валидный старт.

## Уровни: коммитимое и личное

**Коммитится (shared):** `AGENTS.md`, `Makefile`, `docs/sessions.md`,
`docs/sessions/`, `docs/sessions-archive.md`, `docs/adr/`, `backlog/`, `harness/`.

**Личное (в .gitignore):** `session-progress.md`, `session-handoff.md`,
`.agent/`, `.zcode/` — локальные логи и настройки конкретного агента.

## Git-модель (отличие от исходного харнесса)

По решению владельца ([ADR-001](../docs/adr/ADR-001-agent-harness.md)) **веточная
дисциплина исключена**: агент не создаёт, не переключает и не мержит ветки —
работа ведётся в текущей ветке репозитория; ветку при необходимости называет сам
владелец. Коммиты — на задачу/логическую группу с WHY-сообщениями; push — только
по явному запросу владельца. Мержи, `push --force`, `reset --hard`, rebase,
cherry-pick — запрещены агенту.

## Отличия от исходника (zvvvv-abab-vectors)

- **Без веточной модели** — см. выше (решение владельца, [ADR-001](../docs/adr/ADR-001-agent-harness.md)).
- **`check_tasks.py` добавлен**: задачи бенчмарка — текстовый формат, не ABAP;
  их проверяет свой гейт (формат + дословность промптов по датасету).
- **Lint-таргеты с пропуском на пустом `src/`** — иначе baseline красный до
  первой выгрузки abapGit (см. раздел abaplint выше).
- **`AGENTS.md` не шаблонизируется**: точка входа своя, init-скрипт её не трогает.
- abaplint-конфиги, шаблоны сессий/ADR/беклога, архивная механика — дословно
  из исходника; `syntax.version` = наш целевой релиз v754 (ADR-003).

## Чек-лист: harness настроен правильно

- [x] `AGENTS.md` в корне: описание проекта, приоритет источников, Clock-In/Clock-Out
- [x] `Makefile` в корне: `check`, `check-tasks`, `verify-session`, `check-sessions`, `session-archive`, `backlog-archive`, `help`
- [x] `docs/sessions.md`: «Текущее состояние», «История», владельцы треков, таблица сессий с легендой
- [x] `docs/sessions/_template.md` на месте; файлы сессий — `<ID>_session.md`
- [x] `docs/adr/`: README с реестром + `_template.md`
- [x] `backlog/README.md` + `backlog/archive.md`: счётчик BL-N, карта, указатель на архив
- [x] `make check` зелёный (lint + python-гейты) — репозиторий консистентен
- [x] `make verify-session S=<ID>` проходил на реальной сессии (будет на M01)
- [x] `.gitignore`: личные файлы агента
- [x] WIP=1, фиче-дисциплина ⬜→◐→✅ и WHY-коммиты прописаны в `AGENTS.md`
- [x] Git-модель «без веток» прописана в `AGENTS.md` и ADR-001
