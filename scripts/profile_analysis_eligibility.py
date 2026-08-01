from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEATHS_PATTERN = (
    PROJECT_ROOT
    / "data"
    / "staged"
    / "deaths"
    / "kill_match_stats_final_*.csv"
)
AGGREGATE_PATTERN = (
    PROJECT_ROOT
    / "data"
    / "staged"
    / "aggregate"
    / "agg_match_stats_*.csv"
)


def print_result(
    title: str,
    cursor: duckdb.DuckDBPyConnection,
) -> None:
    columns = [description[0] for description in cursor.description]
    rows: list[tuple[Any, ...]] = cursor.fetchall()
    print(f"\n[{title}]")
    print(" | ".join(columns))
    for row in rows:
        rendered = ["NULL" if value is None else str(value) for value in row]
        print(" | ".join(rendered))


def create_match_dimension(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    aggregate_glob = AGGREGATE_PATTERN.as_posix().replace("'", "''")
    connection.execute(
        f"""
        CREATE TEMP TABLE dim_match AS
        SELECT
            NULLIF(TRIM(match_id), '') AS match_id,
            MIN(NULLIF(TRIM(date), '')) AS match_date,
            COUNT(
                DISTINCT NULLIF(TRIM(date), '')
            )::BIGINT AS date_count
        FROM read_csv_auto(
            '{aggregate_glob}',
            all_varchar = true,
            union_by_name = true
        )
        WHERE NULLIF(TRIM(match_id), '') IS NOT NULL
        GROUP BY NULLIF(TRIM(match_id), '')
        """
    )


def create_environmental_source(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    deaths_glob = DEATHS_PATTERN.as_posix().replace("'", "''")
    connection.execute(
        f"""
        CREATE TEMP TABLE environmental_raw AS
        SELECT
            killed_by,
            killer_name,
            killer_placement,
            killer_position_x,
            killer_position_y,
            map,
            match_id,
            time,
            victim_name,
            victim_placement,
            victim_position_x,
            victim_position_y
        FROM read_csv_auto(
            '{deaths_glob}',
            all_varchar = true,
            union_by_name = true
        )
        WHERE NULLIF(TRIM(killed_by), '') IN ('Falling', 'Drown')
        """
    )

    connection.execute(
        """
        CREATE TEMP TABLE environmental_deduplicated AS
        SELECT
            killed_by,
            killer_name,
            killer_placement,
            killer_position_x,
            killer_position_y,
            map,
            match_id,
            time,
            victim_name,
            victim_placement,
            victim_position_x,
            victim_position_y,
            COUNT(*)::BIGINT AS source_occurrences
        FROM environmental_raw
        GROUP BY ALL
        """
    )


def create_quality_flags(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    connection.execute(
        """
        CREATE TEMP TABLE environmental_flags AS
        SELECT
            NULLIF(TRIM(source.killed_by), '') AS killed_by,
            NULLIF(TRIM(source.map), '') AS map,
            NULLIF(TRIM(source.match_id), '') AS match_id,
            TRY_CAST(
                NULLIF(TRIM(source.victim_position_x), '') AS DOUBLE
            ) AS victim_x,
            TRY_CAST(
                NULLIF(TRIM(source.victim_position_y), '') AS DOUBLE
            ) AS victim_y,
            source.source_occurrences,
            match.match_date,
            COALESCE(match.date_count, 0) AS date_count,
            (
                NULLIF(TRIM(source.map), '')
                    NOT IN ('ERANGEL', 'MIRAMAR')
                OR NULLIF(TRIM(source.map), '') IS NULL
            ) AS fails_map,
            (
                TRY_CAST(
                    NULLIF(TRIM(source.victim_position_x), '') AS DOUBLE
                ) = 0
                AND TRY_CAST(
                    NULLIF(TRIM(source.victim_position_y), '') AS DOUBLE
                ) = 0
            ) AS fails_zero_zero,
            (
                NULLIF(TRIM(source.map), '')
                    IN ('ERANGEL', 'MIRAMAR')
                AND (
                    TRY_CAST(
                        NULLIF(
                            TRIM(source.victim_position_x),
                            ''
                        ) AS DOUBLE
                    ) < 0
                    OR TRY_CAST(
                        NULLIF(
                            TRIM(source.victim_position_x),
                            ''
                        ) AS DOUBLE
                    ) > 816000
                    OR TRY_CAST(
                        NULLIF(
                            TRIM(source.victim_position_y),
                            ''
                        ) AS DOUBLE
                    ) < 0
                    OR TRY_CAST(
                        NULLIF(
                            TRIM(source.victim_position_y),
                            ''
                        ) AS DOUBLE
                    ) > 816000
                )
            ) AS fails_bounds,
            (
                match.match_id IS NULL
                OR match.date_count <> 1
            ) AS fails_date
        FROM environmental_deduplicated AS source
        LEFT JOIN dim_match AS match
            ON NULLIF(TRIM(source.match_id), '') = match.match_id
        """
    )


def print_profiles(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    print_result(
        "Eligibility funnel by cause",
        connection.execute(
            """
            SELECT
                killed_by,
                SUM(source_occurrences)::BIGINT AS raw_rows,
                COUNT(*)::BIGINT AS after_exact_dedup,
                SUM(
                    source_occurrences - 1
                )::BIGINT AS exact_duplicate_excess,
                COUNT_IF(NOT fails_map)::BIGINT AS after_map,
                COUNT_IF(
                    NOT fails_map
                    AND NOT fails_zero_zero
                )::BIGINT AS after_zero_zero,
                COUNT_IF(
                    NOT fails_map
                    AND NOT fails_zero_zero
                    AND NOT fails_bounds
                )::BIGINT AS after_bounds,
                COUNT_IF(
                    NOT fails_map
                    AND NOT fails_zero_zero
                    AND NOT fails_bounds
                    AND NOT fails_date
                )::BIGINT AS final_eligible_rows
            FROM environmental_flags
            GROUP BY killed_by
            ORDER BY killed_by
            """
        ),
    )
    print_result(
        "Primary exclusion reasons",
        connection.execute(
            """
            SELECT
                killed_by,
                CASE
                    WHEN fails_map THEN 'MISSING_MAP'
                    WHEN fails_zero_zero
                        THEN 'INVALID_OR_UNAVAILABLE_POSITION'
                    WHEN fails_bounds THEN 'OUT_OF_MAP_BOUNDS'
                    WHEN fails_date
                        THEN 'DATE_NOT_FOUND_OR_CONFLICT'
                    ELSE 'ELIGIBLE'
                END AS primary_status,
                COUNT(*)::BIGINT AS unique_rows
            FROM environmental_flags
            GROUP BY killed_by, primary_status
            ORDER BY killed_by, primary_status
            """
        ),
    )
    print_result(
        "Overlapping exclusion reasons",
        connection.execute(
            """
            SELECT
                killed_by,
                concat_ws(
                    '|',
                    CASE
                        WHEN fails_map THEN 'MISSING_MAP'
                    END,
                    CASE
                        WHEN fails_zero_zero THEN 'ZERO_ZERO'
                    END,
                    CASE
                        WHEN fails_bounds THEN 'OUT_OF_BOUNDS'
                    END,
                    CASE
                        WHEN fails_date
                            THEN 'DATE_NOT_FOUND_OR_CONFLICT'
                    END
                ) AS exclusion_combination,
                COUNT(*)::BIGINT AS unique_rows
            FROM environmental_flags
            WHERE
                fails_map
                OR fails_zero_zero
                OR fails_bounds
                OR fails_date
            GROUP BY killed_by, exclusion_combination
            ORDER BY killed_by, unique_rows DESC
            """
        ),
    )
    print_result(
        "Final eligible rows by map and cause",
        connection.execute(
            """
            SELECT
                map,
                killed_by,
                COUNT(*)::BIGINT AS eligible_rows,
                COUNT(
                    DISTINCT match_id
                )::BIGINT AS distinct_matches
            FROM environmental_flags
            WHERE
                NOT fails_map
                AND NOT fails_zero_zero
                AND NOT fails_bounds
                AND NOT fails_date
            GROUP BY map, killed_by
            ORDER BY map, killed_by
            """
        ),
    )
    print_result(
        "Row reconciliation",
        connection.execute(
            """
            SELECT
                SUM(
                    source_occurrences
                )::BIGINT AS raw_environmental_rows,
                SUM(
                    source_occurrences - 1
                )::BIGINT AS exact_duplicate_excess,
                COUNT(*)::BIGINT AS deduplicated_rows,
                COUNT_IF(
                    fails_map
                    OR fails_zero_zero
                    OR fails_bounds
                    OR fails_date
                )::BIGINT AS unique_excluded_rows,
                COUNT_IF(
                    NOT (
                        fails_map
                        OR fails_zero_zero
                        OR fails_bounds
                        OR fails_date
                    )
                )::BIGINT AS final_eligible_rows,
                (
                    SUM(source_occurrences)
                    - SUM(source_occurrences - 1)
                    - COUNT_IF(
                        fails_map
                        OR fails_zero_zero
                        OR fails_bounds
                        OR fails_date
                    )
                    - COUNT_IF(
                        NOT (
                            fails_map
                            OR fails_zero_zero
                            OR fails_bounds
                            OR fails_date
                        )
                    )
                )::BIGINT AS reconciliation_difference
            FROM environmental_flags
            """
        ),
    )


def main() -> None:
    started_at = perf_counter()
    with TemporaryDirectory(
        prefix="pubg_analysis_eligibility_",
    ) as temp_directory:
        connection = duckdb.connect()
        connection.execute("SET enable_progress_bar = false")
        connection.execute("SET preserve_insertion_order = false")
        escaped_temp = temp_directory.replace("'", "''")
        connection.execute(f"SET temp_directory = '{escaped_temp}'")

        create_match_dimension(connection)
        create_environmental_source(connection)
        create_quality_flags(connection)
        print_profiles(connection)

        elapsed_seconds = perf_counter() - started_at
        print(f"\nelapsed_seconds: {elapsed_seconds:.4f}")
        connection.close()


if __name__ == "__main__":
    main()
