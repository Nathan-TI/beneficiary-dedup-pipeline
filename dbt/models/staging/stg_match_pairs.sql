select
    record_id_a,
    record_id_b,
    cast(match_score as {{ dbt.type_float() }}) as match_score,
    decision
from {{ source('raw', 'match_pairs') }}
