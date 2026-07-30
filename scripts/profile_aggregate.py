from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import perf_counter

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = (
    PROJECT_ROOT / "data" / "staged" / "aggregate" / "agg_match_stats_0.csv"
)


def positive_int(value: str) -> int:
    parsed_value = int(value)
    if parsed_value <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed_value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile a sample of an aggregate PUBG CSV with DuckDB."
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Aggregate CSV path.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=10_000,
        help="Maximum number of rows to profile.",
    )
    return parser.parse_args()


def profile_aggregate(csv_path: Path, row_limit: int) -> int:
    started_at = perf_counter()
    failure_count = 0

    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    connection = duckdb.connect()
    try:
        sample = connection.read_csv(str(csv_path), sample_size=20_000).limit(
            row_limit
        )
        sample.create_view("aggregate_sample")

        print(f"Input file: {csv_path}")
        print(f"Sample row limit: {row_limit:,}")

        print("\n[Schema]")
        connection.sql("DESCRIBE aggregate_sample").show()

        print("\n[First 5 rows]")
        connection.sql("SELECT * FROM aggregate_sample LIMIT 5").show()

        print("\n[Basic quality profile]")
        connection.sql(
            """
            SELECT
                COUNT(*) AS sampled_rows,
                COUNT(*) FILTER (WHERE match_id IS NULL) AS null_match_id,
                COUNT(*) FILTER (WHERE player_name IS NULL) AS null_player_name,
                MIN(player_kills) AS min_kills,
                MAX(player_kills) AS max_kills,
                MIN(player_dmg) AS min_damage,
                MAX(player_dmg) AS max_damage
            FROM aggregate_sample
            """
        ).show()

        print("\n[Duplicate candidate keys]")
        connection.sql(
            """
            SELECT
                COUNT(*) AS duplicate_groups,
                COALESCE(SUM(group_rows - 1), 0) AS duplicate_rows
            FROM (
                SELECT
                    match_id,
                    player_name,
                    COUNT(*) AS group_rows
                FROM aggregate_sample
                GROUP BY match_id, player_name
                HAVING COUNT(*) > 1
            ) AS duplicate_keys
            """
        ).show()
    except duckdb.Error:
        failure_count = 1
        raise
    finally:
        connection.close()
        elapsed_seconds = perf_counter() - started_at
        print(f"\nFailure count: {failure_count}")
        print(f"Elapsed seconds: {elapsed_seconds:.3f}")

    return 0


def main() -> int:
    args = parse_args()
    try:
        return profile_aggregate(args.csv_path.resolve(), args.limit)
    except (FileNotFoundError, duckdb.Error) as error:
        print(f"Profile failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
