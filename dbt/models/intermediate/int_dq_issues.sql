-- One row per (record, failed rule). Rules live here in one list so adding a rule is one line.
{%- set as_of = "cast('" ~ var('as_of_date', '2026-11-01') ~ "' as date)" -%}
{%- set rules = [
    ('missing_first_name',   'Missing first name',              'critical', "first_name_raw is null"),
    ('invalid_first_name',   'First name contains numbers or placeholders',              'critical', "first_name_raw is not null and not " ~ full_match('first_name_raw', '[A-Za-z][A-Za-z -]+')),
    ('missing_father_name',  'Missing father name',             'critical', "father_name is null"),
    ('missing_sex',          'Missing sex',                     'critical', "sex_raw is null"),
    ('nonstandard_sex',      'Sex not written as F or M',          'warning',  "sex_raw is not null and sex_raw not in ('F', 'M')"),
    ('missing_dob',          'Missing date of birth',           'critical', "date_of_birth_raw is null"),
    ('unparseable_dob',      'Birth date cannot be read',       'critical', "date_of_birth_raw is not null and date_of_birth is null"),
    ('future_dob',           'Birth date is in the future',         'critical', "date_of_birth > " ~ as_of),
    ('implausible_age',      'Age over 110',          'warning',  years_between('date_of_birth', as_of) ~ " > 110"),
    ('invalid_phone',        'Phone number in wrong format',            'warning',  "phone_raw is not null and phone is null"),
    ('household_size_range', 'Household size not between 1 and 20', 'warning', "household_size is null or household_size not between 1 and 20"),
    ('invalid_reg_date',     'Registration date not valid',       'warning',  "registration_date is null"),
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
