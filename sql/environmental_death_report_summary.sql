-- 환경 사망 리포트 첫 화면에 표시할 데이터 선별 흐름과 대표 QA 후보
--
-- 100m 단순 건수 상위 후보를 재검증한 사례로 에란겔 추락 건수 2위
-- 격자의 전체 사망 대비 추락 비율과 주변 8개 격자 대비 배수를 계산한다.

WITH environmental_deaths AS (
    SELECT *
    FROM read_parquet('data/processed/environmental_deaths.parquet')
),
environmental_cells AS (
    SELECT
        map,
        killed_by,
        FLOOR(victim_position_x / 10_000)::INTEGER AS grid_x,
        FLOOR(victim_position_y / 10_000)::INTEGER AS grid_y,
        COUNT(*) AS death_count,
        COUNT(DISTINCT match_id) AS match_count,
        COUNT(DISTINCT date) AS date_count
    FROM environmental_deaths
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
        ) AS count_rank
    FROM environmental_cells
),
focus_candidate AS (
    SELECT *
    FROM ranked_cells
    WHERE map = 'ERANGEL'
      AND killed_by = 'Falling'
      AND count_rank = 2
),
raw_metrics AS (
    SELECT
        COUNT(*) AS raw_input_rows,
        COUNT(*) FILTER (
            WHERE deaths.killed_by IN ('Falling', 'Drown')
        ) AS raw_environmental_rows,
        COUNT(*) FILTER (
            WHERE deaths.map = focus.map
              AND deaths.victim_position_x >= focus.grid_x * 10_000
              AND deaths.victim_position_x < (focus.grid_x + 1) * 10_000
              AND deaths.victim_position_y >= focus.grid_y * 10_000
              AND deaths.victim_position_y < (focus.grid_y + 1) * 10_000
        ) AS cell_all_death_count,
        COUNT(*) FILTER (
            WHERE deaths.map = focus.map
              AND deaths.killed_by = focus.killed_by
              AND deaths.victim_position_x >= focus.grid_x * 10_000
              AND deaths.victim_position_x < (focus.grid_x + 1) * 10_000
              AND deaths.victim_position_y >= focus.grid_y * 10_000
              AND deaths.victim_position_y < (focus.grid_y + 1) * 10_000
        ) AS cell_cause_death_count,
        COUNT(*) FILTER (
            WHERE deaths.map = focus.map
              AND deaths.victim_position_x >= (focus.grid_x - 1) * 10_000
              AND deaths.victim_position_x < (focus.grid_x + 2) * 10_000
              AND deaths.victim_position_y >= (focus.grid_y - 1) * 10_000
              AND deaths.victim_position_y < (focus.grid_y + 2) * 10_000
              AND NOT (
                  deaths.victim_position_x >= focus.grid_x * 10_000
                  AND deaths.victim_position_x < (focus.grid_x + 1) * 10_000
                  AND deaths.victim_position_y >= focus.grid_y * 10_000
                  AND deaths.victim_position_y < (focus.grid_y + 1) * 10_000
              )
        ) AS neighbor_all_death_count,
        COUNT(*) FILTER (
            WHERE deaths.map = focus.map
              AND deaths.killed_by = focus.killed_by
              AND deaths.victim_position_x >= (focus.grid_x - 1) * 10_000
              AND deaths.victim_position_x < (focus.grid_x + 2) * 10_000
              AND deaths.victim_position_y >= (focus.grid_y - 1) * 10_000
              AND deaths.victim_position_y < (focus.grid_y + 2) * 10_000
              AND NOT (
                  deaths.victim_position_x >= focus.grid_x * 10_000
                  AND deaths.victim_position_x < (focus.grid_x + 1) * 10_000
                  AND deaths.victim_position_y >= focus.grid_y * 10_000
                  AND deaths.victim_position_y < (focus.grid_y + 1) * 10_000
              )
        ) AS neighbor_cause_death_count
    FROM read_csv_auto(
        'data/staged/deaths/kill_match_stats_final_*.csv',
        union_by_name = true
    ) AS deaths
    CROSS JOIN focus_candidate AS focus
),
detail_cells AS (
    SELECT
        FLOOR(deaths.victim_position_x / 1_000)::INTEGER AS detail_grid_x,
        FLOOR(deaths.victim_position_y / 1_000)::INTEGER AS detail_grid_y,
        COUNT(*) AS death_count
    FROM environmental_deaths AS deaths
    CROSS JOIN focus_candidate AS focus
    WHERE deaths.map = focus.map
      AND deaths.killed_by = focus.killed_by
      AND FLOOR(deaths.victim_position_x / 10_000) = focus.grid_x
      AND FLOOR(deaths.victim_position_y / 10_000) = focus.grid_y
    GROUP BY detail_grid_x, detail_grid_y
),
ranked_detail_cells AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            ORDER BY death_count DESC, detail_grid_x, detail_grid_y
        ) AS detail_rank
    FROM detail_cells
),
detail_metrics AS (
    SELECT
        MAX(death_count) FILTER (
            WHERE detail_rank = 1
        ) AS top_detail_death_count,
        SUM(death_count) FILTER (
            WHERE detail_rank <= 3
        ) AS top_three_detail_death_count
    FROM ranked_detail_cells
),
final_count AS (
    SELECT COUNT(*) AS final_analysis_rows
    FROM environmental_deaths
)
SELECT
    focus.map,
    focus.killed_by,
    focus.count_rank,
    focus.grid_x,
    focus.grid_y,
    focus.death_count,
    focus.match_count,
    focus.date_count,
    raw.raw_input_rows,
    raw.raw_environmental_rows,
    final_count.final_analysis_rows,
    raw.cell_all_death_count,
    ROUND(
        raw.cell_cause_death_count::DOUBLE
        / NULLIF(raw.cell_all_death_count, 0)
        * 100,
        2
    ) AS cell_cause_share_pct,
    raw.neighbor_all_death_count,
    raw.neighbor_cause_death_count,
    ROUND(
        raw.neighbor_cause_death_count::DOUBLE
        / NULLIF(raw.neighbor_all_death_count, 0)
        * 100,
        2
    ) AS neighbor_cause_share_pct,
    ROUND(
        (
            raw.cell_cause_death_count::DOUBLE
            / NULLIF(raw.cell_all_death_count, 0)
        )
        / NULLIF(
            raw.neighbor_cause_death_count::DOUBLE
            / NULLIF(raw.neighbor_all_death_count, 0),
            0
        ),
        2
    ) AS neighbor_lift,
    detail.top_detail_death_count,
    ROUND(
        detail.top_detail_death_count::DOUBLE
        / NULLIF(focus.death_count, 0)
        * 100,
        2
    ) AS top_detail_share_pct,
    ROUND(
        detail.top_three_detail_death_count::DOUBLE
        / NULLIF(focus.death_count, 0)
        * 100,
        2
    ) AS top_three_detail_share_pct
FROM focus_candidate AS focus
CROSS JOIN raw_metrics AS raw
CROSS JOIN detail_metrics AS detail
CROSS JOIN final_count;
