from __future__ import annotations

import csv
from pathlib import Path
from time import perf_counter

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_GROUPS = {
    "deaths": (
        PROJECT_ROOT / "data" / "staged" / "deaths",
        "kill_match_stats_final_*.csv",
    ),
    "aggregate": (
        PROJECT_ROOT / "data" / "staged" / "aggregate",
        "agg_match_stats_*.csv",
    ),
}


def read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))


def infer_schema(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
) -> list[tuple[str, str]]:
    escaped_path = path.as_posix().replace("'", "''")
    rows = connection.execute(
        f"""
        DESCRIBE SELECT *
        FROM read_csv_auto(
            '{escaped_path}',
            sample_size = -1
        )
        """
    ).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def main() -> None:
    started_at = perf_counter()
    connection = duckdb.connect()
    connection.execute("SET enable_progress_bar = false")
    mismatch_found = False

    for group_name, (directory, pattern) in INPUT_GROUPS.items():
        files = sorted(directory.glob(pattern))
        if not files:
            raise FileNotFoundError(
                f"No CSV files matched: {directory / pattern}"
            )

        baseline_header = read_header(files[0])
        baseline_schema = infer_schema(connection, files[0])
        print(f"\n[{group_name} schema]")

        for path in files:
            header = read_header(path)
            schema = infer_schema(connection, path)
            header_matches = header == baseline_header
            types_match = schema == baseline_schema
            mismatch_found = (
                mismatch_found or not header_matches or not types_match
            )
            print(
                f"{path.name}: columns={len(header)}, "
                f"header_matches={header_matches}, "
                f"types_match={types_match}"
            )
            for column_name, column_type in schema:
                print(f"  {column_name}: {column_type}")

    elapsed_seconds = perf_counter() - started_at
    print(f"\nelapsed_seconds: {elapsed_seconds:.4f}")
    connection.close()

    if mismatch_found:
        raise RuntimeError("An input CSV schema mismatch was detected.")


if __name__ == "__main__":
    main()
