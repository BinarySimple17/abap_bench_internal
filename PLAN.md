# Внутренний LLM-бенчмарк ABAP (in-SAP) — план реализации

Еженедельный фоновый мониторинг качества LLM на генерации ABAP-кода, целиком
внутри SAP-системы. Цель — накопительная статистика по моделям, чтобы ловить
момент, когда модель улучшается или деградирует (в т.ч. из-за тихих апдейтов
вендора).

Подход перенесён из Python-бенчмарка
`LLM-Benchmark-ABAP-Code-Generation` (arXiv:2601.15188): задачи HumanEval-типа,
раунды с фидбеком по ошибкам, повторения, многоуровневая оценка. Промпты задач
используются дословно — это сохраняет преемственность с исходным бенчмарком.

---

## 1. Зафиксированные решения (из обсуждения)

| Параметр | Решение |
|---|---|
| Фаза 1 | **Syntax-only**: `SYNTAX-CHECK FOR itab`, без создания и без исполнения кода |
| Фаза 2 | Юнит-тесты через `GENERATE SUBROUTINE POOL`, включается **настройкой** (по умолчанию выкл.) |
| Объём на старте | 10 задач × 5 повторений × до 5 попыток на диалог (всё — настройки) |
| Управление задачами | Задачи — текстовые файлы в git (`tasks/`), импорт в БД отчётом |
| Система | dev; исполнение сгенерированного кода в фазе 1 исключено архитектурно |
| Интерпретация «5 попыток» | `REPETITIONS = 5`, `MAX_ATTEMPTS = 5` (всего вызовов LLM на диалог: 1 + 4 коррекции). Оба значения в таблице настроек, меняются без кода |
| Версия системы | **NetWeaver 7.54** — та же dev-система, что у zvvvv-abab-vectors ([ADR-003](docs/adr/ADR-003-nw-754.md)): и наш Z-код, и генерируемый код — языковой уровень до ABAP 7.54 (конструкции 7.55+ запрещены); гейт abaplint `syntax.version = v754` ([ADR-002](docs/adr/ADR-002-abaplint-gate.md)) |
| LLM SDK | **Microsoft AI SDK for ABAP** ([aisdkforsapabap](https://github.com/microsoft/aisdkforsapabap)) — общий случай; ставится в dev-систему отдельно (abapGit, [ADR-005](docs/adr/ADR-005-llm-sdk.md), BL-1). Поверх — наш прокси `ZCL_AI_LLM_SDK_PROXY` за `ZIF_AI_LLM_CLIENT`; до установки SDK движок отлаживается на `ZCL_AI_LLM_MOCK` |

---

## 2. Архитектура

```
SM36: еженедельная периодическая job
   └─ REPORT ZAI_RUN (создаёт run, вызывает движок)
        └─ ZCL_AI_ENGINE                      цикл: модель × задача × повторение
             ├─ ZIF_AI_LLM_CLIENT             абстракция LLM
             │    ├─ ZCL_AI_LLM_SDK_PROXY      прокси над aisdkforsapabap (ставится отдельно)
             │    └─ ZCL_AI_LLM_MOCK           детерминированные ответы для отладки
             ├─ ZCL_AI_CANON                   снятие ```-фенсов, каноникализация класса/метода
             ├─ ZCL_AI_CHECK                   SYNTAX-CHECK FOR itab   (фаза 1)
             │    └─ (фаза 2) Z_AI_RUN_TESTS / DESTINATION 'NONE' + GENERATE SUBROUTINE POOL
             ├─ ZCL_AI_SETT                    настройки: ZTAI_SETT + дефолты в коде (ADR-006)
             ├─ ZTAI_ROUND / ZTAI_RESULT       лог раундов и итоги (COMMIT после каждого раунда)
             └─ ENQUEUE EZ_AI_RUN               защита от параллельного запуска; идемпотентный resume
        └─ ZAI_STATUS (live ALV)  /  ZAI_REPORT (итоги + тренды + алерты)
```

Ключевое свойство: движок пишет каждый раунд в БД сразу (`COMMIT WORK` после
раунда). Упавшая или прерванная job перезапускается на том же `run_id` и
продолжает только недостающие (модель × задача × повторение).

---

## 3. Контракт задачи и промпты

**Промпт** — дословно Python-спека из исходного датасета (`def f(...) -> T` +
docstring с doctest-примерами). Модель должна сама перенести её на ABAP.
10 стартовых задач уже лежат в `tasks/` (см. §4.1).

**System prompt** — адаптация исходного (см. `src/generate_llm_answers.py`
репозитория-источника), с двумя изменениями для работы без создания объектов:

- вместо глобального Z-класса — **локальный класс `LCL_SOLUTION`** в составе
  программы (локальный класс проверяется `SYNTAX-CHECK`'ом и в фазе 2
  исполняется во временном пуле, глобальный — нет);
- версия системы — подставляется из настройки `NW_VERSION`; дефолт для нашей
  dev-системы — **NetWeaver 7.54** ([ADR-003](docs/adr/ADR-003-nw-754.md)). В
  исходном бенчмарке стоял 7.57 / S/4HANA 2022 — разница осознанная и
  объявляется модели явно.

Остальное сохраняем для сравнимости: один публичный **статический** метод,
`RETURNING` вместо `EXPORTING`, точка как десятичный разделитель, «только код,
без пояснений». System prompt хранится в настройках — редактируется без кода.

**Языковой уровень — до ABAP 7.54 включительно (система NW 7.54, [ADR-003](docs/adr/ADR-003-nw-754.md)).** Действует в обе стороны:

- **Для LLM**: system prompt объявляет модели версию системы. Ответ с
  конструкциями 7.55+ не пройдёт syntax-check на 7.54 — это корректный сигнал
  бенчмарка (модель должна писать под объявленную версию), а не шум.
- **Для нашего Z-кода** (`Z*AI_*`): допустим весь синтаксис до 7.54
  включительно — inline-объявления `DATA(...)`, `VALUE/CONV/COND/REDUCE`,
  `FOR ... IN`, табличные выражения, `CORRESPONDING`, строковые шаблоны, а
  также Open SQL CTE `WITH` (7.50) и оконные функции (7.54). Запрещены
  конструкции 7.55+ — например, `FINAL(...)` (7.57). Статистику в отчётах
  считаем в ABAP. Локальный гейт — abaplint `syntax.version = v754`
  ([ADR-002](docs/adr/ADR-002-abaplint-gate.md)); он задаёт базлайн парсера и
  правил, но не жёстко отсекает всё новее (проверено: `FINAL(...)` не ловится)
  — запрет 7.55+ остаётся правилом кодирования, авторитетная проверка — система.
- Стартовые 10 задач проверены на 7.40 — на 7.54 остаются валидными. При
  добавлении задач проверять совместимость с 7.54 (в конвертере/импорте).
- На M1 сверить фактический релиз системы (CVERS / SAP_BASIS + SP) с целевым
  NW 7.54; при расхождении — ADR с синхронной правкой `syntax.version` и §3.

**Каноникализация** (порт `extract_contract` / `canonicalize_code` /
`remove_code_blocks` из `abap_interaction.py`):

1. снять markdown-фенсы (```` ```lang ```` / ` ``` ` строки);
2. найти `CLASS <name> DEFINITION` (первое вхождение); нет класса → фидбек
   «Code structure issue: …» (аналог stage `canonicalization`), попытка не
   сгорает только если ошибка инфраструктурная — см. §6;
3. переименовать класс → `lcl_solution` (whole-word, case-insensitive) и
   первый публичный метод → контрактное имя задачи (`@method` в файле задачи);
4. удалить атрибут `PUBLIC` из `DEFINITION` (глобальный класс от модели —
   частый случай; локальным классам `PUBLIC` запрещён).

Контрактное имя метода берётся из юнит-теста исходного датасета (первый вызов
`z_humaneval_NNN=>метод(`) — это ровно то, как контракт извлекается в исходном
бенчмарке. В файле задачи оно уже зафиксировано в `@method`.

**Обёртка для проверки** — канонизированный код дополняется шапкой программы:

```abap
PROGRAM zai_probe.
"* ---- код LLM (class lcl_solution ... ) ----
```

---

## 4. Хранение данных

### 4.1. Файлы задач — `tasks/*.task.txt` (источник правды для содержания задач)

```
@id: humaneval_013                          — ключ в БД
@source: LLM-Benchmark-... 13.txt (MIT)     — происхождение
@method: greatest_common_divisor            — контрактное имя метода
@category: Mathematical Calculation
@active: true

---PROMPT---      (обязателен) текст промпта дословно
---CANONICAL---   (опц.) эталонное решение, класс уже переименован в lcl_solution
---TEST---        (опц., фаза 2) юнит-тест; вызовы уже lcl_solution=>метод(
```

Управление задачами:

- **Добавить задачу**: положить файл в `tasks/` (или расширить
  `SELECTED` в `tools/build_tasks.py` для задач из исходного датасета и
  запустить его), запустить отчёт `ZAI_IMPORT_TASKS` (диалог: выбор файла;
  фон: каталог на сервере приложений).
- Импорт — upsert по `@id`. Если содержание изменилось → `task_version + 1`;
  «замороженность» набора обеспечивает snapshot: `ZTAI_RUN-TASKSET_HASH`
  (хэш отсортированного списка id+version активных задач) — тренды считаются
  только внутри одинаковых hash.
- Деактивация: `@active: false` + реимпорт, или флаг в `ZTAI_TASK` через SM30.
- Файлы в git → история изменений задач бесплатна.

### 4.2. Таблицы (префикс `ZTAI_*` — [ADR-004](docs/adr/ADR-004-naming-convention.md))

| Таблица | Ключ | Назначение / основные поля |
|---|---|---|
| `ZTAI_TASK` | `TASK_ID` (char30, напр. `humaneval_013`) | `PROMPT`, `TEST_SOURCE`, `CANONICAL` (STRING); `METHOD_NAME`, `CATEGORY`, `ACTIVE`, `TASK_VERSION`, `SOURCE_INFO`, changed-by/at |
| `ZTAI_MODEL` | `MODEL_ID` (char30) | `DISPLAY_NAME`, `SDK_PROFILE` (ссылка на конфиг SDK), `TEMPERATURE` (деф. 0.2), `MAX_TOKENS`, `ACTIVE`, заметки |
| `ZTAI_RUN` | `RUN_ID` (char32 UUID) | `STARTED_AT/ FINISHED_AT`, `STATUS` (R/S/F), snapshot параметров (`REPETITIONS`, `MAX_ATTEMPTS`, `EXECUTE_UNIT_TESTS`, `SYSTEM_PROMPT`-hash), `TASKSET_HASH`, `TRIGGERED_BY` |
| `ZTAI_ROUND` | `RUN_ID, MODEL_ID, TASK_ID, REP_NO, ATTEMPT_NO` | лог раунда: `RESPONSE_RAW`, `CODE` (после фенсов), `CANON_OK`, `SYNTAX_OK`, `SYNTAX_MSG`, `SYNTAX_LINE`, `FEEDBACK_SENT` (STRING; пусто при успехе), `INFRA_FLAG`, `INFRA_MSG`, `LATENCY_MS`, `TOKENS_IN/OUT`, `CREATED_AT` |
| `ZTAI_RESULT` | `RUN_ID, MODEL_ID, TASK_ID, REP_NO` | итог диалога: `STATUS` (S=success / X=maxed out / I=infra-failed), `ATTEMPTS_USED`, `FIRST_OK_ATTEMPT`, `LATENCY_MS_SUM`, `TOKENS_*_SUM`, `LAST_ERROR` |
| `ZTAI_SETT` | `KEY` (char30) | `VALUE` (STRING); SM30-совместимо |

STRING-колонки → таблицы с LOB (требование NW ≥ 7.40 — ок для dev).

В `ZTAI_ROUND` хранится вся история диалога (аналог `data/<model>.json`):
восстановление сообщений = system prompt + промпт задачи + чередование
`RESPONSE_RAW` / `FEEDBACK_SENT`.

### 4.3. Настройки `ZTAI_SETT` (ключ → дефолт)

| Ключ | Дефолт | Смысл |
|---|---|---|
| `REPETITIONS` | `5` | повторений каждой задачи на модель за прогон |
| `MAX_ATTEMPTS` | `5` | максимум вызовов LLM на один диалог (1 + 4 коррекции) |
| `EXECUTE_UNIT_TESTS` | `` (выкл.) | **галка фазы 2**; в фазе 1 движок её игнорирует |
| `SYSTEM_PROMPT` | текст из §3 | system prompt (с плейсхолдером версии NW) |
| `NW_VERSION` | `NetWeaver 7.54 (AS ABAP 7.54)` | подстановка в system prompt; модель генерирует под эту версию ([ADR-003](docs/adr/ADR-003-nw-754.md)) |
| `INFRA_RETRIES` | `3` | ретраи инфра-ошибок SDK с бэкоффом |
| `INFRA_BACKOFF_S` | `30` | пауза между ретраями, сек |
| `ALERT_MIN_RUNS` | `4` | алерты включаются после N прогонов |
| `ALERT_DELTA_PCT` | `10` | порог алерта, процентных пунктов |

Дефолты зашиты в коде `ZCL_AI_SETT` ([ADR-006](docs/adr/ADR-006-phases-offline.md)):
первый прогон работает на пустой `ZTAI_SETT`, строки таблицы — override без
кода (SM30 после генерации вида на M07).

---

## 5. Фаза 1 — syntax-only проверка (ядро)

```abap
DATA: lt_source TYPE STANDARD TABLE OF string,   " при проблемах с STRING — c leng 255
      lv_msg    TYPE string,
      lv_line   TYPE i,
      lv_word   TYPE string,
      ls_trdir  TYPE trdir.

ls_trdir-name = 'ZAI_PROBE'.
ls_trdir-subc = '1'.            " исполняемая программа

SYNTAX-CHECK FOR lt_source
  MESSAGE lv_msg LINE lv_line WORD lv_word
  PROGRAM 'ZAI_PROBE'
  DIRECTORY ENTRY ls_trdir.
IF sy-subrc <> 0.
  " фидбек модели: ошибка lv_msg, строка lv_line
ENDIF.
```

Гарантии фазы 1 (безопасность):

- оператор `SYNTAX-CHECK FOR itab` не создаёт объект в репозитории и не
  исполняет проверяемый код;
- в движке фазы 1 **отсутствуют** `INSERT REPORT`, `SUBMIT`, `GENERATE`,
  `CALL TRANSFORMATION` и запись объектов — код LLM физически негде исполнить;
- job гоняется от технического пользователя с минимальными правами
  (таблицы + RFC SDK) — гигиена на будущее.

Проверяемая сущность — полный исходник программы (`PROGRAM` + локальный
класс), поэтому любые ссылки на существующие DDIC-типы/таблицы системы
резолвятся штатно. Задачи со спроектированными Z-таблицами (ERP-задачи
исходного датасета) пока не включены.

**Фидбек при ошибке** (стиль исходного бенчмарка, для сравнимости):

```
The syntax check failed with the following error: <msg> (line <n>).
Return the complete corrected code only.
```

Ошибки каноникализации: `Code structure issue: no ABAP class definition
found in your answer. ...` — попытка засчитывается (поведение как в исходном
бенчмарке для stage `canonicalization`).

---

## 6. Движок — жизненный цикл диалога

На каждый (модель × задача × повторение):

```
attempt = 1..MAX_ATTEMPTS:
  1. собрать сообщения: system + промпт + (ответ, фидбек)×прошлые попытки
  2. ZIF_AI_LLM_CLIENT->chat( ... )          " TIMESTAMPS, tokens, latency
       ├─ инфра-сбой SDK → INFRA_FLAG, ретрай ≤ INFRA_RETRIES с бэкоффом,
       │                    попытка НЕ сгорает, модели не отправляется;
       │                    исчерпаны → диалог STATUS = 'I', идти дальше
  3. CANON: фенсы → класс → переименование     " сбой = фидбек, attempt сгорает
  4. CHECK: SYNTAX-CHECK
       ├─ ok  → STATUS='S', FIRST_OK_ATTEMPT=attempt, конец диалога
       └─ err → FEEDBACK_SENT = текст ошибки, следующий attempt
  5. COMMIT WORK (раунд записан в ZTAI_ROUND)
attempt > MAX_ATTEMPTS → STATUS='X' (maxed out)
```

- Состояния (`ZTAI_RESULT.STATUS`): `S` / `X` / `I` — прямой аналог
  `Success / MaxedOut / InfraRetriable→infra-failed` из `chat_state.py`;
  `R`unning — пока диалог не закрыт.
- **Resume**: `ZTAI_RUN-STATUS='R'` + отсутствие строки результата = работа
  продолжается; строки с финальным статусом не пересчитываются. Перезапуск
  job с тем же `RUN_ID` (параметр отчёта) докручивает хвост.
- Версия модели из ответа SDK пишется в `ZTAI_RESULT`/отчёты — изменение
  версии вендором сразу видно в трендах.

---

## 7. Фаза 2 — юнит-тесты (дизайн заложен сейчас, включается галкой)

`EXECUTE_UNIT_TESTS = X` переключает шаг 4 движка с syntax-check на
тестовый прогон (syntax-check выполняется первым — это под-условие).

**Сборка тестовой программы** (per задача, детерминированно):

```
PROGRAM zai_probe.
<канонизированный код LLM: class lcl_solution ...>
<тест-класс из @TEST: class ltcl_... for testing ...>
"* подмена при сборке: cl_abap_unit_assert=>  →  zcl_ai_assert=>
FORM run_tests CHANGING cs_summary TYPE ... .
  DATA(lo_t) = NEW ltcl_xxx( ).
  TRY. lo_t->test_case_1( ). "passed+1. CATCH zcx_ai_assert INTO lx. "failed + msg
  ENDTRY.                                     " по FORM-у на каждый тест-метод
ENDFORM.
```

- Имена тест-методов парсятся один раз из `---TEST---` (`METHODS ... FOR
  TESTING`) — FORM генерируется статически, без RTTI.
- `ZCL_AI_ASSERT` — свой мини-assert (assert_equals и фактический набор из
  тестов задач), при провале рейзит `ZCX_AI_ASSERT` с текстом; поведение вне
  AUnit-раннера становится предсказуемым, текст уходит модели как фидбек.

**Исполнение** — `GENERATE SUBROUTINE POOL lt_source` (сборка = неявный
syntax-check; объект временный, живёт до конца внутренней сессии, в БД не
попадает):

```abap
CALL FUNCTION 'Z_AI_RUN_TESTS'
  DESTINATION 'NONE'              " новая внутренняя сессия на каждый диалог:
  EXPORTING source = lt_source    " нет накопления subroutine-pools, есть таймаут RFC
  IMPORTING summary = ls_summary.
```

- Фидбек модели при провале: список упавших тестов с сообщениями assert'ов.
- Метрики фазы 2: `UnitOK@1`, `UnitOK_best` + разбивка «синтаксис ok, но
  поведение неверное» (главный сигнал, которого нет в фазе 1).
- Безопасность фазы 2: исполнение кода LLM включается **только** галкой;
  техпользователь без полномочий на модификацию данных; DB-задачи (SELECT) —
  только на копиях таблиц, в стартовый набор не входят.

---

## 8. Метрики, тренды, алерты

На прогон × модель (все — по `ZTAI_ROUND/RESULT`, только в пределах
одинакового `TASKSET_HASH`):

| Метрика | Определение |
|---|---|
| `SynOK@1` | % диалогов, синтаксис прошёл с 1-й попытки (аналог Success_R0) |
| `SynOK@k` | накопительный % «прошли к попытке k» (кривая по раундам) |
| `SynOK_best` | % прошедших за ≤ MAX_ATTEMPTS |
| `MeanAttempts` | среднее число попыток до успеха |
| `CanonFailRate` | % попыток, сгоревших на каноникализации |
| `InfraRate`, `Latency p50/p95`, `Tokens` | эксплуатационные |
| Drill-down | по категориям (`@category`) и по задачам |

**Тренд** — серия `SynOK@1` (фазы 2: `UnitOK@1`) по `RUN_ID` за недели.

**Алерт**: начиная с `ALERT_MIN_RUNS` прогонов, если последний прогон
отклоняется от среднего предыдущих на ≥ `ALERT_DELTA_PCT` п.п. → строка
помечается (в отчёте красным; опционально — e-mail через BCS, M4+).

Отчёты: `ZAI_STATUS` (ход текущего прогона, ALV), `ZAI_REPORT`
(итоги прогона + тренд + алерты, выгрузка CSV). CDS/Fiori — опционально позже.

---

## 9. Планировщик

- Разовая настройка: отчёт `ZAI_SCHEDULE_JOB` — `JOB_OPEN` /
  `JOB_SUBMIT(ZAI_RUN, вариант)` / `JOB_CLOSE` с недельной периодичностью
  (например, понедельник 05:00). Ручная альтернатива — SM36.
- Вариант `ZAI_RUN`: фильтры моделей/задач, override повторений/попыток,
  «возобновить RUN_ID» (пусто = новый прогон).
- Anti-overlap: `ENQUEUE EZ_AI_RUN`; второй запуск ждёт/выходит.

---

## 10. Объекты SAP (полный список имён)

| Тип | Имена |
|---|---|
| Таблицы | `ZTAI_TASK`, `ZTAI_MODEL`, `ZTAI_RUN`, `ZTAI_ROUND`, `ZTAI_RESULT`, `ZTAI_SETT` |
| Элементы данных | `ZEAI_*` — по мере необходимости при типизации полей таблиц (напр. `ZEAI_TASK_ID`, `ZEAI_MODEL_ID`, `ZEAI_RUN_ID`, статусы); конкретный набор — на M1 |
| Структуры | `ZSAI_*` — по мере необходимости (напр. `ZSAI_TEST_SUMMARY` — summary фазы 2 для `Z_AI_RUN_TESTS`) |
| Lock | `EZ_AI_RUN` |
| Интерфейс | `ZIF_AI_LLM_CLIENT` |
| Классы | `ZCL_AI_ENGINE`, `ZCL_AI_CANON`, `ZCL_AI_CHECK`, `ZCL_AI_SETT` (настройки с кодовыми дефолтами, ADR-006), `ZCL_AI_LLM_SDK_PROXY`, `ZCL_AI_LLM_MOCK`, `ZCL_AI_ASSERT`, `ZCL_AI_TASKS` (парсер/импорт) |
| Исключения | `ZCX_AI_LLM`, `ZCX_AI_ASSERT` |
| Отчёты | `ZAI_RUN`, `ZAI_IMPORT_TASKS`, `ZAI_STATUS`, `ZAI_REPORT`, `ZAI_SCHEDULE_JOB` |
| FM | `Z_AI_RUN_TESTS` (фаза 2, RFC 'NONE') |
| Maintenance | SM30-виды на `ZTAI_SETT`, `ZTAI_MODEL` (и `ZTAI_TASK` без STRING-полей); генерируются в системе на M07 ([ADR-006](docs/adr/ADR-006-phases-offline.md)) |

Конвенция префиксов — [ADR-004](docs/adr/ADR-004-naming-convention.md):
классы `ZCL_AI_*`, интерфейсы `ZIF_AI_*`, исключения `ZCX_AI_*`, таблицы
`ZTAI_*`, элементы данных `ZEAI_*`, структуры `ZSAI_*`, отчёты `ZAI_*`,
FM `Z_AI_*`, lock `EZ_AI_*`. При создании объекта проверять занятость имени
(инфикс `AI` ходовой — см. риски в ADR-004).

Пакет: транспортный `ZAI` ([ADR-007](docs/adr/ADR-007-package-zai.md)).

---

## 11. Дорожная карта — фазы ([ADR-006](docs/adr/ADR-006-phases-offline.md))

Разработка офлайн: ABAP пишется в `src/` в формате abapGit, локальная
верификация — только abaplint-гейт; системные проверки собраны в приёмочной
сессии M07. Соответствие прежним этапам: M1+M2 → фаза 1 (без smoke
реального SDK); smoke+M3+M4 → фаза 2; M5 → фаза 3.

### Фаза 1 — MVP ручного прогона на MOCK (сессии M01–M07)

| Сессия | Содержание | Критерий приёмки |
|---|---|---|
| M01 | DDIC офлайн: `ZEAI_*`/`ZTAI_*`/`ZSAI_*` (по мере необходимости) + `EZ_AI_RUN` — XML abapGit в `src/` | все объекты в `src/`, `make lint` зелёный |
| M02 | `ZCL_AI_TASKS` + `ZAI_IMPORT_TASKS`: парсер §4.1, upsert, `task_version`, `TASKSET_HASH` | код в `src/`, lint зелёный; сквозной импорт — M07 |
| M03 | `ZIF_AI_LLM_CLIENT` + `ZCL_AI_LLM_MOCK` + `ZCX_AI_LLM` (сценарии S / canon-fail / infra) | код в `src/`, lint зелёный; ответы MOCK — M07 |
| M04 | `ZCL_AI_CANON` + `ZCL_AI_CHECK` (§5) | код в `src/`, lint зелёный; реальный syntax-check — M07 |
| M05 | `ZCL_AI_SETT` (дефолты §4.3 в коде) + `ZCL_AI_ENGINE` (§6: S/X/I, ретраи, COMMIT, resume, ENQUEUE) | код в `src/`, lint зелёный; сквозной цикл — M07 |
| M06 | `ZAI_RUN` (ручной запуск: фильтры, override, resume-RUN_ID) + `ZAI_STATUS` (ALV логов) | код в `src/`, lint зелёный; прогон — M07 |
| M07 | Деплой в систему (пакет `ZAI`, ADR-007): abapGit pull, активация, SM30-виды (SE54), MOCK в `ZTAI_MODEL`, импорт 10 задач, проверки §13.5, ручной прогон на MOCK | сквозной прогон MOCK 10 задач; логи в `ZTAI_ROUND`/`ZTAI_RESULT` видны в ALV; resume работает |

### Фаза 2 — реальные модели и регулярность (после M07)

BL-1 (установка aisdkforsapabap), `ZCL_AI_LLM_SDK_PROXY` (ADR-005), реестр
реальных моделей (решение владельца, temperature 0.2), первый реальный
прогон, `ZAI_REPORT` (тренды/алерты/CSV), планировщик `ZAI_SCHEDULE_JOB`,
транзакционные коды (§13.4). Email — BL-2 (ALV достаточно, ADR-006).

### Фаза 3 — юнит-тесты (фаза 2 бенчмарка, §7)

`Z_AI_RUN_TESTS`, `ZCL_AI_ASSERT`, галка `EXECUTE_UNIT_TESTS`, метрики
UnitOK.

Наращивание объёма (больше задач, 180, ERP) — после стабилизации базелина,
расширением `SELECTED` в конвертере + реимпортом (новый `TASKSET_HASH`,
тренды не смешиваются автоматически).

---

## 12. Структура папки

```
abap_bench_internal/
  PLAN.md               этот план (канон)
  AGENTS.md             точка входа агента (рутины харнесса)
  tasks/                10 стартовых задач (*.task.txt, git)
  tools/build_tasks.py  конвертер задач из исходного датасета
  src/                  выгрузка abapGit: ABAP-объекты Z*AI_* (.abap + .xml)
  .abapgit.xml          контракт синхронизации с системой
  abaplint.json         abaplint-гейт ABAP-кода (make lint, v754 — ADR-002)
  abaplint-all.json     широкий линт-репорт (make lint-all)
  package.json          Node-зависимости только для локального abaplint
  Makefile              единый интерфейс команд (make check = lint + гейты)
  harness/              гейты, шаблоны, инструкция харнесса (ADR-001/002)
  docs/                 sessions.md (состояние работ), sessions/, adr/,
                        ABAP-PITFALLS.md (грабли ABAP — база знаний агента);
                        reference/ — читшиты SAP, локально (.gitignore)
  backlog/              всё вне скоупа сессий
```

Полная карта — в `AGENTS.md` («Структура»); состояние работ — `docs/sessions.md`.

---

## 13. Открытые вопросы

Закрыто:

- **LLM SDK** — Microsoft AI SDK for ABAP (aisdkforsapabap), ставится в
  систему отдельно (abapGit, BL-1); наш прокси-адаптер `ZCL_AI_LLM_SDK_PROXY`
  ([ADR-005](docs/adr/ADR-005-llm-sdk.md)); до установки — отладка на
  `ZCL_AI_LLM_MOCK`. Реальный SDK и прокси — фаза 2 ([ADR-006](docs/adr/ADR-006-phases-offline.md)).
- **Версия системы** — NetWeaver 7.54, языковой уровень до ABAP 7.54 (см. §3, [ADR-003](docs/adr/ADR-003-nw-754.md)).
- **Пакет** — транспортный `ZAI` ([ADR-007](docs/adr/ADR-007-package-zai.md)).
- **Email-отчёт** — отложен: ALV достаточно, рассылка BCS — [BL-2](backlog/items/BL-2-email-report.md) (решение владельца, [ADR-006](docs/adr/ADR-006-phases-offline.md)).

Открыто:

1. **Модели на старте** (фаза 2): сколько и какие (temperature 0.2 — как в исходном бенчмарке, кроме моделей с залоченной температурой); до фазы 2 работаем на MOCK ([ADR-006](docs/adr/ADR-006-phases-offline.md)).
2. Транзакционные коды для отчётов (удобство) — решить в фазе 2.
3. **Проверить на M07 (первый доступ к системе)**: фактический SAP_BASIS/SP (таблица `CVERS`); принимает ли `SYNTAX-CHECK FOR itab` строки типа STRING (если нет — паддинг в строки `c length 255`).
