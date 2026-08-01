-- 환경 사망 250m 후보의 보고서용 표현 계층
--
-- 이 SQL은 scripts/build_environmental_death_hotspot_report.py가 생성한
-- environmental_death_grid_candidates_250m TEMP VIEW를 입력으로 사용한다.

WITH labeled_candidates AS (
    SELECT
        CONCAT(
            CASE map
                WHEN 'ERANGEL' THEN 'ERA'
                WHEN 'MIRAMAR' THEN 'MIR'
                ELSE map
            END,
            '-',
            CASE killed_by
                WHEN 'Drown' THEN 'DRO'
                WHEN 'Falling' THEN 'FAL'
                ELSE killed_by
            END,
            '-G',
            grid_x,
            '-',
            grid_y
        ) AS candidate_id,
        map,
        CASE map
            WHEN 'ERANGEL' THEN '에란겔'
            WHEN 'MIRAMAR' THEN '미라마'
            ELSE map
        END AS map_name_ko,
        killed_by,
        CASE killed_by
            WHEN 'Drown' THEN '익사'
            WHEN 'Falling' THEN '추락'
            ELSE killed_by
        END AS death_cause_ko,
        grid_x,
        grid_y,
        CONCAT(
            'X ',
            ROUND(grid_min_x_m / 1_000.0, 2),
            '~',
            ROUND(grid_max_x_m / 1_000.0, 2),
            'km, Y ',
            ROUND(grid_min_y_m / 1_000.0, 2),
            '~',
            ROUND(grid_max_y_m / 1_000.0, 2),
            'km'
        ) AS coordinate_range_km,
        death_count,
        distinct_match_count,
        distinct_date_count,
        first_death_date AS observed_from,
        last_death_date AS observed_to,
        deaths_per_match AS deaths_per_affected_match,
        death_share_pct,
        hotspot_candidate_rank AS candidate_rank
    FROM environmental_death_grid_candidates_250m
),
report_rows AS (
    SELECT
        *,
        CONCAT(
            map_name_ko,
            ' ',
            death_cause_ko,
            ' ',
            candidate_rank,
            '순위 후보(',
            coordinate_range_km,
            '): ',
            death_count,
            '건, ',
            distinct_match_count,
            '개 경기, ',
            distinct_date_count,
            '개 날짜에서 관측, 원인 내 비중 ',
            ROUND(death_share_pct, 2),
            '%. 100m 상세 분석 후보.'
        ) AS report_summary
    FROM labeled_candidates
)
SELECT
    candidate_id,
    map_name_ko,
    death_cause_ko,
    coordinate_range_km,
    death_count,
    distinct_match_count,
    distinct_date_count,
    observed_from,
    observed_to,
    deaths_per_affected_match,
    death_share_pct,
    candidate_rank,
    report_summary,
    map,
    killed_by,
    grid_x,
    grid_y
FROM report_rows
ORDER BY
    map,
    killed_by,
    candidate_rank,
    grid_x,
    grid_y;
