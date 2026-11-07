-- How often each data-quality rule fails, as a share of all registrations.
with issues as (
    select * from {{ ref('int_dq_issues') }}
),
total as (
    select count(*) as n from {{ ref('stg_registrations') }}
)
select
    i.rule_code,
    i.rule_name,
    i.severity,
    count(distinct i.record_id)                                   as records_failing,
    round(100.0 * count(distinct i.record_id) / max(t.n), 2)      as pct_of_registrations
from issues i
cross join total t
group by i.rule_code, i.rule_name, i.severity
