-- One row per field registration, with every field standardised.
-- Raw values are kept alongside (suffix _raw) so data-quality rules can report what was actually captured.
with src as (
    select * from {{ source('raw', 'raw_records') }}
),

phone_steps as (
    select
        *,
        {{ digits_only('phone') }} as phone_digits
    from src
),

phone_clean as (
    select
        *,
        case
            when phone_digits like '251%' then substr(phone_digits, 4)
            when phone_digits like '0%' then substr(phone_digits, 2)
            else phone_digits
        end as phone_9
    from phone_steps
)

select
    record_id,

    {{ blank_to_null('first_name') }}                       as first_name_raw,
    nullif({{ letters_only('first_name') }}, '')            as first_name,
    nullif({{ letters_only('father_name') }}, '')           as father_name,
    nullif({{ letters_only('grandfather_name') }}, '')      as grandfather_name,

    {{ blank_to_null('sex') }}                              as sex_raw,
    case
        when upper(trim(sex)) in ('F', 'FEMALE') then 'F'
        when upper(trim(sex)) in ('M', 'MALE') then 'M'
    end                                                     as sex,

    {{ blank_to_null('date_of_birth') }}                    as date_of_birth_raw,
    {{ parse_iso_date('date_of_birth') }}                   as date_of_birth,

    {{ blank_to_null('phone') }}                            as phone_raw,
    case
        when {{ full_match('phone_9', '[79][0-9]{8}') }} then phone_9
    end                                                     as phone,

    case
        when {{ full_match('id_number', '[0-9]{12}') }} then id_number
    end                                                     as id_number,

    {{ blank_to_null('region') }}                           as region,
    {{ blank_to_null('zone') }}                             as zone,
    {{ blank_to_null('woreda') }}                           as woreda,
    {{ blank_to_null('kebele') }}                           as kebele,

    {{ safe_int('household_size') }}                        as household_size,
    {{ parse_iso_date('registration_date') }}               as registration_date,
    {{ blank_to_null('registration_date') }}                as registration_date_raw,
    enumerator_id
from phone_clean
