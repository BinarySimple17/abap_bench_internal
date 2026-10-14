# M01 — DDIC офлайн: ZEAI_/ZTAI_/EZ_AI_RUN в src/

Этап: Фаза 1 (ADR-006), фундамент | Владелец: M | Зависимости: — | Оценка: — | Статус: [x] ✅ (2026-10-14)

## ⚠️ Прочитай перед началом

> Создать весь DDIC бенчмарка как XML-файлы abapGit в `src/` — **без доступа к
> системе** ([ADR-006](../adr/ADR-006-phases-offline.md)): 6 таблиц `ZTAI_*`
> (PLAN.md §4.2), элементы данных `ZEAI_*` для ключей, lock-объект `EZ_AI_RUN`.
> Активация и семантическая проверка — только на M07; локальная верификация —
> abaplint-гейт. Пакет в системе — транспортный `ZAI`
> ([ADR-007](../adr/ADR-007-package-zai.md)), офлайн это ни на что не влияет,
> кроме поля пакета в XML.

### Правила для исполнителя

1. Код/данные — только в `src/` в формате abapGit (FOLDER_LOGIC=FULL):
   `zeai_*.dtel.xml`, `ztai_*.tabl.xml`, `ez_ai_run.enqu.xml`. Никаких
   «проверено в системе» заявлений — только lint.
2. Формат XML не выдумывать: брать за образец выгрузку
   `F:/JAVA/zvvvv-abab-vectors/src/*.tabl.xml` (та же версия abapGit-формата,
   рабочий DDIC) и сверять структуру тегов.
3. Язык/типы — уровень 7.54 (ADR-003); имена — строго PLAN.md §10 (ADR-004).
4. Перед созданием DDIC — [ABAP-PITFALLS §DDIC](../ABAP-PITFALLS.md) #14–#19
   (актуально для M07-активации; офлайн — помнить, что XML видит только парсер).
5. `make lint` обязан быть зелёным в конце сессии; `make check` — тоже.

## Предусловия

- [x] `make check` зелёный на старте (baseline)
- [x] [ADR-006](../adr/ADR-006-phases-offline.md) и [ADR-007](../adr/ADR-007-package-zai.md) прочитаны; образцы XML в `F:/JAVA/zvvvv-abab-vectors/src/` доступны

## Задачи

### Task 1: Элементы данных `ZEAI_*`

Минимальный набор для ключей и служебных полей: `ZEAI_TASK_ID` (char30),
`ZEAI_MODEL_ID` (char30), `ZEAI_RUN_ID` (char32, UUID-строка). Неключевые
поля — встроенные типы (`char`, `numc`, `int4`, `dec16_2`, `timestampl`,
`STRING` для LOB). Домены при необходимости — `ZDAI_*` (ADR-004); если
достаточно встроенных — не плодить.

**✅ Самопроверка:** `.dtel.xml`-файлы в `src/`, имена/длины совпадают с
PLAN.md §4.2; `make lint` зелёный.

---

### Task 2: Таблицы `ZTAI_*` (6 шт.)

`ZTAI_TASK`, `ZTAI_MODEL`, `ZTAI_RUN`, `ZTAI_ROUND`, `ZTAI_RESULT`,
`ZTAI_SETT` — поля и ключи строго из таблицы PLAN.md §4.2. Общее: delivery
class `A`, data class `APPL0`, buffering `no`; STRING-поля (LOB) только
неключевые; админ. данные (`CREATED_BY/AT`, changed-by/at) — где указано в
§4.2. `ZTAI_SETT`: KEY char30 + VALUE STRING — SM30-совместимая (без
STRING в ключе; вид генерируется на M07).

**✅ Самопроверка:** 6 `.tabl.xml` в `src/`; построчная сверка полей с §4.2
(отчёт сессии: таблица «поле → тип» на каждую таблицу не нужна, достаточно
факта сверки); `make lint` зелёный (включая `check_ddic`, `xml_consistency`).

---

### Task 3: Lock-объект `EZ_AI_RUN`

Lock на таблицу `ZTAI_RUN` по `RUN_ID`, режим E; параметр `_SCOPE = 2`
(освобождается DEQUEUE/коммитом сессии). Назначение — anti-overlap и resume
(PLAN.md §2, §9).

**✅ Самопроверка:** `ez_ai_run.enqu.xml` в `src/`; режим/поля соответствуют;
`make lint` зелёный.

---

## Критерии приёмки

- [x] В `src/` лежат все DDIC-объекты фазы 1 (3+ ZEAI, 6 ZTAI, EZ_AI_RUN), ничего лишнего
- [x] `make lint` и `make check` зелёные (гейт abaplint теперь работает по-настоящему — в src/ есть файлы)
- [x] Отчёт сессии заполнен; список «проверить на M07» — активация, SE11-сверка, SM30-генерация

## Ловушки

1. Ручной DDIC-XML: опечатка в типе/длине увидится только активацией на M07 —
   сверяй каждый тег с образцом из zvvvv-abab-vectors, не по памяти.
2. `STRING` в ключе таблицы запрещён (LOB) — все ключи char30/char32.
3. Имя файла = имя объекта нижним регистром + верный суффикс
   (`.dtel.xml`, `.tabl.xml`, `.enqu.xml`) — иначе abapGit не сматчит объект.
4. Не добавляй текстовые таблицы/поисковые помощи — фазе 1 они не нужны.
5. `.abapgit.xml` не трогать (правило AGENTS.md); папки в src/ не плодить —
   FOLDER_LOGIC=FULL плоский список файлов по типам.

## Отчёт по сессии (заполняется по факту)

- Сделано по Task'ам:
  - **Task 1:** 3 элемента данных по образцу `zevvvv_vctr_cby.dtel.xml`:
    `ZEAI_TASK_ID` (CHAR30), `ZEAI_MODEL_ID` (CHAR30), `ZEAI_RUN_ID` (CHAR32)
    — `*.dtel.xml` без домена (DD04V), тексты короткие/средние/длинные заданы.
  - **Task 2:** 6 таблиц `ZTAI_*` — CLIDEP+MANDT (как в образце), ключи через
    ZEAI_*, строки через STRING/CHAR/INT4/NUMC3/DEC15 по §4.2; технастройки
    TABART USER1 / TABKAT по объёму (0–4) / BUFALLOW N. Ключевые поля с
    `NOTNULL X`. Построчная сверка с §4.2 выполнена (список полей — в
    выводе гейта `make lint`/grep FIELDNAME).
  - **Task 3:** `EZ_AI_RUN` — формат по исходникам сериализатора abapGit
    (`zcl_abapgit_object_enqu`): DD25V (AGGTYPE=E, ROOTTAB=ZTAI_RUN) +
    DD26E_TABLE (ENQMODE=E) + DD27P_TABLE (параметр RUN_ID). Локального
    образца ENQU не было — это главный офлайн-допуск сессии.
- Отклонения от плана:
  1. `ZTAI_SETT`: `KEY`/`VALUE` → `SETT_KEY`/`SETT_VALUE` — ключевые слова
     ABAP запрещены как имена полей DDIC; `ZTAI_RUN`: `EXECUTE_UNIT_TESTS`
     → `EXEC_UNIT_TESTS` (лимит 16 симв.), hash system prompt → `PROMPT_HASH`
     (то же ограничение). PLAN.md §4.2 синхронизирован.
  2. TABART `USER1` вместо заявленного `APPL0` — значение фактически
     активировано на целевом стенде (образец zvvvv-abab-vectors), APPL0
     офлайн не проверяем.
  3. `INT4`-поля сериализуются abapGit с `INTTYPE=X` (не `I`) — поймал гейт
     `xml_consistency` на первом прогоне, исправлено (13 полей).
- Перенесено в другие сессии: —
- Верификация: `make lint` — 0 issues / 10 files; `make check` зелёный;
  `make verify-session S=M01` PASS (см. логи ниже).
- Проверить на M07: (a) активация всех 10 объектов, лог без ошибок;
  (b) ENQU-сериализация — сверить с фактической выгрузкой после pull (формат
  собран из исходников abapGit, не из работающего образца); (c) DD09L
  TABKAT/TABART; (d) генерация SM30-видов (SE54) на ZTAI_SETT/ZTAI_MODEL/
  ZTAI_TASK (без LOB-полей); (e) после первого pull abapGit — статус «чисто»,
  расхождений с src/ нет.
