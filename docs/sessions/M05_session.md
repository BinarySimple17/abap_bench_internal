# M05 — Движок ZCL_AI_ENGINE + настройки ZCL_AI_SETT

Этап: Фаза 1 (ADR-006), ядро | Владелец: M | Зависимости: M02, M03, M04 | Оценка: — | Статус: [ ] ⬜

## ⚠️ Прочитай перед началом

> Написать офлайн ядро: `ZCL_AI_SETT` — чтение `ZTAI_SETT` с дефолтами §4.3,
> зашитыми в код (ADR-006 — первый прогон на пустой таблице), и
> `ZCL_AI_ENGINE` — жизненный цикл диалога PLAN.md §6: цикл модель × задача ×
> повторение, попытки 1..MAX_ATTEMPTS, состояния S/X/I, инфра-ретраи с
> бэкоффом, `COMMIT WORK` после каждого раунда, resume, ENQUEUE `EZ_AI_RUN`.
> Проверка сквозного цикла на MOCK — M07; локально — lint.

### Правила для исполнителя

1. Транзакционность: каждый раунд — запись `ZTAI_ROUND` + `COMMIT WORK`
   (PLAN.md §2); никакой записи целыми пачками по прогону.
2. Resume идемпотентен: строка `ZTAI_RESULT` с финальным статусом не
   пересчитывается; `ZTAI_RUN-STATUS='R'` + отсутствие результата = работа.
3. Настройки — только через `ZCL_AI_SETT` (никаких «магических чисел» в
   движке); дефолты §4.3 — в коде SETT.
4. Уровень 7.54; `make lint` зелёный.

## Предусловия

- [ ] M02–M04 закрыты: контракты `ZCL_AI_TASKS`, `ZIF_AI_LLM_CLIENT`,
      `ZCL_AI_CANON`, `ZCL_AI_CHECK` доступны
- [ ] `make check` зелёный на старте

## Задачи

### Task 1: `ZCL_AI_SETT`

`get_string( iv_key )` + типизированные `get_int`/`get_flag`: SELECT из
`ZTAI_SETT`, пусто → дефолт из констант §4.3 (REPETITIONS=5, MAX_ATTEMPTS=5,
SYSTEM_PROMPT=текст §3, NW_VERSION=«NetWeaver 7.54 (AS ABAP 7.54)»,
INFRA_RETRIES=3, INFRA_BACKOFF_S=30, ALERT_*, EXECUTE_UNIT_TESTS — выкл.).
System prompt с плейсхолдером `{NW_VERSION}` → метод сборки.

**✅ Самопроверка:** класс в `src/`; полный набор дефолтов §4.3 константами;
lint зелёный.

---

### Task 2: `ZCL_AI_ENGINE` — цикл диалога §6

Старт (или resume по `IV_RUN_ID`): `ZTAI_RUN` (UUID `cl_system_uuid`,
snapshot параметров, `TASKSET_HASH` из `ZCL_AI_TASKS`, STATUS='R'),
`ENQUEUE EZ_AI_RUN` (занято → ясная ошибка «прогон уже идёт»). Цикл:
активные `ZTAI_MODEL` × активные `ZTAI_TASK` × 1..REPETITIONS; skip, если
`ZTAI_RESULT` уже есть. Диалог (§6): попытка 1..MAX_ATTEMPTS — собрать
сообщения (system + промпт + история `ZTAI_ROUND`: ответ/фидбек) →
`chat` → инфра-сбой: `ZCX_AI_LLM` → ретрай ≤ INFRA_RETRIES с
`WAIT UP TO … SECONDS`; исчерпаны → `ZTAI_RESULT-STATUS='I'`, дальше;
успех ответа → CANON (провал → раунд с CANON_OK=abap, фидбек, попытка
сгорает) → CHECK (ok → STATUS='S', FIRST_OK_ATTEMPT; err → фидбек).
`ATTEMPT > MAX_ATTEMPTS` → 'X'. После каждого раунда — `COMMIT WORK`.
Финал: `ZTAI_RUN-STATUS='S'`, `FINISHED_AT`, DEQUEUE.

**✅ Самопроверка:** класс в `src/`; все ветви §6 в коде (S/X/I, ретраи,
CANON-провал, resume); lint зелёный.

---

## Критерии приёмки

- [ ] `ZCL_AI_SETT`, `ZCL_AI_ENGINE` в `src/`; `make lint`/`make check` зелёные
- [ ] В отчёте — таблица соответствия веток кода → пункты §6
- [ ] «Проверить на M07»: сквозной цикл на MOCK-сценариях S/X/CANON/INFRA; прерывание и resume

## Ловушки

1. `WAIT UP TO n SECONDS` принимает секунды; INFRA_BACKOFF_S — уже секунды,
   не миллисекунды.
2. Latency/tokens — суммируются в `ZTAI_RESULT` (LATENCY_MS_SUM,
   TOKENS_*_SUM); версия модели из ответа — в результат/отчёты (§6).
3. Не лови `CX_ROOT` везде — только контрактные `ZCX_AI_LLM` у клиента;
   прочее — падение job = resume на M07.
4. ENQUEUE/DEQUEUE — по `RUN_ID`; DEQUEUE в очистке (даже при исключении),
   иначе повторный запуск заблокирован до таймаута.
5. `SY-TZONE`/`utclong` — фиксируй схему времени один раз (UTC) и держи её
   во всех полях-метках.

## Отчёт по сессии (заполняется по факту)

- Сделано по Task'ам:
  - **Task 1:** <...>
  - **Task 2:** <...>
- Отклонения от плана: <...>
- Перенесено в другие сессии: <...>
- Верификация: <`make check`, `make verify-session S=M05`>
- Проверить на M07: <сквозной цикл, resume, ENQUEUE>
