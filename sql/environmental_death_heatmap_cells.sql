-- 환경 사망 지도 히트맵용 100m 격자 데이터
--
-- 맵과 사망 원인별 상위 400개 격자만 HTML에 포함해 파일 크기를 제한한다.
-- 색 강도는 각 맵·원인 조합 내부에서만 비교한다.

WITH cells AS (
    SELECT
        map,
        killed_by,
        FLOOR(victim_position_x / 10_000)::INTEGER AS grid_x,
        FLOOR(victim_position_y / 10_000)::INTEGER AS grid_y,
        COUNT(*) AS death_count,
        COUNT(DISTINCT match_id) AS match_count,
        COUNT(DISTINCT date) AS date_count
    FROM read_parquet(
        'data/processed/environmental_deaths.parquet'
    )
    GROUP BY
        map,
        killed_by,
        grid_x,
        grid_y
),
ranked_cells AS (
    SELECT
        *,
        SUM(death_count) OVER (
            PARTITION BY map, killed_by
        ) AS cause_total,
        ROW_NUMBER() OVER (
            PARTITION BY map, killed_by
            ORDER BY
                death_count DESC,
                match_count DESC,
                grid_x,
                grid_y
        ) AS heat_rank
    FROM cells
)
SELECT
    map,
    killed_by,
    100 AS grid_size_m,
    grid_x,
    grid_y,
    death_count,
    match_count,
    date_count,
    ROUND(
        death_count::DOUBLE / cause_total * 100,
        4
    ) AS share_pct,
    heat_rank
FROM ranked_cells
WHERE heat_rank <= 400
ORDER BY
    map,
    killed_by,
    heat_rank;
