"""Validate and publish environmental analytics results to PostgreSQL."""

import argparse
import os
from contextlib import chdir
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

import duckdb
import psycopg
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "environmental_deaths.parquet"
QUALITY_SQL_PATH = PROJECT_ROOT / "sql" / "final_environmental_quality_checks.sql"
HOTSPOT_SQL_PATH = PROJECT_ROOT / "sql" / "environmental_death_heatmap_cells.sql"
SCHEMA_SQL_PATH = PROJECT_ROOT / "sql" / "postgres_schema.sql"
PIPELINE_NAME = "environmental_hotspot_publish"
RULE_VERSION = "1.0.0"
CHUNK_SIZE = 1024 * 1024

QUALITY_DESCRIPTIONS = {
    "DQ-FINAL-ELIGIBILITY-001": "Final rows satisfy every publication rule.",
    "DQ-EVENT-ID-001": "A non-identifying source-grain event ID is present.",
    "DQ-MAP-001": "Map is ERANGEL or MIRAMAR.",
    "DQ-MATCH-001": "match_id is present and non-empty.",
    "DQ-COORD-NULL-001": "Victim coordinates are present.",
    "DQ-COORD-002": "Victim coordinates are not exactly (0, 0).",
    "DQ-COORD-001": "Victim coordinates are inside 0..816000 cm.",
    "DQ-DATE-001": "A source aggregate date is linked to the event.",
    "DQ-CAUSE-001": "Death cause is Falling or Drown.",
    "DQ-DUP-001": "No duplicate final event key remains.",
}


@dataclass(frozen=True)
class DatabaseSettings:
    """PostgreSQL connection settings loaded from environment variables."""

    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str

    @classmethod
    def from_environment(cls) -> "DatabaseSettings":
        required = {
            "POSTGRES_DB": os.getenv("POSTGRES_DB", ""),
            "POSTGRES_USER": os.getenv("POSTGRES_USER", ""),
            "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            names = ", ".join(missing)
            raise ValueError(f"Missing required database environment values: {names}")

        password = required["POSTGRES_PASSWORD"]
        if password == "replace-with-a-local-password":
            raise ValueError("Replace the example POSTGRES_PASSWORD before running.")

        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5433")),
            dbname=required["POSTGRES_DB"],
            user=required["POSTGRES_USER"],
            password=password,
            sslmode=os.getenv("POSTGRES_SSLMODE", "disable"),
        )

    def connection_kwargs(self) -> dict[str, object]:
        """Return Psycopg keyword arguments without logging credentials."""

        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
            "sslmode": self.sslmode,
        }


def load_env_file(path: Path) -> None:
    """Load a simple local dotenv file without overriding shell variables."""

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def file_sha256(path: Path) -> str:
    """Calculate the immutable input fingerprint used as the batch key."""

    digest = sha256()
    with path.open("rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_dicts(
    cursor: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """Convert the latest DuckDB result into dictionaries."""

    columns = [column[0] for column in cursor.description]
    return [
        dict(zip(columns, values, strict=True))
        for values in cursor.fetchall()
    ]


def find_date_column(conn: duckdb.DuckDBPyConnection) -> str:
    """Find the linked source-date column without inventing a date."""

    columns = {
        row[0]
        for row in conn.execute(
            "DESCRIBE SELECT * FROM "
            "read_parquet('data/processed/environmental_deaths.parquet')"
        ).fetchall()
    }
    for candidate in ("match_date", "date"):
        if candidate in columns:
            return candidate
    raise ValueError("Final Parquet has neither match_date nor date.")


def calculate_results() -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
    """Run final quality checks and the 100 m hotspot metric query."""

    with chdir(PROJECT_ROOT):
        conn = duckdb.connect()
        try:
            input_rows = conn.execute(
                "SELECT COUNT(*) FROM "
                "read_parquet('data/processed/environmental_deaths.parquet')"
            ).fetchone()[0]
            date_column = find_date_column(conn)
            quality_sql = QUALITY_SQL_PATH.read_text(encoding="utf-8").replace(
                "__DATE_COLUMN__",
                f'"{date_column}"',
            )
            quality_results = fetch_dicts(conn.execute(quality_sql))
            hotspot_results = fetch_dicts(
                conn.execute(HOTSPOT_SQL_PATH.read_text(encoding="utf-8"))
            )
        finally:
            conn.close()
    return int(input_rows), quality_results, hotspot_results


def ensure_schema(connection: psycopg.Connection[Any]) -> None:
    """Apply idempotent PostgreSQL DDL."""

    with connection.cursor() as cursor:
        cursor.execute(
            SCHEMA_SQL_PATH.read_text(encoding="utf-8"),
            prepare=False,
        )


def insert_running_row(
    connection: psycopg.Connection[Any],
    run_id: UUID,
    batch_id: str,
    checksum: str,
    started_at: datetime,
) -> None:
    """Create an immutable execution-history row before processing."""

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO analytics_ops.pipeline_runs (
                run_id,
                pipeline_name,
                batch_id,
                input_checksum,
                status,
                quality_status,
                started_at
            )
            VALUES (%s, %s, %s, %s, 'RUNNING', 'NOT_CHECKED', %s)
            """,
            (run_id, PIPELINE_NAME, batch_id, checksum, started_at),
        )


def insert_quality_results(
    cursor: psycopg.Cursor[Any],
    run_id: UUID,
    batch_id: str,
    checked_at: datetime,
    quality_results: list[dict[str, Any]],
) -> None:
    """Persist one result per named quality rule."""

    rows = []
    for result in quality_results:
        checked_rows = int(result["checked_rows"])
        error_count = int(result["error_count"])
        error_rate = error_count / checked_rows if checked_rows else 0.0
        check_name = str(result["check_name"])
        rows.append(
            (
                run_id,
                batch_id,
                check_name,
                RULE_VERSION,
                "PASS" if error_count == 0 else "FAIL",
                checked_rows,
                error_count,
                error_rate,
                checked_at,
                Jsonb(
                    {
                        "description": QUALITY_DESCRIPTIONS[check_name],
                        "accepted_error_count": 0,
                    }
                ),
            )
        )

    cursor.executemany(
        """
        INSERT INTO analytics_ops.quality_check_results (
            run_id,
            batch_id,
            check_name,
            rule_version,
            status,
            checked_rows,
            error_count,
            error_rate,
            checked_at,
            details
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )


def publish_hotspots(
    cursor: psycopg.Cursor[Any],
    run_id: UUID,
    batch_id: str,
    published_at: datetime,
    hotspots: list[dict[str, Any]],
) -> None:
    """Replace one batch snapshot so reruns cannot create duplicate cells."""

    cursor.execute(
        "DELETE FROM analytics_ops.environmental_hotspots WHERE batch_id = %s",
        (batch_id,),
    )
    cursor.executemany(
        """
        INSERT INTO analytics_ops.environmental_hotspots (
            batch_id,
            source_run_id,
            map,
            killed_by,
            grid_size_m,
            grid_x,
            grid_y,
            death_count,
            match_count,
            date_count,
            share_pct,
            heat_rank,
            published_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                batch_id,
                run_id,
                row["map"],
                row["killed_by"],
                int(row["grid_size_m"]),
                int(row["grid_x"]),
                int(row["grid_y"]),
                int(row["death_count"]),
                int(row["match_count"]),
                int(row["date_count"]),
                row["share_pct"],
                int(row["heat_rank"]),
                published_at,
            )
            for row in hotspots
        ],
    )


def update_run(
    cursor: psycopg.Cursor[Any],
    run_id: UUID,
    *,
    status: str,
    quality_status: str,
    finished_at: datetime,
    duration_seconds: float,
    input_rows: int,
    output_rows: int,
    failed_rows: int,
    error_message: str | None,
) -> None:
    """Finalize execution counts and status."""

    cursor.execute(
        """
        UPDATE analytics_ops.pipeline_runs
        SET
            status = %s,
            quality_status = %s,
            finished_at = %s,
            duration_seconds = %s,
            input_rows = %s,
            output_rows = %s,
            failed_rows = %s,
            error_message = %s
        WHERE run_id = %s
        """,
        (
            status,
            quality_status,
            finished_at,
            duration_seconds,
            input_rows,
            output_rows,
            failed_rows,
            error_message,
            run_id,
        ),
    )


def parse_args() -> argparse.Namespace:
    """Parse local execution options."""

    parser = argparse.ArgumentParser(
        description="Publish validated environmental metrics to PostgreSQL."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="Local dotenv path. Existing shell variables take precedence.",
    )
    return parser.parse_args()


def main() -> int:
    """Record quality results and publish an idempotent hotspot snapshot."""

    args = parse_args()
    load_env_file(args.env_file)
    settings = DatabaseSettings.from_environment()
    if not PARQUET_PATH.exists():
        raise FileNotFoundError(
            "Missing processed input. Run "
            "`python scripts/build_environmental_deaths.py` first."
        )

    checksum = file_sha256(PARQUET_PATH)
    batch_id = f"environmental-deaths-{checksum[:20]}"
    run_id = uuid4()
    started_at = datetime.now(UTC)
    started_timer = perf_counter()
    connection = psycopg.connect(**settings.connection_kwargs(), autocommit=True)

    try:
        ensure_schema(connection)
        insert_running_row(connection, run_id, batch_id, checksum, started_at)
        input_rows, quality_results, hotspots = calculate_results()
        failed_rules = [
            result
            for result in quality_results
            if int(result["error_count"]) > 0
        ]
        final_check = next(
            result
            for result in quality_results
            if result["check_name"] == "DQ-FINAL-ELIGIBILITY-001"
        )
        failed_rows = int(final_check["error_count"])
        finished_at = datetime.now(UTC)
        duration_seconds = perf_counter() - started_timer

        with connection.transaction(), connection.cursor() as cursor:
            insert_quality_results(
                cursor,
                run_id,
                batch_id,
                finished_at,
                quality_results,
            )
            if failed_rules:
                update_run(
                    cursor,
                    run_id,
                    status="FAILED",
                    quality_status="FAIL",
                    finished_at=finished_at,
                    duration_seconds=duration_seconds,
                    input_rows=input_rows,
                    output_rows=0,
                    failed_rows=failed_rows,
                    error_message=(
                        f"Publication blocked by {len(failed_rules)} quality rules."
                    ),
                )
            else:
                publish_hotspots(
                    cursor,
                    run_id,
                    batch_id,
                    finished_at,
                    hotspots,
                )
                update_run(
                    cursor,
                    run_id,
                    status="SUCCEEDED",
                    quality_status="PASS",
                    finished_at=finished_at,
                    duration_seconds=duration_seconds,
                    input_rows=input_rows,
                    output_rows=len(hotspots),
                    failed_rows=0,
                    error_message=None,
                )

        print(f"run_id: {run_id}")
        print(f"batch_id: {batch_id}")
        print(f"input_rows: {input_rows:,}")
        print(f"quality_checks: {len(quality_results)}")
        print(f"hotspot_rows: {0 if failed_rules else len(hotspots):,}")
        print(f"status: {'FAILED' if failed_rules else 'SUCCEEDED'}")
        return 1 if failed_rules else 0
    except Exception as error:
        finished_at = datetime.now(UTC)
        duration_seconds = perf_counter() - started_timer
        try:
            with connection.transaction(), connection.cursor() as cursor:
                update_run(
                    cursor,
                    run_id,
                    status="FAILED",
                    quality_status="NOT_CHECKED",
                    finished_at=finished_at,
                    duration_seconds=duration_seconds,
                    input_rows=0,
                    output_rows=0,
                    failed_rows=0,
                    error_message=str(error)[:2000],
                )
        except Exception:
            pass
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
