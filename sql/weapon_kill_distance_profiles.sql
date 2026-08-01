WITH death_events AS (
    SELECT
        map,
        killed_by,
        CASE
            WHEN killed_by IN ('S686', 'S1897', 'S12K') THEN 'Shotgun'
            WHEN killed_by IN ('Micro UZI', 'UMP9', 'Vector', 'Tommy Gun') THEN 'SMG'
            WHEN killed_by IN ('AKM', 'M16A4', 'M416', 'SCAR-L', 'AUG', 'Groza') THEN 'AR'
            WHEN killed_by IN ('Mini 14', 'SKS', 'Mk14', 'VSS') THEN 'DMR'
            WHEN killed_by IN ('Kar98k', 'M24', 'AWM', 'Win94') THEN 'SR'
            WHEN killed_by IN ('DP-28', 'M249') THEN 'LMG'
            WHEN killed_by IN ('P18C', 'P1911', 'P92', 'R1895', 'R45') THEN 'Pistol'
            WHEN killed_by = 'Crossbow' THEN 'Special'
        END AS weapon_class,
        SQRT(
            POW(killer_position_x - victim_position_x, 2)
            + POW(killer_position_y - victim_position_y, 2)
        ) / 100.0 AS death_distance_m
    FROM read_csv_auto(
        'data/staged/deaths/kill_match_stats_final_*.csv',
        union_by_name = true
    )
    WHERE map IN ('ERANGEL', 'MIRAMAR')
      AND killer_name IS NOT NULL
      AND victim_name IS NOT NULL
      AND killer_name <> victim_name
      AND killer_position_x IS NOT NULL
      AND killer_position_y IS NOT NULL
      AND victim_position_x IS NOT NULL
      AND victim_position_y IS NOT NULL
      AND NOT (killer_position_x = 0 AND killer_position_y = 0)
      AND NOT (victim_position_x = 0 AND victim_position_y = 0)
      AND killer_position_x BETWEEN 0 AND 816000
      AND killer_position_y BETWEEN 0 AND 816000
      AND victim_position_x BETWEEN 0 AND 816000
      AND victim_position_y BETWEEN 0 AND 816000
),
valid_firearm_events AS (
    SELECT *
    FROM death_events
    WHERE weapon_class IS NOT NULL
      AND death_distance_m BETWEEN 0 AND 2000
),
profiles AS (
    SELECT
        CASE WHEN GROUPING(map) = 1 THEN 'ALL' ELSE map END AS scope,
        weapon_class,
        killed_by,
        COUNT(*) AS event_count,
        QUANTILE_CONT(death_distance_m, 0.5) AS median_distance_m,
        QUANTILE_CONT(death_distance_m, 0.75) AS p75_distance_m,
        QUANTILE_CONT(death_distance_m, 0.9) AS p90_distance_m,
        QUANTILE_CONT(death_distance_m, 0.99) AS p99_distance_m,
        COUNT(*) FILTER (WHERE death_distance_m >= 100) * 1.0 / COUNT(*)
            AS share_above_100m,
        COUNT(*) FILTER (WHERE death_distance_m >= 300) * 1.0 / COUNT(*)
            AS share_above_300m
    FROM valid_firearm_events
    GROUP BY GROUPING SETS (
        (map, weapon_class, killed_by),
        (weapon_class, killed_by),
        (map, weapon_class),
        (weapon_class)
    )
)
SELECT
    scope,
    weapon_class,
    killed_by,
    event_count,
    ROUND(median_distance_m, 1) AS median_distance_m,
    ROUND(p75_distance_m, 1) AS p75_distance_m,
    ROUND(p90_distance_m, 1) AS p90_distance_m,
    ROUND(p99_distance_m, 1) AS p99_distance_m,
    ROUND(share_above_100m * 100, 2) AS share_above_100m_pct,
    ROUND(share_above_300m * 100, 2) AS share_above_300m_pct,
    (SELECT COUNT(*) FROM valid_firearm_events) AS valid_event_count
FROM profiles
WHERE killed_by IS NULL OR event_count >= 10000
ORDER BY
    CASE scope WHEN 'ALL' THEN 0 WHEN 'ERANGEL' THEN 1 ELSE 2 END,
    CASE weapon_class
        WHEN 'Shotgun' THEN 1
        WHEN 'SMG' THEN 2
        WHEN 'AR' THEN 3
        WHEN 'DMR' THEN 4
        WHEN 'SR' THEN 5
        WHEN 'LMG' THEN 6
        WHEN 'Pistol' THEN 7
        ELSE 8
    END,
    killed_by NULLS FIRST;
