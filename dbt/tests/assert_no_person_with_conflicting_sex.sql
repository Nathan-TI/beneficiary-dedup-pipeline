-- Flags merged people whose registrations disagree on sex. These are usually correct merges
-- (same national ID / phone) where one registration has a data-entry error, so this warns
-- instead of failing: the list goes to the field team for correction.
{{ config(severity='warn') }}

select person_key
from {{ ref('int_registrations_enriched') }}
where sex is not null
group by person_key
having count(distinct sex) > 1
