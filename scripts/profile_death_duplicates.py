from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEATHS_DIR = PROJECT_ROOT / "data" / "staged" / "deaths"
DEATHS_PATTERN = "kill_match_stats_final_*.csv"
RAW_COLUMNS = (
    "killed_by",
    "killer_name",
    "killer_placement",
    "killer_position_x",
    "killer_position_y",
    "map",
    "match_id",
    "time",
    "victim_name",
    "victim_placement",
    "victim_position_x",
    "victim_position_y",
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
        print(" | ".join("NULL" if value is None else str(value) for value in row))


def build_source_sql(csv_glob: str) -> str:
    escaped_glob = csv_glob.replace("'", "''")
    selected_columns = ",\n            ".join(RAW_COLUMNS)
    return f"""
        SELECT
            filename,
            {selected_columns}
        FROM read_csv_auto(
            '{escaped_glob}',
            all_varchar = true,
            filename = true,
            union_by_name = true
        )
    """


def create_exact_duplicate_groups(
    connection: duckdb.DuckDBPyConnection,
    source_sql: str,
) -> None:
    hash_arguments = ", ".join(RAW_COLUMNS)
    group_columns = ", ".join(RAW_COLUMNS)

    connection.execute(
        f"""
        CREATE TEMP TABLE repeated_row_hashes AS
        SELECT
            row_hash,
            COUNT(*)::BIGINT AS hash_rows
        FROM (
            SELECT hash({hash_arguments}) AS row_hash
            FROM ({source_sql})
        )
        GROUP BY row_hash
        HAVING COUNT(*) > 1
        """
    )

    connection.execute(
        f"""
        CREATE TEMP TABLE exact_duplicate_groups AS
        SELECT
            {group_columns},
            COUNT(*)::BIGINT AS row_count,
            COUNT(DISTINCT filename)::BIGINT AS source_file_count
        FROM (
            SELECT source.*
            FROM ({source_sql}) AS source
            INNER JOIN repeated_row_hashes AS repeated
                ON hash({hash_arguments}) = repeated.row_hash
        )
        GROUP BY {group_columns}
        HAVING COUNT(*) > 1
        """
    )


def create_event_candidate_groups(
    connection: duckdb.DuckDBPyConnection,
    source_sql: str,
) -> None:
    hash_arguments = ", ".join(RAW_COLUMNS)
    event_hash = """
        hash(
            NULLIF(TRIM(match_id), ''),
            NULLIF(TRIM(victim_name), ''),
            TRY_CAST(NULLIF(TRIM(time), '') AS DOUBLE),
            NULLIF(TRIM(killed_by), '')
        )
    """
    complete_event_key = """
        NULLIF(TRIM(match_id), '') IS NOT NULL
        AND NULLIF(TRIM(victim_name), '') IS NOT NULL
        AND TRY_CAST(NULLIF(TRIM(time), '') AS DOUBLE) IS NOT NULL
        AND NULLIF(TRIM(killed_by), '') IS NOT NULL
    """

    connection.execute(
        f"""
        CREATE TEMP TABLE repeated_event_hashes AS
        SELECT
            event_hash,
            COUNT(*)::BIGINT AS hash_rows
        FROM (
            SELECT {event_hash} AS event_hash
            FROM ({source_sql})
            WHERE {complete_event_key}
        )
        GROUP BY event_hash
        HAVING COUNT(*) > 1
        """
    )

    connection.execute(
        f"""
        CREATE TEMP TABLE event_candidate_groups AS
        SELECT
            NULLIF(TRIM(match_id), '') AS match_id_key,
            NULLIF(TRIM(victim_name), '') AS victim_name_key,
            TRY_CAST(NULLIF(TRIM(time), '') AS DOUBLE) AS time_key,
            NULLIF(TRIM(killed_by), '') AS killed_by_key,
            COUNT(*)::BIGINT AS row_count,
            COUNT(
                DISTINCT hash({hash_arguments})
            )::BIGINT AS detail_variants,
            COUNT(DISTINCT filename)::BIGINT AS source_file_count
        FROM (
            SELECT source.*
            FROM ({source_sql}) AS source
            INNER JOIN repeated_event_hashes AS repeated
                ON {event_hash} = repeated.event_hash
            WHERE {complete_event_key}
        )
        GROUP BY
            match_id_key,
            victim_name_key,
            time_key,
            killed_by_key
        HAVING COUNT(*) > 1
        """
    )


def print_profiles(
    connection: duckdb.DuckDBPyConnection,
    source_sql: str,
) -> None:
    print_result(
        "Exact duplicate summary",
        connection.execute(
            """
            SELECT
                COUNT(*)::BIGINT AS duplicate_groups,
                COALESCE(SUM(row_count), 0)::BIGINT
                    AS rows_in_duplicate_groups,
                COALESCE(SUM(row_count - 1), 0)::BIGINT
                    AS excess_duplicate_rows,
                COUNT_IF(source_file_count = 1)::BIGINT
                    AS within_file_groups,
                COUNT_IF(source_file_count > 1)::BIGINT
                    AS cross_file_groups,
                COALESCE(MAX(row_count), 0)::BIGINT AS max_copies
            FROM exact_duplicate_groups
            """
        ),
    )
    print_result(
        "Exact duplicates by environmental cause",
        connection.execute(
            """
            SELECT
                killed_by,
                COUNT(*)::BIGINT AS duplicate_groups,
                SUM(row_count)::BIGINT AS rows_in_groups,
                SUM(row_count - 1)::BIGINT AS excess_rows,
                MAX(row_count)::BIGINT AS max_copies
            FROM exact_duplicate_groups
            WHERE killed_by IN ('Falling', 'Drown')
            GROUP BY killed_by
            ORDER BY killed_by
            """
        ),
    )
    print_result(
        "Event candidate summary",
        connection.execute(
            """
            SELECT
                COUNT(*)::BIGINT AS candidate_groups,
                COALESCE(SUM(row_count), 0)::BIGINT
                    AS rows_in_candidate_groups,
                COALESCE(SUM(row_count - 1), 0)::BIGINT
                    AS excess_candidate_rows,
                COUNT_IF(detail_variants = 1)::BIGINT
                    AS exact_only_groups,
                COUNT_IF(detail_variants > 1)::BIGINT
                    AS differing_detail_groups,
                COALESCE(MAX(row_count), 0)::BIGINT
                    AS max_rows_per_key
            FROM event_candidate_groups
            """
        ),
    )
    print_result(
        "Environmental event candidates",
        connection.execute(
            """
            SELECT
                killed_by_key,
                COUNT(*)::BIGINT AS candidate_groups,
                SUM(row_count)::BIGINT AS rows_in_groups,
                SUM(row_count - 1)::BIGINT AS excess_rows,
                COUNT_IF(detail_variants = 1)::BIGINT
                    AS exact_only_groups,
                COUNT_IF(detail_variants > 1)::BIGINT
                    AS differing_detail_groups,
                MAX(row_count)::BIGINT AS max_rows_per_key
            FROM event_candidate_groups
            WHERE killed_by_key IN ('Falling', 'Drown')
            GROUP BY killed_by_key
            ORDER BY killed_by_key
            """
        ),
    )
    print_result(
        "Event key completeness",
        connection.execute(
            f"""
            SELECT
                COUNT(*)::BIGINT AS total_rows,
                COUNT_IF(
                    NULLIF(TRIM(match_id), '') IS NULL
                )::BIGINT AS missing_match_id,
                COUNT_IF(
                    NULLIF(TRIM(victim_name), '') IS NULL
                )::BIGINT AS missing_victim_name,
                COUNT_IF(
                    TRY_CAST(NULLIF(TRIM(time), '') AS DOUBLE) IS NULL
                )::BIGINT AS invalid_or_missing_time,
                COUNT_IF(
                    NULLIF(TRIM(killed_by), '') IS NULL
                )::BIGINT AS missing_killed_by
            FROM ({source_sql})
            """
        ),
    )


def main() -> None:
    files = sorted(DEATHS_DIR.glob(DEATHS_PATTERN))
    if not files:
        raise FileNotFoundError(
            f"No deaths CSV files matched: {DEATHS_DIR / DEATHS_PATTERN}"
        )

    started_at = perf_counter()
    source_sql = build_source_sql(
        (DEATHS_DIR / DEATHS_PATTERN).as_posix()
    )

    with TemporaryDirectory(
        prefix="pubg_duplicate_profile_",
    ) as temp_directory:
        connection = duckdb.connect()
        connection.execute("SET enable_progress_bar = false")
        connection.execute("SET preserve_insertion_order = false")
        escaped_temp = temp_directory.replace("'", "''")
        connection.execute(f"SET temp_directory = '{escaped_temp}'")

        create_exact_duplicate_groups(connection, source_sql)
        create_event_candidate_groups(connection, source_sql)
        print_profiles(connection, source_sql)

        elapsed_seconds = perf_counter() - started_at
        print(f"\nelapsed_seconds: {elapsed_seconds:.4f}")
        connection.close()


if __name__ == "__main__":
    main()
