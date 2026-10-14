CLASS zcl_ai_tasks DEFINITION
  PUBLIC
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.

    TYPES ty_action TYPE c LENGTH 9.

    TYPES: BEGIN OF ts_task,
             task_id     TYPE zeai_task_id,
             source_info TYPE ztai_task-source_info,
             method_name TYPE ztai_task-method_name,
             category    TYPE ztai_task-category,
             active      TYPE abap_bool,
             prompt      TYPE string,
             canonical   TYPE string,
             test_source TYPE string,
           END OF ts_task.

    TYPES: BEGIN OF ts_error,
             line    TYPE i,
             message TYPE string,
           END OF ts_error.
    TYPES tt_errors TYPE STANDARD TABLE OF ts_error WITH DEFAULT KEY.

    CONSTANTS gc_action_inserted  TYPE ty_action VALUE 'INSERTED'.
    CONSTANTS gc_action_updated   TYPE ty_action VALUE 'UPDATED'.
    CONSTANTS gc_action_unchanged TYPE ty_action VALUE 'UNCHANGED'.

    " Разбор формата *.task.txt (PLAN §4.1): мета-строки @id/@source/@method/
    " @category/@active до первого маркера, затем секции ---PROMPT--- (обяз.),
    " ---CANONICAL---, ---TEST---. Содержимое секций хранится дословно
    " (без обрезки пробелов), завершающие LF срезаются.
    " Предусловие: iv_raw декодирован из UTF-8, BOM снят вызывающим.
    CLASS-METHODS parse
      IMPORTING iv_raw    TYPE string
      EXPORTING es_task   TYPE ts_task
                et_errors TYPE tt_errors.

    " Upsert по @id (PLAN §4.1): новая задача -> task_version = 1;
    " изменение содержания -> +1; идентичное -> без записи.
    CLASS-METHODS import_task
      IMPORTING is_task    TYPE ts_task
      EXPORTING ev_action  TYPE ty_action
                ev_version TYPE i.

    " TASKSET_HASH (PLAN §4.1): MD5 по отсортированным по TASK_ID строкам
    " "id:version" активных задач, разделитель LF. Менять алгоритм нельзя
    " без осознанного решения — на нём держится сравнимость трендов.
    CLASS-METHODS calc_taskset_hash
      RETURNING VALUE(rv_hash) TYPE ztai_run-taskset_hash.

  PROTECTED SECTION.
  PRIVATE SECTION.

    CLASS-METHODS join_trim
      IMPORTING it_lines       TYPE string_table
      RETURNING VALUE(rv_text) TYPE string.

    CLASS-METHODS add_error
      IMPORTING iv_line    TYPE i
                iv_message TYPE string
      CHANGING  ct_errors  TYPE tt_errors.

    CLASS-METHODS fields_differ
      IMPORTING is_task        TYPE ts_task
                is_db          TYPE ztai_task
      RETURNING VALUE(rv_diff) TYPE abap_bool.

ENDCLASS.


CLASS zcl_ai_tasks IMPLEMENTATION.

  METHOD parse.

    CLEAR: es_task, et_errors.

    DATA lv_text TYPE string.
    lv_text = iv_raw.
    REPLACE ALL OCCURRENCES OF cl_abap_char_utilities=>cr_lf IN lv_text
            WITH cl_abap_char_utilities=>newline.
    SPLIT lv_text AT cl_abap_char_utilities=>newline INTO TABLE DATA(lt_lines).

    CONSTANTS: lc_prompt    TYPE string VALUE `---PROMPT---`,
               lc_canonical TYPE string VALUE `---CANONICAL---`,
               lc_test      TYPE string VALUE `---TEST---`.

    DATA: lv_state   TYPE c LENGTH 1,  " '' = мета, P/C/T = внутри секции
          lv_tabix   TYPE i,
          lv_check   TYPE string,
          lv_key     TYPE string,
          lv_val     TYPE string,
          lv_active_seen TYPE abap_bool,
          lt_prompt    TYPE string_table,
          lt_canonical TYPE string_table,
          lt_test      TYPE string_table.

    LOOP AT lt_lines INTO DATA(lv_line).

      lv_tabix = sy-tabix.
      lv_check = lv_line.
      CONDENSE lv_check.

      " маркеры секций (после обрезки — точное совпадение)
      IF lv_check = lc_prompt OR lv_check = lc_canonical OR lv_check = lc_test.
        CASE lv_check.
          WHEN lc_prompt.    lv_state = 'P'.
          WHEN lc_canonical. lv_state = 'C'.
          WHEN lc_test.      lv_state = 'T'.
        ENDCASE.
        CONTINUE.
      ENDIF.

      IF lv_state = ''.
        " блок меты: строки @ключ: значение; пустые строки пропускаются
        IF lv_check IS INITIAL.
          CONTINUE.
        ENDIF.
        IF lv_check(1) = '@'.
          CLEAR: lv_key, lv_val.  " SPLIT без разделителя не чистит второй target
          SPLIT lv_check AT ':' INTO lv_key lv_val.
          lv_key = to_lower( lv_key ).
          SHIFT lv_key LEFT DELETING LEADING '@'.
          CONDENSE lv_val.
          CASE lv_key.
            WHEN 'id'.
              IF es_task-task_id IS NOT INITIAL.
                add_error( EXPORTING iv_line = lv_tabix
                                    iv_message = 'duplicate @id'
                           CHANGING ct_errors = et_errors ).
              ENDIF.
              es_task-task_id = lv_val.
            WHEN 'source'.
              es_task-source_info = lv_val.
            WHEN 'method'.
              es_task-method_name = lv_val.
            WHEN 'category'.
              es_task-category = lv_val.
            WHEN 'active'.
              lv_active_seen = abap_true.
              es_task-active = boolc( to_lower( lv_val ) = 'true' ).
            WHEN OTHERS.
              add_error( EXPORTING iv_line = lv_tabix
                                  iv_message = |unknown meta key { lv_key }|
                         CHANGING ct_errors = et_errors ).
            ENDCASE.
          ELSE.
            add_error( EXPORTING iv_line = lv_tabix
                                iv_message = 'content before ---PROMPT---'
                       CHANGING ct_errors = et_errors ).
          ENDIF.
          CONTINUE.
        ENDIF.

        " содержимое секций — без изменений
        CASE lv_state.
          WHEN 'P'. APPEND lv_line TO lt_prompt.
          WHEN 'C'. APPEND lv_line TO lt_canonical.
          WHEN 'T'. APPEND lv_line TO lt_test.
        ENDCASE.
    ENDLOOP.

    es_task-prompt      = join_trim( lt_prompt ).
    es_task-canonical   = join_trim( lt_canonical ).
    es_task-test_source = join_trim( lt_test ).

    " обязательные мета и секция PROMPT — как в гейте check_tasks.py
    IF es_task-task_id IS INITIAL.
      add_error( EXPORTING iv_line = 0 iv_message = '@id missing'
                 CHANGING ct_errors = et_errors ).
    ENDIF.
    IF lv_active_seen = abap_false.
      add_error( EXPORTING iv_line = 0 iv_message = '@active missing'
                 CHANGING ct_errors = et_errors ).
    ENDIF.
    IF es_task-method_name IS INITIAL.
      add_error( EXPORTING iv_line = 0 iv_message = '@method missing'
                 CHANGING ct_errors = et_errors ).
    ENDIF.
    IF es_task-source_info IS INITIAL.
      add_error( EXPORTING iv_line = 0 iv_message = '@source missing'
                 CHANGING ct_errors = et_errors ).
    ENDIF.
    IF es_task-category IS INITIAL.
      add_error( EXPORTING iv_line = 0 iv_message = '@category missing'
                 CHANGING ct_errors = et_errors ).
    ENDIF.
    IF es_task-prompt IS INITIAL.
      add_error( EXPORTING iv_line = 0 iv_message = 'PROMPT section missing/empty'
                 CHANGING ct_errors = et_errors ).
    ENDIF.

  ENDMETHOD.


  METHOD import_task.

    CLEAR: ev_action, ev_version.

    DATA ls_db TYPE ztai_task.
    SELECT SINGLE * FROM ztai_task
      WHERE task_id = @is_task-task_id
      INTO @ls_db.

    DATA lv_ts TYPE ztai_task-created_at.
    GET TIME STAMP FIELD lv_ts.

    IF sy-subrc <> 0.
      " новая задача
      ls_db = CORRESPONDING ztai_task( is_task ).
      ls_db-task_version = 1.
      ls_db-created_by   = sy-uname.
      ls_db-created_at   = lv_ts.
      INSERT ztai_task FROM @ls_db.
      ev_action  = gc_action_inserted.
      ev_version = 1.
    ELSE.
      IF fields_differ( is_task = is_task is_db = ls_db ) = abap_false.
        ev_action  = gc_action_unchanged.
        ev_version = ls_db-task_version.
        RETURN.
      ENDIF.
      " содержание изменилось — версия +1, поле active правится реимпортом
      DATA lv_version TYPE i.
      lv_version = ls_db-task_version.
      ls_db = CORRESPONDING ztai_task( is_task ).
      ls_db-task_version = lv_version + 1.
      ls_db-changed_by   = sy-uname.
      ls_db-changed_at   = lv_ts.
      UPDATE ztai_task FROM @ls_db.
      ev_action  = gc_action_updated.
      ev_version = ls_db-task_version.
    ENDIF.

  ENDMETHOD.


  METHOD calc_taskset_hash.

    SELECT task_id, task_version
      FROM ztai_task
      WHERE active = @abap_true
      ORDER BY task_id
      INTO TABLE @DATA(lt_tasks).

    DATA lt_lines TYPE string_table.
    LOOP AT lt_tasks INTO DATA(ls_task).
      APPEND |{ ls_task-task_id }:{ ls_task-task_version }| TO lt_lines.
    ENDLOOP.

    DATA lv_data TYPE string.
    lv_data = concat_lines_of( table = lt_lines
                               sep   = cl_abap_char_utilities=>newline ).
    IF lv_data IS INITIAL.
      RETURN.  " нет активных задач — пустой хэш
    ENDIF.

    DATA lv_hashx TYPE xstring.
    CALL FUNCTION 'CALCULATE_HASH_FOR_CHAR'
      EXPORTING
        alg   = 'MD5'
        data  = lv_data
      IMPORTING
        hashx = lv_hashx
      EXCEPTIONS
        OTHERS = 1.
    IF sy-subrc = 0.
      rv_hash = lv_hashx.  " xstring -> CHAR32 (hex-представление)
    ENDIF.

  ENDMETHOD.


  METHOD join_trim.

    rv_text = concat_lines_of( table = it_lines
                               sep   = cl_abap_char_utilities=>newline ).

    " срезать завершающие переводы строк
    DATA lv_off TYPE i.
    lv_off = strlen( rv_text ) - 1.
    WHILE lv_off >= 0 AND rv_text+lv_off(1) = cl_abap_char_utilities=>newline.
      rv_text = rv_text(lv_off).
      lv_off = lv_off - 1.
    ENDWHILE.

  ENDMETHOD.


  METHOD add_error.
    APPEND VALUE ts_error( line = iv_line message = iv_message ) TO ct_errors.
  ENDMETHOD.


  METHOD fields_differ.
    rv_diff = boolc( is_task-prompt      <> is_db-prompt
                  OR is_task-canonical   <> is_db-canonical
                  OR is_task-test_source <> is_db-test_source
                  OR is_task-method_name <> is_db-method_name
                  OR is_task-category    <> is_db-category
                  OR is_task-source_info <> is_db-source_info
                  OR is_task-active      <> is_db-active ).
  ENDMETHOD.

ENDCLASS.
