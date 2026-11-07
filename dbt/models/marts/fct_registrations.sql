-- Registration grain fact table: every record, the person it resolved to, and its quality flags.
select
    record_id,
    person_key,
    enumerator_id,
    region,
    zone,
    woreda,
    kebele,
    registration_date,
    survivorship_rank = 1      as is_surviving_record,
    survivorship_rank > 1      as is_duplicate,
    dq_issue_count,
    dq_critical_count,
    dq_issue_count > 0         as has_dq_issue,
    phone is not null          as has_valid_phone,
    id_number is not null      as has_national_id
from {{ ref('int_registrations_enriched') }}
