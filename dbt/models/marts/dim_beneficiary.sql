-- One row per real person (golden record). Fields come from the most complete registration;
-- contact fields fall back to any other registration of the same person when the survivor lacks them.
with enriched as (
    select * from {{ ref('int_registrations_enriched') }}
),

survivor as (
    select * from enriched where survivorship_rank = 1
),

person_rollup as (
    select
        person_key,
        count(*)                as registration_count,
        min(registration_date)  as first_registered_on,
        max(registration_date)  as last_registered_on,
        max(phone)              as any_phone,
        max(id_number)          as any_id_number,
        max(grandfather_name)   as any_grandfather_name,
        sum(dq_issue_count)     as dq_issue_count
    from enriched
    group by person_key
)

select
    s.person_key,
    s.record_id                                           as surviving_record_id,
    s.first_name,
    s.father_name,
    coalesce(s.grandfather_name, p.any_grandfather_name)  as grandfather_name,
    s.sex,
    s.date_of_birth,
    coalesce(s.phone, p.any_phone)                        as phone,
    coalesce(s.id_number, p.any_id_number)                as id_number,
    s.region,
    s.zone,
    s.woreda,
    s.kebele,
    s.household_size,
    p.registration_count,
    p.registration_count > 1                              as had_duplicates,
    p.first_registered_on,
    p.last_registered_on,
    p.dq_issue_count
from survivor s
join person_rollup p on s.person_key = p.person_key
