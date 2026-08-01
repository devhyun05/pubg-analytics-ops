-- 상위 1·2·3위 100m 격자 내부의 10m 상세 분포
--
-- 각 100m 후보를 10m × 10m로 다시 나누고, 사망 건수에 따라
-- 확대 지도에서 색 강도를 다르게 표현하기 위한 데이터다.

WITH events AS (
    SELECT
        map,
        killed_by,
        match_id,
        date,
        FLOOR(victim_position_x / 10_000)::INTEGER AS parent_grid_x,
        FLOOR(victim_position_y / 10_000)::INTEGER AS parent_grid_y,
        FLOOR(victim_position_x / 1_000)::INTEGER AS detail_grid_x,
        FLOOR(victim_position_y / 1_000)::INTEGER AS detail_grid_y
    FROM read_parquet(
        'data/processed/environmental_deaths.parquet'
    )
),
parent_cells AS (
    SELECT
        map,
        killed_by,
        parent_grid_x,
        parent_grid_y,
        COUNT(*) AS parent_death_count,
        COUNT(DISTINCT match_id) AS parent_match_count
    FROM events
    GROUP BY
        map,
        killed_by,
        parent_grid_x,
        parent_grid_y
),
ranked_parents AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY map, killed_by
            ORDER BY
                parent_death_count DESC,
                parent_match_count DESC,
                parent_grid_x,
                parent_grid_y
        ) AS parent_rank
    FROM parent_cells
),
top_parents AS (
    SELECT *
    FROM ranked_parents
    WHERE parent_rank <= 3
),
detail_cells AS (
    SELECT
        events.map,
        events.killed_by,
        top_parents.parent_rank,
        top_parents.parent_grid_x,
        top_parents.parent_grid_y,
        events.detail_grid_x,
        events.detail_grid_y,
        COUNT(*) AS death_count,
        COUNT(DISTINCT events.match_id) AS match_count,
        COUNT(DISTINCT events.date) AS date_count,
        top_parents.parent_death_count
    FROM events
    INNER JOIN top_parents
        ON events.map = top_parents.map
        AND events.killed_by = top_parents.killed_by
        AND events.parent_grid_x = top_parents.parent_grid_x
        AND events.parent_grid_y = top_parents.parent_grid_y
    GROUP BY
        events.map,
        events.killed_by,
        top_parents.parent_rank,
        top_parents.parent_grid_x,
        top_parents.parent_grid_y,
        events.detail_grid_x,
        events.detail_grid_y,
        top_parents.parent_death_count
),
ranked_details AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY map, killed_by, parent_rank
            ORDER BY
                death_count DESC,
                match_count DESC,
                detail_grid_x,
                detail_grid_y
        ) AS detail_rank
    FROM detail_cells
)
SELECT
    map,
    killed_by,
    parent_rank,
    parent_grid_x,
    parent_grid_y,
    10 AS grid_size_m,
    detail_grid_x,
    detail_grid_y,
    death_count,
    match_count,
    date_count,
    ROUND(
        death_count::DOUBLE / parent_death_count * 100,
        4
    ) AS parent_share_pct,
    detail_rank
FROM ranked_details
ORDER BY
    map,
    killed_by,
    parent_rank,
    detail_rank;
