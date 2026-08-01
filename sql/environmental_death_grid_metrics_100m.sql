-- 환경 사망 100m 전역 격자 집중 지표
--
-- 250m 격자를 불균등하게 자르지 않고 전체 맵을 독립적인 100m 격자로
-- 다시 계산한다. 입력 좌표 단위는 cm이므로 100m를 10,000cm로 변환한다.

WITH gridded_events AS (
    SELECT
        map,
        killed_by,
        match_id,
        date,
        FLOOR(victim_position_x / 10_000)::INTEGER AS grid_x,
        FLOOR(victim_position_y / 10_000)::INTEGER AS grid_y
    FROM read_parquet(
        'data/processed/environmental_deaths.parquet'
    )
),
grid_metrics AS (
    SELECT
        map,
        killed_by,
        100 AS grid_size_m,
        grid_x,
        grid_y,
        grid_x * 100 AS grid_min_x_m,
        LEAST((grid_x + 1) * 100, 8_160) AS grid_max_x_m,
        grid_y * 100 AS grid_min_y_m,
        LEAST((grid_y + 1) * 100, 8_160) AS grid_max_y_m,
        COUNT(*) AS death_count,
        COUNT(DISTINCT match_id) AS distinct_match_count,
        COUNT(DISTINCT date) AS distinct_date_count,
        MIN(date) AS first_death_date,
        MAX(date) AS last_death_date,
        ROUND(
            COUNT(*)::DOUBLE
            / NULLIF(COUNT(DISTINCT match_id), 0),
            4
        ) AS deaths_per_match
    FROM gridded_events
    GROUP BY
        map,
        killed_by,
        grid_x,
        grid_y
),
ranked_metrics AS (
    SELECT
        *,
        ROUND(
            death_count::DOUBLE
            / SUM(death_count) OVER (PARTITION BY map, killed_by)
            * 100,
            4
        ) AS death_share_pct,
        DENSE_RANK() OVER (
            PARTITION BY map, killed_by
            ORDER BY
                distinct_match_count DESC,
                distinct_date_count DESC,
                death_count DESC
        ) AS hotspot_candidate_rank
    FROM grid_metrics
)
SELECT
    map,
    killed_by,
    grid_size_m,
    grid_x,
    grid_y,
    grid_min_x_m,
    grid_max_x_m,
    grid_min_y_m,
    grid_max_y_m,
    death_count,
    distinct_match_count,
    distinct_date_count,
    first_death_date,
    last_death_date,
    deaths_per_match,
    death_share_pct,
    hotspot_candidate_rank
FROM ranked_metrics
WHERE hotspot_candidate_rank <= 10
ORDER BY
    map,
    killed_by,
    hotspot_candidate_rank,
    grid_x,
    grid_y;
