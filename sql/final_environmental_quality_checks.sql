WITH source AS (
    SELECT *
    FROM read_parquet('data/processed/environmental_deaths.parquet')
),
tagged AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
        ) AS duplicate_rank
    FROM source
),
checks AS (
    SELECT
        1 AS rule_order,
        'DQ-FINAL-ELIGIBILITY-001' AS check_name,
        COUNT(*) AS checked_rows,
        COUNT(*) FILTER (
            WHERE map IS NULL
               OR TRIM(map) NOT IN ('ERANGEL', 'MIRAMAR')
               OR event_id IS NULL
               OR TRIM(event_id) = ''
               OR match_id IS NULL
               OR TRIM(match_id) = ''
               OR victim_position_x IS NULL
               OR victim_position_y IS NULL
               OR (
                   victim_position_x = 0
                   AND victim_position_y = 0
               )
               OR victim_position_x < 0
               OR victim_position_y < 0
               OR victim_position_x > 816000
               OR victim_position_y > 816000
               OR __DATE_COLUMN__ IS NULL
               OR killed_by NOT IN ('Falling', 'Drown')
               OR duplicate_rank > 1
        ) AS error_count
    FROM tagged

    UNION ALL

    SELECT
        2,
        'DQ-EVENT-ID-001',
        COUNT(*),
        COUNT(*) FILTER (
            WHERE event_id IS NULL
               OR TRIM(event_id) = ''
        )
    FROM tagged

    UNION ALL

    SELECT
        3,
        'DQ-MAP-001',
        COUNT(*),
        COUNT(*) FILTER (
            WHERE map IS NULL
               OR TRIM(map) NOT IN ('ERANGEL', 'MIRAMAR')
        )
    FROM tagged

    UNION ALL

    SELECT
        4,
        'DQ-MATCH-001',
        COUNT(*),
        COUNT(*) FILTER (
            WHERE match_id IS NULL
               OR TRIM(match_id) = ''
        )
    FROM tagged

    UNION ALL

    SELECT
        5,
        'DQ-COORD-NULL-001',
        COUNT(*),
        COUNT(*) FILTER (
            WHERE victim_position_x IS NULL
               OR victim_position_y IS NULL
        )
    FROM tagged

    UNION ALL

    SELECT
        6,
        'DQ-COORD-002',
        COUNT(*),
        COUNT(*) FILTER (
            WHERE victim_position_x = 0
              AND victim_position_y = 0
        )
    FROM tagged

    UNION ALL

    SELECT
        7,
        'DQ-COORD-001',
        COUNT(*),
        COUNT(*) FILTER (
            WHERE victim_position_x < 0
               OR victim_position_y < 0
               OR victim_position_x > 816000
               OR victim_position_y > 816000
        )
    FROM tagged

    UNION ALL

    SELECT
        8,
        'DQ-DATE-001',
        COUNT(*),
        COUNT(*) FILTER (WHERE __DATE_COLUMN__ IS NULL)
    FROM tagged

    UNION ALL

    SELECT
        9,
        'DQ-CAUSE-001',
        COUNT(*),
        COUNT(*) FILTER (
            WHERE killed_by NOT IN ('Falling', 'Drown')
               OR killed_by IS NULL
        )
    FROM tagged

    UNION ALL

    SELECT
        10,
        'DQ-DUP-001',
        COUNT(*),
        COUNT(*) FILTER (WHERE duplicate_rank > 1)
    FROM tagged
)
SELECT
    check_name,
    CAST(checked_rows AS BIGINT) AS checked_rows,
    CAST(error_count AS BIGINT) AS error_count
FROM checks
ORDER BY rule_order;
