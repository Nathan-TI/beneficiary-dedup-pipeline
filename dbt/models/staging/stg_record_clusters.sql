select
    cast(record_id as {{ dbt.type_string() }})  as record_id,
    cast(cluster_id as {{ dbt.type_string() }}) as person_key
from {{ source('raw', 'record_clusters') }}
