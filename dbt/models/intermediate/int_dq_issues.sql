-- One row per (record, failed rule). Rules live here in one list so adding a rule is one line.
{%- set as_of = "cast('" ~ var('as_of_date', '2026-11-01') ~ "' as date)" -%}
{%- set rules = [
    ('missing_first_name',   'Missing first name',              'critical', "first_name_raw is null"),
    ('invalid_first_name',   'Invalid first name',              'critical', "first_name_raw is not null and not " ~ full_match('first_name_raw', '[A-Za-z][A-Za-z -]+')),
    ('missing_father_name',  'Missing father name',             'critical', "father_name is null"),
    ('missing_sex',          'Missing sex',                     'critical', "sex_raw is null"),
    ('nonstandard_sex',      'Non-standard sex value',          'warning',  "sex_raw is not null and sex_raw not in ('F', 'M')"),
    ('missing_dob',          'Missing date of birth',           'critical', "date_of_birth_raw is null"),
    ('unparseable_dob',      'Unparseable date of birth',       'critical', "date_of_birth_raw is not null and date_of_birth is null"),
    ('future_dob',           'Date of birth in future',         'critical', "date_of_birth > " ~ as_of),
    ('implausible_age',      'Implausible age (>110)',          'warning',  years_between('date_of_birth', as_of) ~ " > 110"),
    ('invalid_phone',        'Invalid phone format',            'warning',  "phone_raw is not null and phone is null"),
    ('household_size_range', 'Household size out of range (1-20)', 'warning', "household_size is null or household_size not between 1 and 20"),
    ('invalid_reg_date',     'Invalid registration date',       'warning',  "registration_date is null"),
    ('missing_location',     'Missing woreda or kebele',        'critical', "woreda is null or kebele is null"),
] %}

with registrations as (
    select * from {{ ref('stg_registrations') }}
)

{% for code, label, severity, condition in rules %}
select
    record_id,
    '{{ code }}'     as rule_code,
    '{{ label }}'    as rule_name,
    '{{ severity }}' as severity
from registrations
where {{ condition }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
