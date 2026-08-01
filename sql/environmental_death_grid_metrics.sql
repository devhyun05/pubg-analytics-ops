-- 환경 사망 250m 격자 집중 지표
--
-- 입력 좌표 단위는 cm이므로 250m를 25,000cm로 변환한다.
-- 결과의 한 행은 맵 + 사망 원인 + 250m 격자 한 칸을 의미한다.
-- 이 결과는 지형 문제를 확정하는 지표가 아니라 상세 조사 후보를 찾는 지표다.

WITH gridded_events AS (
    SELECT
        map,
        killed_by,
        match_id,
        date,
        FLOOR(victim_position_x / 25_000)::INTEGER AS grid_x,
        FLOOR(victim_position_y / 25_000)::INTEGER AS grid_y
    FROM read_parquet(
        'data/processed/environmental_deaths.parquet'
    )
),
grid_metrics AS (
    SELECT
        map,
        killed_by,
        250 AS grid_size_m,
        grid_x,
        grid_y,
        grid_x * 250 AS grid_min_x_m,
        LEAST((grid_x + 1) * 250, 8_160) AS grid_max_x_m,
        grid_y * 250 AS grid_min_y_m,
        LEAST((grid_y + 1) * 250, 8_160) AS grid_max_y_m,
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
