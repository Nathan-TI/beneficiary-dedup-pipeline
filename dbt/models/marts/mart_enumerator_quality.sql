-- Who needs retraining? Data-quality and duplicate rates per enumerator.
with f as (
    select * from {{ ref('fct_registrations') }}
)
select
    enumerator_id,
    count(*)                                                                   as registrations,
    sum(case when has_dq_issue then 1 else 0 end)                              as records_with_issues,
    round(100.0 * sum(case when has_dq_issue then 1 else 0 end) / count(*), 1) as issue_rate_pct,
    sum(case when is_duplicate then 1 else 0 end)                              as duplicate_registrations,
    round(100.0 * sum(case when is_duplicate then 1 else 0 end) / count(*), 1) as duplicate_rate_pct,
    round(100.0 * sum(case when has_valid_phone then 1 else 0 end) / count(*), 1) as valid_phone_pct
from f
group by enumerator_id
