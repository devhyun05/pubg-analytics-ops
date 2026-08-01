-- 환경 사망 250m 후보와 전역 100m 후보의 해상도 비교
--
-- 모든 100m 격자는 동일한 크기로 계산한다. 100m 후보가 여러 250m 후보와
-- 겹치면 겹치는 면적이 가장 큰 후보를 연결하고, 동률이면 250m 순위가 높은
-- 후보를 연결한다.

WITH overlap_pairs AS (
    SELECT
        detail.map,
        detail.killed_by,
        detail.grid_x AS grid_100_x,
        detail.grid_y AS grid_100_y,
        parent.grid_x AS grid_250_x,
        parent.grid_y AS grid_250_y,
        parent.hotspot_candidate_rank AS parent_candidate_rank,
        parent.grid_min_x_m AS parent_min_x_m,
        parent.grid_max_x_m AS parent_max_x_m,
        parent.grid_min_y_m AS parent_min_y_m,
        parent.grid_max_y_m AS parent_max_y_m,
        (
            GREATEST(
                0,
                LEAST(detail.grid_max_x_m, parent.grid_max_x_m)
                - GREATEST(detail.grid_min_x_m, parent.grid_min_x_m)
            )
            * GREATEST(
                0,
                LEAST(detail.grid_max_y_m, parent.grid_max_y_m)
                - GREATEST(detail.grid_min_y_m, parent.grid_min_y_m)
            )
        )::DOUBLE AS overlap_area_m2,
        (
            (detail.grid_max_x_m - detail.grid_min_x_m)
            * (detail.grid_max_y_m - detail.grid_min_y_m)
        )::DOUBLE AS detail_area_m2
    FROM environmental_death_grid_candidates_100m AS detail
    INNER JOIN environmental_death_grid_candidates_250m AS parent
        ON detail.map = parent.map
        AND detail.killed_by = parent.killed_by
        AND detail.grid_min_x_m < parent.grid_max_x_m
        AND detail.grid_max_x_m > parent.grid_min_x_m
        AND detail.grid_min_y_m < parent.grid_max_y_m
        AND detail.grid_max_y_m > parent.grid_min_y_m
),
best_parent AS (
    SELECT *
    FROM overlap_pairs
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY
            map,
            killed_by,
            grid_100_x,
            grid_100_y
        ORDER BY
            overlap_area_m2 DESC,
            parent_candidate_rank,
            grid_250_x,
            grid_250_y
    ) = 1
),
labeled_candidates AS (
    SELECT
        CONCAT(
            CASE detail.map
                WHEN 'ERANGEL' THEN 'ERA'
                WHEN 'MIRAMAR' THEN 'MIR'
                ELSE detail.map
            END,
            '-',
            CASE detail.killed_by
                WHEN 'Drown' THEN 'DRO'
                WHEN 'Falling' THEN 'FAL'
                ELSE detail.killed_by
            END,
            '-100-G',
            detail.grid_x,
            '-',
            detail.grid_y
        ) AS candidate_id_100m,
        detail.map,
        CASE detail.map
            WHEN 'ERANGEL' THEN '에란겔'
            WHEN 'MIRAMAR' THEN '미라마'
            ELSE detail.map
        END AS map_name_ko,
        detail.killed_by,
        CASE detail.killed_by
            WHEN 'Drown' THEN '익사'
            WHEN 'Falling' THEN '추락'
            ELSE detail.killed_by
        END AS death_cause_ko,
        detail.grid_x AS grid_x_100m,
        detail.grid_y AS grid_y_100m,
        CONCAT(
            'X ',
            ROUND(detail.grid_min_x_m / 1_000.0, 2),
            '~',
            ROUND(detail.grid_max_x_m / 1_000.0, 2),
            'km, Y ',
            ROUND(detail.grid_min_y_m / 1_000.0, 2),
            '~',
            ROUND(detail.grid_max_y_m / 1_000.0, 2),
            'km'
        ) AS coordinate_range_100m,
        detail.death_count,
        detail.distinct_match_count,
        detail.distinct_date_count,
        detail.first_death_date AS observed_from,
        detail.last_death_date AS observed_to,
        detail.deaths_per_match AS deaths_per_affected_match,
        detail.death_share_pct,
        detail.hotspot_candidate_rank AS candidate_rank_100m,
        parent.grid_250_x,
        parent.grid_250_y,
        parent.parent_candidate_rank AS candidate_rank_250m,
        parent.overlap_area_m2,
        parent.detail_area_m2
    FROM environmental_death_grid_candidates_100m AS detail
    LEFT JOIN best_parent AS parent
        ON detail.map = parent.map
        AND detail.killed_by = parent.killed_by
        AND detail.grid_x = parent.grid_100_x
        AND detail.grid_y = parent.grid_100_y
),
classified_candidates AS (
    SELECT
        *,
        ROUND(
            overlap_area_m2
            / NULLIF(detail_area_m2, 0)
            * 100,
            2
        ) AS overlap_with_250m_pct,
        CASE
            WHEN candidate_rank_250m <= 3
                THEN '250m 우선 후보와 일치'
            WHEN candidate_rank_250m <= 10
                THEN '250m 상위 후보와 일치'
            ELSE '100m 신규 후보'
        END AS resolution_status
    FROM labeled_candidates
),
reported_candidates AS (
    SELECT
        *,
        CONCAT(
            map_name_ko,
            ' ',
            death_cause_ko,
            ' 100m ',
            candidate_rank_100m,
            '순위 후보(',
            coordinate_range_100m,
            '): ',
            death_count,
            '건, ',
            distinct_match_count,
            '개 경기, ',
            distinct_date_count,
            '개 날짜에서 관측, 원인 내 비중 ',
            ROUND(death_share_pct, 2),
            '%. ',
            CASE
                WHEN candidate_rank_250m IS NULL
                    THEN '250m 상위 10순위와 겹치지 않는 신규 후보.'
                ELSE CONCAT(
                    '250m ',
                    candidate_rank_250m,
                    '순위 후보와 ',
                    overlap_with_250m_pct,
                    '% 겹침.'
                )
            END
        ) AS report_summary
    FROM classified_candidates
)
SELECT
    candidate_id_100m,
    map_name_ko,
    death_cause_ko,
    coordinate_range_100m,
    death_count,
    distinct_match_count,
    distinct_date_count,
    observed_from,
    observed_to,
    deaths_per_affected_match,
    death_share_pct,
    candidate_rank_100m,
    grid_x_100m,
    grid_y_100m,
    grid_250_x,
    grid_250_y,
    candidate_rank_250m,
    overlap_with_250m_pct,
    resolution_status,
    report_summary,
    map,
    killed_by
FROM reported_candidates
ORDER BY
    map,
    killed_by,
    candidate_rank_100m,
    grid_x_100m,
    grid_y_100m;
