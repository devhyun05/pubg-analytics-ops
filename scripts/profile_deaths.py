from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEATHS_DIR = PROJECT_ROOT / "data" / "staged" / "deaths"
DEATHS_PATTERN = "kill_match_stats_final_*.csv"
MAP_COORDINATE_MAX = 816_000.0


def format_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.4f}"
    return str(value)


def print_table(columns: list[str], rows: list[tuple[Any, ...]]) -> None:
    rendered_rows = [[format_value(value) for value in row] for row in rows]
    widths = [len(column) for column in columns]

    for row in rendered_rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    header = " | ".join(
        column.ljust(widths[index]) for index, column in enumerate(columns)
    )
    divider = "-+-".join("-" * width for width in widths)

    print(header)
    print(divider)
    for row in rendered_rows:
        print(
            " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        )


def fetch_table(
    connection: duckdb.DuckDBPyConnection,
    query: str,
) -> tuple[list[str], list[tuple[Any, ...]]]:
    cursor = connection.execute(query)
    columns = [description[0] for description in cursor.description]
    return columns, cursor.fetchall()


def create_source_view(
    connection: duckdb.DuckDBPyConnection,
    csv_glob: str,
) -> None:
    escaped_glob = csv_glob.replace("'", "''")
    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW deaths_profile_source AS
        SELECT
            filename,
            killed_by AS killed_by_raw,
            NULLIF(TRIM(killed_by), '') AS killed_by,
            map AS map_raw,
            NULLIF(TRIM(map), '') AS map,
            match_id AS match_id_raw,
            NULLIF(TRIM(match_id), '') AS match_id,
            TRY_CAST(NULLIF(TRIM(time), '') AS DOUBLE) AS death_time,
            NULLIF(TRIM(killer_name), '') AS killer_name,
            NULLIF(TRIM(victim_name), '') AS victim_name,
            TRY_CAST(
                NULLIF(TRIM(killer_position_x), '') AS DOUBLE
            ) AS killer_x,
            TRY_CAST(
                NULLIF(TRIM(killer_position_y), '') AS DOUBLE
            ) AS killer_y,
            TRY_CAST(
                NULLIF(TRIM(victim_placement), '') AS DOUBLE
            ) AS victim_placement,
            victim_position_x AS victim_x_raw,
            victim_position_y AS victim_y_raw,
            TRY_CAST(
                NULLIF(TRIM(victim_position_x), '') AS DOUBLE
            ) AS victim_x,
            TRY_CAST(
                NULLIF(TRIM(victim_position_y), '') AS DOUBLE
            ) AS victim_y
        FROM read_csv_auto(
            '{escaped_glob}',
            all_varchar = true,
            filename = true,
            union_by_name = true
        )
        """
    )


def profile_core(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, int]:
    cursor = connection.execute(
        f"""
        SELECT
            COUNT(*)::BIGINT AS total_rows,
            COUNT(DISTINCT match_id)::BIGINT AS distinct_match_ids,
            COUNT_IF(killed_by_raw IS NULL)::BIGINT AS null_killed_by,
            COUNT_IF(
                killed_by_raw IS NOT NULL
                AND TRIM(killed_by_raw) = ''
            )::BIGINT AS blank_killed_by,
            COUNT_IF(killed_by IS NULL)::BIGINT AS missing_killed_by,
            COUNT_IF(map_raw IS NULL)::BIGINT AS null_map,
            COUNT_IF(
                map_raw IS NOT NULL
                AND TRIM(map_raw) = ''
            )::BIGINT AS blank_map,
            COUNT_IF(map IS NULL)::BIGINT AS missing_map,
            COUNT_IF(match_id_raw IS NULL)::BIGINT AS null_match_id,
            COUNT_IF(
                match_id_raw IS NOT NULL
                AND TRIM(match_id_raw) = ''
            )::BIGINT AS blank_match_id,
            COUNT_IF(match_id IS NULL)::BIGINT AS missing_match_id,
            COUNT_IF(victim_x_raw IS NULL)::BIGINT AS null_victim_x,
            COUNT_IF(
                victim_x_raw IS NOT NULL
                AND TRIM(victim_x_raw) = ''
            )::BIGINT AS blank_victim_x,
            COUNT_IF(victim_y_raw IS NULL)::BIGINT AS null_victim_y,
            COUNT_IF(
                victim_y_raw IS NOT NULL
                AND TRIM(victim_y_raw) = ''
            )::BIGINT AS blank_victim_y,
            COUNT_IF(
                victim_x_raw IS NOT NULL
                AND TRIM(victim_x_raw) <> ''
                AND victim_x IS NULL
            )::BIGINT AS invalid_numeric_victim_x,
            COUNT_IF(
                victim_y_raw IS NOT NULL
                AND TRIM(victim_y_raw) <> ''
                AND victim_y IS NULL
            )::BIGINT AS invalid_numeric_victim_y,
            COUNT_IF(
                victim_x IS NULL
                AND victim_y IS NULL
            )::BIGINT AS both_coordinates_missing,
            COUNT_IF(
                (victim_x IS NULL AND victim_y IS NOT NULL)
                OR (victim_x IS NOT NULL AND victim_y IS NULL)
            )::BIGINT AS one_coordinate_missing,
            COUNT_IF(victim_x = 0)::BIGINT AS zero_victim_x,
            COUNT_IF(victim_y = 0)::BIGINT AS zero_victim_y,
            COUNT_IF(
                victim_x = 0
                AND victim_y = 0
            )::BIGINT AS zero_zero_coordinates,
            COUNT_IF(
                victim_x < 0
                OR victim_y < 0
            )::BIGINT AS negative_coordinates,
            COUNT_IF(
                (victim_x IS NOT NULL AND NOT ISFINITE(victim_x))
                OR (victim_y IS NOT NULL AND NOT ISFINITE(victim_y))
            )::BIGINT AS non_finite_coordinates,
            COUNT_IF(
                map IN ('ERANGEL', 'MIRAMAR')
                AND (
                    victim_x < 0
                    OR victim_x > {MAP_COORDINATE_MAX}
                    OR victim_y < 0
                    OR victim_y > {MAP_COORDINATE_MAX}
                )
            )::BIGINT AS out_of_bounds_coordinates,
            COUNT_IF(
                map IN ('ERANGEL', 'MIRAMAR')
                AND victim_x < 0
            )::BIGINT AS victim_x_below_zero,
            COUNT_IF(
                map IN ('ERANGEL', 'MIRAMAR')
                AND victim_x > {MAP_COORDINATE_MAX}
            )::BIGINT AS victim_x_above_max,
            COUNT_IF(
                map IN ('ERANGEL', 'MIRAMAR')
                AND victim_y < 0
            )::BIGINT AS victim_y_below_zero,
            COUNT_IF(
                map IN ('ERANGEL', 'MIRAMAR')
                AND victim_y > {MAP_COORDINATE_MAX}
            )::BIGINT AS victim_y_above_max,
            COUNT_IF(
                killed_by IS NOT NULL
                AND map IS NOT NULL
                AND match_id IS NOT NULL
                AND victim_x IS NOT NULL
                AND victim_y IS NOT NULL
                AND ISFINITE(victim_x)
                AND ISFINITE(victim_y)
            )::BIGINT AS complete_required_fields,
            COUNT_IF(
                killed_by IN ('Falling', 'Drown')
            )::BIGINT AS environmental_rows,
            COUNT_IF(
                killed_by IN ('Falling', 'Drown')
                AND map IS NOT NULL
                AND match_id IS NOT NULL
                AND victim_x IS NOT NULL
                AND victim_y IS NOT NULL
                AND ISFINITE(victim_x)
                AND ISFINITE(victim_y)
            )::BIGINT AS complete_environmental_rows,
            COUNT_IF(
                killed_by IN ('Falling', 'Drown')
                AND victim_x = 0
                AND victim_y = 0
            )::BIGINT AS environmental_zero_zero_rows
        FROM deaths_profile_source
        """
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("The deaths profile query returned no result.")
    return {
        description[0]: int(value)
        for description, value in zip(cursor.description, row, strict=True)
    }


def print_core_profile(summary: dict[str, int]) -> None:
    total_rows = summary["total_rows"]
    no_rate_metrics = {"total_rows", "distinct_match_ids"}

    print("\n[Core profile]")
    for name, value in summary.items():
        if name in no_rate_metrics:
            print(f"{name}: {value:,}")
            continue

        rate = value / total_rows * 100 if total_rows else 0
        print(f"{name}: {value:,} ({rate:.6f}%)")


def main() -> None:
    files = sorted(DEATHS_DIR.glob(DEATHS_PATTERN))
    if not files:
        raise FileNotFoundError(
            f"No deaths CSV files matched: {DEATHS_DIR / DEATHS_PATTERN}"
        )

    started_at = perf_counter()
    connection = duckdb.connect()
    connection.execute("SET enable_progress_bar = false")
    create_source_view(
        connection,
        (DEATHS_DIR / DEATHS_PATTERN).as_posix(),
    )

    print(f"input_file_count: {len(files)}")
    for file in files:
        print(f"input_file: {file}")

    file_columns, file_rows = fetch_table(
        connection,
        """
        SELECT
            filename,
            COUNT(*)::BIGINT AS row_count
        FROM deaths_profile_source
        GROUP BY filename
        ORDER BY filename
        """,
    )
    print("\n[Rows by file]")
    print_table(file_columns, file_rows)

    summary = profile_core(connection)
    print_core_profile(summary)

    map_columns, map_rows = fetch_table(
        connection,
        f"""
        SELECT
            COALESCE(map, '<NULL_OR_BLANK>') AS map,
            COUNT(*)::BIGINT AS row_count,
            COUNT(DISTINCT match_id)::BIGINT AS distinct_match_ids,
            MIN(
                CASE WHEN ISFINITE(victim_x) THEN victim_x END
            ) AS min_victim_x,
            MAX(
                CASE WHEN ISFINITE(victim_x) THEN victim_x END
            ) AS max_victim_x,
            MIN(
                CASE WHEN ISFINITE(victim_y) THEN victim_y END
            ) AS min_victim_y,
            MAX(
                CASE WHEN ISFINITE(victim_y) THEN victim_y END
            ) AS max_victim_y,
            COUNT_IF(
                victim_x = 0
                AND victim_y = 0
            )::BIGINT AS zero_zero_rows,
            COUNT_IF(
                map IN ('ERANGEL', 'MIRAMAR')
                AND (
                    victim_x < 0
                    OR victim_x > {MAP_COORDINATE_MAX}
                    OR victim_y < 0
                    OR victim_y > {MAP_COORDINATE_MAX}
                )
            )::BIGINT AS out_of_bounds_rows,
            COUNT_IF(killed_by = 'Falling')::BIGINT AS falling_rows,
            COUNT_IF(killed_by = 'Drown')::BIGINT AS drown_rows
        FROM deaths_profile_source
        GROUP BY map
        ORDER BY row_count DESC
        """,
    )
    print("\n[Profile by map]")
    print_table(map_columns, map_rows)

    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE match_map_profile AS
        SELECT
            match_id,
            COUNT(*)::BIGINT AS death_rows,
            COUNT_IF(map IS NULL)::BIGINT AS missing_map_rows,
            COUNT(DISTINCT map)::BIGINT AS distinct_known_maps,
            MIN(map) FILTER (
                WHERE map IS NOT NULL
            ) AS only_known_map
        FROM deaths_profile_source
        GROUP BY match_id
        """
    )
    map_match_columns, map_match_rows = fetch_table(
        connection,
        """
        SELECT
            SUM(death_rows)::BIGINT AS total_rows,
            SUM(missing_map_rows)::BIGINT AS missing_map_rows,
            COUNT_IF(
                missing_map_rows > 0
            )::BIGINT AS matches_with_missing_map,
            SUM(
                CASE
                    WHEN missing_map_rows > 0
                         AND distinct_known_maps = 1
                    THEN missing_map_rows
                    ELSE 0
                END
            )::BIGINT AS recoverable_rows,
            SUM(
                CASE
                    WHEN missing_map_rows > 0
                         AND distinct_known_maps = 0
                    THEN missing_map_rows
                    ELSE 0
                END
            )::BIGINT AS unrecoverable_rows,
            COUNT_IF(
                missing_map_rows > 0
                AND distinct_known_maps = 0
            )::BIGINT AS all_missing_matches,
            COUNT_IF(
                distinct_known_maps > 1
            )::BIGINT AS conflicting_map_matches
        FROM match_map_profile
        """,
    )
    print("\n[Map completeness by match]")
    print_table(map_match_columns, map_match_rows)

    environmental_map_columns, environmental_map_rows = fetch_table(
        connection,
        """
        SELECT
            source.killed_by,
            COUNT(*)::BIGINT AS missing_map_rows,
            COUNT_IF(
                profile.distinct_known_maps = 1
            )::BIGINT AS recoverable_rows,
            COUNT_IF(
                profile.distinct_known_maps = 0
            )::BIGINT AS unrecoverable_rows,
            COUNT_IF(
                profile.distinct_known_maps > 1
            )::BIGINT AS conflict_rows
        FROM deaths_profile_source AS source
        INNER JOIN match_map_profile AS profile USING (match_id)
        WHERE source.map IS NULL
          AND source.killed_by IN ('Falling', 'Drown')
        GROUP BY source.killed_by
        ORDER BY source.killed_by
        """,
    )
    print("\n[Environmental deaths with missing map]")
    print_table(environmental_map_columns, environmental_map_rows)

    cause_columns, cause_rows = fetch_table(
        connection,
        """
        SELECT
            COALESCE(killed_by, '<NULL_OR_BLANK>') AS killed_by,
            COUNT(*)::BIGINT AS row_count,
            COUNT(DISTINCT match_id)::BIGINT AS distinct_match_ids,
            COUNT_IF(
                victim_x IS NULL
                OR victim_y IS NULL
            )::BIGINT AS missing_coordinate_rows,
            COUNT_IF(
                victim_x = 0
                AND victim_y = 0
            )::BIGINT AS zero_zero_rows
        FROM deaths_profile_source
        GROUP BY killed_by
        ORDER BY row_count DESC, killed_by
        """,
    )
    print("\n[Profile by killed_by]")
    print_table(cause_columns, cause_rows)

    environmental_bounds_columns, environmental_bounds_rows = fetch_table(
        connection,
        f"""
        SELECT
            map,
            killed_by,
            COUNT(*)::BIGINT AS cause_rows,
            COUNT_IF(
                victim_x < 0
                OR victim_x > {MAP_COORDINATE_MAX}
                OR victim_y < 0
                OR victim_y > {MAP_COORDINATE_MAX}
            )::BIGINT AS out_of_bounds_rows,
            printf(
                '%.9f%%',
                COUNT_IF(
                    victim_x < 0
                    OR victim_x > {MAP_COORDINATE_MAX}
                    OR victim_y < 0
                    OR victim_y > {MAP_COORDINATE_MAX}
                ) * 100.0 / COUNT(*)
            ) AS out_of_bounds_rate
        FROM deaths_profile_source
        WHERE map IN ('ERANGEL', 'MIRAMAR')
          AND killed_by IN ('Falling', 'Drown')
        GROUP BY map, killed_by
        ORDER BY map, killed_by
        """,
    )
    print("\n[Environmental deaths outside map coordinate bounds]")
    print_table(environmental_bounds_columns, environmental_bounds_rows)

    bounds_example_columns, bounds_example_rows = fetch_table(
        connection,
        f"""
        SELECT
            regexp_extract(filename, '[^/]+$') AS source_file,
            killed_by,
            map,
            match_id,
            victim_x,
            victim_y,
            concat_ws(
                ', ',
                CASE WHEN victim_x < 0 THEN 'X_BELOW_0' END,
                CASE
                    WHEN victim_x > {MAP_COORDINATE_MAX}
                    THEN 'X_ABOVE_816000'
                END,
                CASE WHEN victim_y < 0 THEN 'Y_BELOW_0' END,
                CASE
                    WHEN victim_y > {MAP_COORDINATE_MAX}
                    THEN 'Y_ABOVE_816000'
                END
            ) AS violation
        FROM deaths_profile_source
        WHERE map IN ('ERANGEL', 'MIRAMAR')
          AND (
              victim_x < 0
              OR victim_x > {MAP_COORDINATE_MAX}
              OR victim_y < 0
              OR victim_y > {MAP_COORDINATE_MAX}
          )
        ORDER BY
            CASE WHEN killed_by IN ('Falling', 'Drown') THEN 0 ELSE 1 END,
            GREATEST(
                CASE WHEN victim_x < 0 THEN -victim_x ELSE 0 END,
                CASE
                    WHEN victim_x > {MAP_COORDINATE_MAX}
                    THEN victim_x - {MAP_COORDINATE_MAX}
                    ELSE 0
                END,
                CASE WHEN victim_y < 0 THEN -victim_y ELSE 0 END,
                CASE
                    WHEN victim_y > {MAP_COORDINATE_MAX}
                    THEN victim_y - {MAP_COORDINATE_MAX}
                    ELSE 0
                END
            ) DESC
        LIMIT 12
        """,
    )
    print("\n[Coordinate bounds examples]")
    print_table(bounds_example_columns, bounds_example_rows)

    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE drown_profile AS
        SELECT
            regexp_extract(filename, '[^/]+$') AS source_file,
            map,
            match_id,
            death_time,
            killer_name,
            victim_name,
            killer_x,
            killer_y,
            victim_placement,
            victim_x,
            victim_y
        FROM deaths_profile_source
        WHERE killed_by = 'Drown'
        """
    )

    drown_zero_columns, drown_zero_rows = fetch_table(
        connection,
        """
        SELECT
            COUNT(*)::BIGINT AS drown_rows,
            COUNT_IF(
                victim_x = 0 AND victim_y = 0
            )::BIGINT AS zero_zero_rows,
            printf(
                '%.9f%%',
                COUNT_IF(victim_x = 0 AND victim_y = 0)
                * 100.0 / COUNT(*)
            ) AS zero_zero_rate,
            COUNT(DISTINCT match_id)::BIGINT AS drown_matches,
            COUNT(
                DISTINCT CASE
                    WHEN victim_x = 0 AND victim_y = 0 THEN match_id
                END
            )::BIGINT AS zero_zero_matches,
            COUNT_IF(
                victim_x = 0 AND victim_y <> 0
            )::BIGINT AS only_x_zero,
            COUNT_IF(
                victim_x <> 0 AND victim_y = 0
            )::BIGINT AS only_y_zero,
            COUNT_IF(
                victim_x BETWEEN 0 AND 1000
                AND victim_y BETWEEN 0 AND 1000
                AND NOT (victim_x = 0 AND victim_y = 0)
            )::BIGINT AS nonzero_within_10m_square,
            COUNT_IF(
                victim_x BETWEEN 0 AND 10000
                AND victim_y BETWEEN 0 AND 10000
                AND NOT (victim_x = 0 AND victim_y = 0)
            )::BIGINT AS nonzero_within_100m_square
        FROM drown_profile
        """,
    )
    print("\n[Drown zero-zero summary]")
    print_table(drown_zero_columns, drown_zero_rows)

    drown_map_columns, drown_map_rows = fetch_table(
        connection,
        """
        SELECT
            COALESCE(map, '<NULL_OR_BLANK>') AS map,
            COUNT(*)::BIGINT AS drown_rows,
            COUNT_IF(
                victim_x = 0 AND victim_y = 0
            )::BIGINT AS zero_zero_rows,
            printf(
                '%.9f%%',
                COUNT_IF(victim_x = 0 AND victim_y = 0)
                * 100.0 / COUNT(*)
            ) AS zero_zero_rate,
            COUNT(
                DISTINCT CASE
                    WHEN victim_x = 0 AND victim_y = 0 THEN match_id
                END
            )::BIGINT AS zero_zero_matches
        FROM drown_profile
        GROUP BY map
        ORDER BY drown_rows DESC
        """,
    )
    print("\n[Drown zero-zero by map]")
    print_table(drown_map_columns, drown_map_rows)

    drown_file_columns, drown_file_rows = fetch_table(
        connection,
        """
        SELECT
            source_file,
            COUNT(*)::BIGINT AS drown_rows,
            COUNT_IF(
                victim_x = 0 AND victim_y = 0
            )::BIGINT AS zero_zero_rows,
            printf(
                '%.9f%%',
                COUNT_IF(victim_x = 0 AND victim_y = 0)
                * 100.0 / COUNT(*)
            ) AS zero_zero_rate
        FROM drown_profile
        GROUP BY source_file
        ORDER BY source_file
        """,
    )
    print("\n[Drown zero-zero by source file]")
    print_table(drown_file_columns, drown_file_rows)

    drown_time_columns, drown_time_rows = fetch_table(
        connection,
        """
        SELECT
            CASE
                WHEN victim_x = 0 AND victim_y = 0 THEN 'ZERO_ZERO'
                ELSE 'NON_ZERO'
            END AS position_group,
            COUNT(*)::BIGINT AS row_count,
            MIN(death_time) AS min_time,
            QUANTILE_CONT(death_time, 0.25) AS p25_time,
            MEDIAN(death_time) AS median_time,
            QUANTILE_CONT(death_time, 0.75) AS p75_time,
            QUANTILE_CONT(death_time, 0.95) AS p95_time,
            MAX(death_time) AS max_time,
            AVG(death_time) AS avg_time,
            COUNT_IF(
                death_time >= 120 AND death_time < 300
            )::BIGINT AS time_120_to_299
        FROM drown_profile
        GROUP BY position_group
        ORDER BY position_group
        """,
    )
    print("\n[Drown position groups by time]")
    print_table(drown_time_columns, drown_time_rows)

    drown_related_columns, drown_related_rows = fetch_table(
        connection,
        """
        SELECT
            CASE
                WHEN victim_x = 0 AND victim_y = 0 THEN 'ZERO_ZERO'
                ELSE 'NON_ZERO'
            END AS position_group,
            COUNT(*)::BIGINT AS row_count,
            COUNT_IF(
                killer_x = 0 AND killer_y = 0
            )::BIGINT AS killer_zero_zero,
            COUNT_IF(
                killer_x IS NULL OR killer_y IS NULL
            )::BIGINT AS killer_coordinate_missing,
            COUNT_IF(
                killer_name = victim_name
            )::BIGINT AS same_named_actor,
            COUNT_IF(killer_name IS NULL)::BIGINT AS missing_killer_name,
            COUNT_IF(
                victim_placement IS NULL
            )::BIGINT AS missing_victim_placement
        FROM drown_profile
        GROUP BY position_group
        ORDER BY position_group
        """,
    )
    print("\n[Drown position groups and related fields]")
    print_table(drown_related_columns, drown_related_rows)

    elapsed_seconds = perf_counter() - started_at
    print(f"\nelapsed_seconds: {elapsed_seconds:.4f}")
    connection.close()


if __name__ == "__main__":
    main()
