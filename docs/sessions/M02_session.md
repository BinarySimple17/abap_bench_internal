# M02 — Парсер задач ZCL_AI_TASKS + отчёт импорта ZAI_IMPORT_TASKS

Этап: Фаза 1 (ADR-006), задачи | Владелец: M | Зависимости: M01 | Оценка: — | Статус: [x] ✅ (2026-10-14)

## ⚠️ Прочитай перед началом

> Написать офлайн в `src/`: класс `ZCL_AI_TASKS` — парсер формата
> `*.task.txt` (PLAN.md §4.1) и импорт в `ZTAI_TASK` (upsert, `task_version`,
> `TASKSET_HASH`), и отчёт `ZAI_IMPORT_TASKS` (диалоговый выбор файла +
> фоновый режим по каталогу). Сквозная проверка импорта — M07; локально —
> lint. Семантика формата — как у гейта `harness/scripts/check_tasks.py`
> (валидация мета/секций), не копируй код — Python-гейт остаётся гейтом
> репозитория, ABAP-парсер — рабочим кодом системы.

### Правила для исполнителя

1. Класс — уровень 7.54, без синтаксиса 7.55+; имена по PLAN.md §10.
2. Парсер — детерминированный, без зависимостей от селекционного экрана:
   чистый метод `parse( iv_raw ) → structure + errors`, поверх — импорт.
3. Файлы задач (`tasks/*.task.txt`) не менять; `make check-tasks` зелёный.
4. `make lint` зелёный; никаких заявлений о системной проверке.

## Предусловия

- [x] M01 закрыта: `ZTAI_TASK` в `src/` (зависимость полей)
- [x] `make check` зелёный на старте

## Задачи

### Task 1: `ZCL_AI_TASKS` — парсер формата §4.1

Парсер: мета-строки `@id/@source/@method/@category/@active` до первого
`---PROMPT---`; секции `---PROMPT---` (обязательна), `---CANONICAL---`,
`---TEST---` до следующего маркера/конца. Результат — структура
(ключи §4.2: `TASK_ID`, `METHOD_NAME`, `CATEGORY`, `ACTIVE`, `SOURCE_INFO`,
`PROMPT`, `CANONICAL`, `TEST_SOURCE`) + список ошибок валидации (пустой
PROMPT, нет мета, кривой `@active`).

**✅ Самопроверка:** `parse` возвращает и мета, и секции для всех 10 файлов из
`tasks/` — прогнать глазами по 2–3 файлам при код-ревью (реальный прогон — M07);
`make lint` зелёный.

---

### Task 2: Импорт — upsert + `task_version` + `TASKSET_HASH`

Импорт по `@id`: строки нет → INSERT; есть и содержание (PROMPT/CANONICAL/TEST/
мета) отличается → UPDATE + `task_version + 1`; идентично → без изменений.
После импорта пересчитать `TASKSET_HASH` = хэш отсортированного списка
`id + task_version` **активных** задач (детерминизм: сортировка по `TASK_ID`,
хэш — SHA через `CL_ABAP_MESSAGE_DIGEST`/`CALCULATE_HASH_FOR_CHAR`,
конкретика — на твой выбор, зафиксируй в комментарии и отчёте). Хэш пишет
движок в `ZTAI_RUN` на старте прогона (потребление — M05).

**✅ Самопроверка:** код upsert и хэша в `src/`; комментарий про выбранный
алгоритм хэша; `make lint` зелёный.

---

### Task 3: Отчёт `ZAI_IMPORT_TASKS`

Селекционный экран: радиус «диалог/фон»; диалог — чтение файла с фронта
(`cl_gui_frontend_services=>gui_upload` в bin + конвертация UTF-8 через
`cl_abap_conv_in_ce`, без BOM-остатка), фон — каталог на сервере приложений
(`OPEN DATASET ... FOR INPUT IN BINARY MODE`, тот же конвертер), файлы
`*.task.txt` по маске. Итог — ALV/список: задача → вставлен/обновлён/пропущен
+ ошибки парсинга.

**✅ Самопроверка:** `.prog.abap` + `.prog.xml` в `src/`; оба режима в коде;
`make lint` зелёный.

---

## Критерии приёмки

- [x] `ZCL_AI_TASKS` и `ZAI_IMPORT_TASKS` в `src/`, `make lint`/`make check` зелёные
- [x] Логика upsert/version/hash объяснена в отчёте (алгоритм хэша зафиксирован)
- [x] «Проверить на M07»: импорт 10 задач, повторный импорт без изменений не инкрементит version, правка файла + реимпорт инкрементит

## Ловушки

1. UTF-8/BOM/CRLF: `gui_upload` — только bin + `cl_abap_conv_in_ce`; маркеры
   секций сравнивать после обрезки CR; BOM `EF BB BF` в начале — срезать.
2. `TASKSET_HASH` держит сравнимость трендов (PLAN.md §4.1) — никаких
   таймстампов/рандомных компонентов в хэше.
3. STRING-поля `ZTAI_TASK` — LOB: в SELECT помечать согласно 7.54-правилам
   ( lobbing handle — при UPDATE через структуру ок; не клади LOB в ключ WHERE
   динамически).
4. Не исполняй загруженный код задач — это только данные (фаза 1, PLAN.md §5).

## Отчёт по сессии (заполняется по факту)

- Сделано по Task'ам:
  - **Task 1:** `ZCL_AI_TASKS` — статический `parse( iv_raw ) → ts_task +
    tt_errors`: нормализация CRLF→LF, мета-блок `@ключ: значение` до первого
    маркера (SPLIT по первому ':', остаток — в значение), секции
    `---PROMPT---`/`---CANONICAL---`/`---TEST---` хранятся дословно, трейлинг
    LF срезается. Валидация обязательного — как в гейте check_tasks.py
    (id/active/method/source/category + непустой PROMPT). Глазами прогнан
    `humaneval_013.task.txt` (трассировка построчно — в отчёте сессии);
    остальные 9 — тот же формат конвертера + гейт.
  - **Task 2:** `import_task` — SELECT SINGLE → INSERT (version=1,
    created_by/at) / UPDATE (version+1, changed_by/at) / без записи;
    сравнение полей — `fields_differ` (PROMPT/CANONICAL/TEST_SOURCE/
    METHOD_NAME/CATEGORY/SOURCE_INFO/ACTIVE). `calc_taskset_hash` — MD5
    (FM `CALCULATE_HASH_FOR_CHAR`) по строкам `id:version` активных задач,
    сортировка по TASK_ID, разделитель LF; алгоритм зафиксирован в
    комментарии метода (менять без решения нельзя — тренды).
  - **Task 3:** отчёт `ZAI_IMPORT_TASKS`: фронт — `gui_upload` BIN →
    склейка xstring → обрезка по filelength → срез BOM EF BB BF →
    `cl_abap_codepage=>convert_from` (UTF-8); сервер —
    `EPS2_GET_DIRECTORY_LISTING` + `READ DATASET ... INTO xstring`
    (бинарно, файл целиком) + тот же конвертер. Итог — ALV
    (task_id/action/version/message) + WRITE TASKSET_HASH.
- Отклонения от плана: UTF-8-декодирование через `cl_abap_codepage` вместо
  `cl_abap_conv_in_ce` (та же семантика, меньше параметров); хэш — FM
  `CALCULATE_HASH_FOR_CHAR`/MD5 (API `CL_ABAP_MESSAGE_DIGEST` в офлайне
  не проверяем; FM-вызов статический — существование параметров проверит
  M07). `active` хранится 'X'/'' — true/false из файла конвертируются.
- Перенесено в другие сессии: —
- Верификация: `make lint` 0 issues / 14 files; `make check` зелёный;
  `make verify-session S=M02` PASS.
- Проверить на M07: (a) импорт 10 файлов диалогом; (b) повторный импорт —
  все UNCHANGED, version не растёт; (c) правка файла + реимпорт — UPDATED,
  version+1; (d) TASKSET_HASH стабилен между идентичными импортами;
  (e) существование FM `CALCULATE_HASH_FOR_CHAR` и таблицы `EPS2FILI`.
