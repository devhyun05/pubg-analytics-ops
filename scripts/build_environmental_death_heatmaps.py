"""Build a self-contained environmental-death heatmap report."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = PROJECT_ROOT / "sql" / "environmental_death_heatmap_cells.sql"
DETAIL_SQL_PATH = (
    PROJECT_ROOT / "sql" / "environmental_death_heatmap_detail_cells.sql"
)
SUMMARY_SQL_PATH = (
    PROJECT_ROOT / "sql" / "environmental_death_report_summary.sql"
)
TEMPLATE_PATH = (
    PROJECT_ROOT / "reports" / "templates" / "environmental_death_heatmaps.html"
)
OUTPUT_PATH = PROJECT_ROOT / "reports" / "environmental_death_heatmaps.html"
MAP_DIRECTORY = PROJECT_ROOT / "data" / "reference" / "maps"
MAP_FILES = (
    MAP_DIRECTORY / "Erangel_2017-11-03.jpg",
    MAP_DIRECTORY / "Miramar_2017-12-23.jpg",
)
GRID_SIZE_M = 100
INCLUDED_RANK_LIMIT = 400


def to_json_value(value: Any) -> Any:
    """Convert DuckDB result values into JSON-safe values."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def query_rows(
    conn: duckdb.DuckDBPyConnection,
    sql_path: Path,
) -> list[dict[str, Any]]:
    """Execute a checked-in spatial metric SQL file and return named rows."""

    cursor = conn.execute(sql_path.read_text(encoding="utf-8"))
    columns = [column[0] for column in cursor.description]
    return [
        {
            column: to_json_value(value)
            for column, value in zip(columns, values, strict=True)
        }
        for values in cursor.fetchall()
    ]


def main() -> None:
    """Render the four-panel local HTML heatmap report."""

    missing_files = [path for path in MAP_FILES if not path.exists()]
    if missing_files:
        missing = "\n".join(f"- {path}" for path in missing_files)
        raise FileNotFoundError(
            "Historical map files are missing. Run "
            "`python scripts/download_map_assets.py` first:\n"
            f"{missing}"
        )

    conn = duckdb.connect()
    try:
        rows = query_rows(conn, SQL_PATH)
        detail_rows = query_rows(conn, DETAIL_SQL_PATH)
        summary_rows = query_rows(conn, SUMMARY_SQL_PATH)
    finally:
        conn.close()

    if len(summary_rows) != 1:
        raise ValueError(
            "Environmental report summary must return exactly one row."
        )

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "grid_size_m": GRID_SIZE_M,
        "detail_grid_size_m": 10,
        "included_rank_limit": INCLUDED_RANK_LIMIT,
        "map_image_extent_m": 8192,
        "coordinate_valid_max_m": 8160,
        "rows": rows,
        "detail_rows": detail_rows,
        "summary": summary_rows[0],
    }
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = template.replace(
        "__HEATMAP_PAYLOAD__",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
    OUTPUT_PATH.write_text(html, encoding="utf-8")

    print("Heatmap panels: 4")
    print(f"Heatmap cells: {len(rows):,}")
    print(f"10m detail cells: {len(detail_rows):,}")
    print(
        "Priority candidate: "
        f"{summary_rows[0]['map']} {summary_rows[0]['killed_by']} "
        f"count rank #{summary_rows[0]['count_rank']}"
    )
    for row in rows:
        if row["heat_rank"] <= 3:
            start_x_m = row["grid_x"] * GRID_SIZE_M
            start_y_m = row["grid_y"] * GRID_SIZE_M
            print(
                f"- {row['map']} {row['killed_by']} #{row['heat_rank']}: "
                f"X {start_x_m}-{start_x_m + GRID_SIZE_M}m, "
                f"Y {start_y_m}-{start_y_m + GRID_SIZE_M}m, "
                f"{row['death_count']:,} deaths, "
                f"{row['match_count']:,} matches, "
                f"{row['date_count']} dates, "
                f"{row['share_pct']:.4f}%"
            )
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
