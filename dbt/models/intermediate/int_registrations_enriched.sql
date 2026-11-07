-- Registration grain: cleaned fields + the person each record belongs to + issue counts + survivorship rank.
with registrations as (
    select * from {{ ref('stg_registrations') }}
),

clusters as (
    select * from {{ ref('stg_record_clusters') }}
),

issues as (
    select
        record_id,
        count(*)                                                as dq_issue_count,
        sum(case when severity = 'critical' then 1 else 0 end)  as dq_critical_count
    from {{ ref('int_dq_issues') }}
    group by record_id
),

joined as (
    select
        r.*,
        c.person_key,
        coalesce(i.dq_issue_count, 0)    as dq_issue_count,
        coalesce(i.dq_critical_count, 0) as dq_critical_count,
        -- Survivorship score: the most complete record represents the person.
          (case when r.first_name is not null then 1 else 0 end)
        + (case when r.father_name is not null then 1 else 0 end)
        + (case when r.grandfather_name is not null then 1 else 0 end)
        + (case when r.sex is not null then 1 else 0 end)
        + (case when r.date_of_birth is not null then 1 else 0 end)
        + (case when r.phone is not null then 1 else 0 end)
        + (case when r.id_number is not null then 1 else 0 end)
        - coalesce(i.dq_critical_count, 0) as completeness_score
    from registrations r
    left join clusters c on r.record_id = c.record_id
    left join issues i on r.record_id = i.record_id
)

select
    *,
    row_number() over (
        partition by person_key
        order by completeness_score desc, registration_date desc, record_id
    ) as survivorship_rank
from joined
