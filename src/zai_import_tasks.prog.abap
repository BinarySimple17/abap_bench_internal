REPORT zai_import_tasks.

" Импорт задач бенчмарка в ZTAI_TASK (PLAN §4.1/§4.2, сессия M02).
" Диалог: файл с фронтенда (UTF-8, BOM срезается); фон: каталог на сервере
" приложений, файлы по маске. Результат — ALV (задача -> действие/версия/
" ошибки) + TASKSET_HASH после импорта.

CLASS lcl_main DEFINITION FINAL.

  PUBLIC SECTION.
    TYPES: BEGIN OF ts_file,
             name    TYPE string,
             content TYPE string,
           END OF ts_file,
           tt_files TYPE STANDARD TABLE OF ts_file WITH DEFAULT KEY,
           BEGIN OF ts_out,
             task_id      TYPE zeai_task_id,
             action       TYPE c LENGTH 11,
             task_version TYPE i,
             message      TYPE string,
           END OF ts_out,
           tt_out TYPE STANDARD TABLE OF ts_out WITH DEFAULT KEY.

    CLASS-METHODS run.

    CLASS-METHODS read_front
      IMPORTING iv_file         TYPE string
      RETURNING VALUE(rt_files) TYPE tt_files.

    CLASS-METHODS read_server
      IMPORTING iv_dir          TYPE string
                iv_mask         TYPE string
      RETURNING VALUE(rt_files) TYPE tt_files.

    CLASS-METHODS xstring_to_text
      IMPORTING iv_x           TYPE xstring
      RETURNING VALUE(rv_text) TYPE string.

ENDCLASS.


CLASS lcl_main IMPLEMENTATION.

  METHOD xstring_to_text.
    rv_text = cl_abap_codepage=>convert_from( source = iv_x ).
  ENDMETHOD.


  METHOD read_front.

    TYPES ty_x255 TYPE x LENGTH 255.
    DATA lt_bin TYPE STANDARD TABLE OF ty_x255.
    DATA lv_len TYPE i.
    DATA lv_x   TYPE xstring.

    cl_gui_frontend_services=>gui_upload(
      EXPORTING
        filename   = iv_file
        filetype   = 'BIN'
      IMPORTING
        filelength = lv_len
      CHANGING
        data_tab   = lt_bin
      EXCEPTIONS
        file_open_error = 1
        file_read_error = 2
        OTHERS          = 3 ).
    IF sy-subrc <> 0.
      MESSAGE |gui_upload failed (rc={ sy-subrc })| TYPE 'E'.
    ENDIF.

    LOOP AT lt_bin INTO DATA(lv_row).
      CONCATENATE lv_x lv_row INTO lv_x IN BYTE MODE.
    ENDLOOP.

    " хвостовые нули последней строки — до фактической длины файла
    IF lv_len BETWEEN 1 AND xstrlen( lv_x ).
      lv_x = lv_x(lv_len).
    ENDIF.

    " UTF-8 BOM
    IF xstrlen( lv_x ) >= 3 AND lv_x(3) = 'EFBBBF'.
      lv_x = lv_x+3.
    ENDIF.

    APPEND VALUE ts_file( name    = iv_file
                          content = xstring_to_text( lv_x ) ) TO rt_files.

  ENDMETHOD.


  METHOD read_server.

    DATA lt_list TYPE STANDARD TABLE OF eps2fili WITH DEFAULT KEY.
    DATA lv_x    TYPE xstring.

    CALL FUNCTION 'EPS2_GET_DIRECTORY_LISTING'
      EXPORTING
        if_dir_name = iv_dir
        name_mask   = iv_mask
      TABLES
        dir_list    = lt_list
      EXCEPTIONS
        invalid_eps_subdir = 1
        sapgparam_error    = 2
        OTHERS             = 3.
    IF sy-subrc <> 0.
      MESSAGE |directory listing failed ({ iv_dir })| TYPE 'E'.
    ENDIF.

    LOOP AT lt_list INTO DATA(ls_file).
      DATA(lv_path) = |{ iv_dir }/{ ls_file-name }|.
      CLEAR lv_x.

      OPEN DATASET lv_path FOR INPUT IN BINARY MODE.
      IF sy-subrc <> 0.
        MESSAGE |cannot open { lv_path }| TYPE 'E'.
      ENDIF.
      READ DATASET lv_path INTO lv_x.
      CLOSE DATASET lv_path.

      IF xstrlen( lv_x ) >= 3 AND lv_x(3) = 'EFBBBF'.
        lv_x = lv_x+3.
      ENDIF.

      APPEND VALUE ts_file( name    = lv_path
                            content = xstring_to_text( lv_x ) ) TO rt_files.
    ENDLOOP.

  ENDMETHOD.


  METHOD run.

    IF p_file IS INITIAL.
      MESSAGE |Укажите файл (фронт) или каталог (сервер)| TYPE 'E'.
    ENDIF.

    DATA lt_files TYPE tt_files.
    IF p_front = 'X'.
      lt_files = read_front( p_file ).
    ELSE.
      lt_files = read_server( iv_dir = p_file iv_mask = p_mask ).
    ENDIF.

    IF lt_files IS INITIAL.
      WRITE / 'Файлы не найдены'.
      RETURN.
    ENDIF.

    DATA lt_out TYPE tt_out.
    LOOP AT lt_files INTO DATA(ls_file).

      zcl_ai_tasks=>parse(
        EXPORTING
          iv_raw    = ls_file-content
        IMPORTING
          es_task   = DATA(ls_task)
          et_errors = DATA(lt_errors) ).

      DATA ls_out TYPE ts_out.
      CLEAR ls_out.
      ls_out-task_id = ls_task-task_id.

      IF ls_task-task_id IS INITIAL OR ls_task-prompt IS INITIAL.
        ls_out-action = 'PARSE_ERROR'.
        ls_out-message = concat_lines_of(
          table = VALUE string_table(
                    FOR ls_err IN lt_errors
                      ( |{ ls_err-line }: { ls_err-message }| ) )
          sep   = '; ' ).
      ELSE.
        zcl_ai_tasks=>import_task(
          EXPORTING
            is_task    = ls_task
          IMPORTING
            ev_action  = DATA(lv_action)
            ev_version = DATA(lv_version) ).
        ls_out-action       = lv_action.
        ls_out-task_version = lv_version.
        IF lt_errors IS NOT INITIAL.
          " предупреждения (неизвестные ключи меты) — не блокируют импорт
          ls_out-message = concat_lines_of(
            table = VALUE string_table(
                      FOR ls_err IN lt_errors
                        ( |{ ls_err-line }: { ls_err-message }| ) )
            sep   = '; ' ).
        ENDIF.
      ENDIF.

      APPEND ls_out TO lt_out.

    ENDLOOP.

    WRITE: / 'TASKSET_HASH:', zcl_ai_tasks=>calc_taskset_hash( ).
    ULINE.

    cl_salv_table=>factory(
      IMPORTING
        r_salv_table = DATA(lo_alv)
      CHANGING
        t_table      = lt_out ).
    lo_alv->get_columns( )->set_optimize( abap_true ).
    lo_alv->display( ).

  ENDMETHOD.

ENDCLASS.


PARAMETERS p_front RADIOBUTTON GROUP src DEFAULT 'X'.
PARAMETERS p_srv   RADIOBUTTON GROUP src.
PARAMETERS p_file  TYPE string LOWER CASE.
PARAMETERS p_mask  TYPE string LOWER CASE DEFAULT '*.task.txt'.


AT SELECTION-SCREEN ON VALUE-REQUEST FOR p_file.

  IF p_front <> 'X'.
    RETURN.
  ENDIF.

  DATA lt_ftype TYPE filetable.
  DATA lv_rc    TYPE i.
  cl_gui_frontend_services=>file_open_dialog(
    CHANGING
      file_table = lt_ftype
      rc         = lv_rc
    EXCEPTIONS
      file_selector_not_created = 1
      OTHERS                    = 2 ).
  IF sy-subrc = 0 AND lv_rc = 1.
    READ TABLE lt_ftype INTO DATA(ls_f4) INDEX 1.
    IF sy-subrc = 0.
      p_file = ls_f4-filename.
    ENDIF.
  ENDIF.


START-OF-SELECTION.

  lcl_main=>run( ).
