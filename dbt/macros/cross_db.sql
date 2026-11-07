{#- Small set of functions that differ between DuckDB and BigQuery. Models call these, never the raw function. -#}

{% macro digits_only(col) %}{{ return(adapter.dispatch('digits_only')(col)) }}{% endmacro %}
{% macro default__digits_only(col) %}regexp_replace({{ col }}, '[^0-9]', '', 'g'){% endmacro %}
{% macro bigquery__digits_only(col) %}regexp_replace({{ col }}, r'[^0-9]', ''){% endmacro %}

{% macro letters_only(col) %}{{ return(adapter.dispatch('letters_only')(col)) }}{% endmacro %}
{% macro default__letters_only(col) %}trim(regexp_replace(regexp_replace(lower({{ col }}), '[^a-z ]', '', 'g'), ' +', ' ', 'g')){% endmacro %}
{% macro bigquery__letters_only(col) %}trim(regexp_replace(regexp_replace(lower({{ col }}), r'[^a-z ]', ''), r' +', ' ')){% endmacro %}

{% macro full_match(col, pattern) %}{{ return(adapter.dispatch('full_match')(col, pattern)) }}{% endmacro %}
{% macro default__full_match(col, pattern) %}regexp_full_match({{ col }}, '{{ pattern }}'){% endmacro %}
{% macro bigquery__full_match(col, pattern) %}regexp_contains({{ col }}, r'^{{ pattern }}$'){% endmacro %}

{% macro parse_iso_date(col) %}{{ return(adapter.dispatch('parse_iso_date')(col)) }}{% endmacro %}
{% macro default__parse_iso_date(col) %}cast(try_strptime({{ col }}, '%Y-%m-%d') as date){% endmacro %}
{% macro bigquery__parse_iso_date(col) %}safe.parse_date('%Y-%m-%d', {{ col }}){% endmacro %}

{% macro years_between(start_date, end_date) %}{{ return(adapter.dispatch('years_between')(start_date, end_date)) }}{% endmacro %}
{% macro default__years_between(start_date, end_date) %}date_diff('year', {{ start_date }}, {{ end_date }}){% endmacro %}
{% macro bigquery__years_between(start_date, end_date) %}date_diff({{ end_date }}, {{ start_date }}, year){% endmacro %}

{% macro blank_to_null(col) %}nullif(trim({{ col }}), ''){% endmacro %}

{#- Generic test: value is a 9-digit Ethiopian mobile number (9XXXXXXXX or 7XXXXXXXX). -#}
{% test valid_et_mobile(model, column_name) %}
select * from {{ model }}
where {{ column_name }} is not null
  and not {{ full_match(column_name, '[79][0-9]{8}') }}
{% endtest %}

{% macro safe_int(col) %}{{ return(adapter.dispatch('safe_int')(col)) }}{% endmacro %}
{% macro default__safe_int(col) %}try_cast({{ col }} as integer){% endmacro %}
{% macro bigquery__safe_int(col) %}safe_cast({{ col }} as int64){% endmacro %}
