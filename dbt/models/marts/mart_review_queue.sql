-- Borderline pairs for a human reviewer, laid out side by side.
with pairs as (
    select * from {{ ref('stg_match_pairs') }} where decision = 'review'
),
r as (
    select * from {{ ref('stg_registrations') }}
)
select
    p.record_id_a,
    p.record_id_b,
    p.match_score,
    a.first_name       as first_name_a,       b.first_name       as first_name_b,
    a.father_name      as father_name_a,      b.father_name      as father_name_b,
    a.grandfather_name as grandfather_name_a, b.grandfather_name as grandfather_name_b,
    a.date_of_birth    as date_of_birth_a,    b.date_of_birth    as date_of_birth_b,
    a.phone            as phone_a,            b.phone            as phone_b,
    a.kebele           as kebele_a,           b.kebele           as kebele_b
from pairs p
join r a on p.record_id_a = a.record_id
join r b on p.record_id_b = b.record_id
