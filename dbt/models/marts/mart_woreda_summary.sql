-- Location-level view for programme teams: how many people, how many duplicates, how clean the data is.
with f as (
    select * from {{ ref('fct_registrations') }}
)
select
    region,
    zone,
    woreda,
    count(*)                                                                    as registrations,
    count(distinct person_key)                                                  as unique_people,
    round(100.0 * (count(*) - count(distinct person_key)) / count(*), 1)        as duplicate_rate_pct,
    round(100.0 * sum(case when has_dq_issue then 1 else 0 end) / count(*), 1)  as issue_rate_pct,
    round(100.0 * sum(case when has_national_id then 1 else 0 end) / count(*), 1) as national_id_coverage_pct
from f
where woreda is not null
group by region, zone, woreda
