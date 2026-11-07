-- Every raw registration must land in the fact table with a person attached.
select r.record_id
from {{ ref('stg_registrations') }} r
left join {{ ref('fct_registrations') }} f on r.record_id = f.record_id
where f.record_id is null or f.person_key is null
