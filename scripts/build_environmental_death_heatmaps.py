"""Build a self-contained environmental-death heatmap report."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = PROJECT_ROOT / "sql" / "environmental_death_heatmap_cells.sql"
TEMPLATE_PATH = (
    PROJECT_ROOT / "reports" / "templates" / "environmental_death_heatmaps.html"
)
OUTPUT_PATH = PROJECT_ROOT / "reports" / "environmental_death_heatmaps.html"
MAP_DIRECTORY = PROJECT_ROOT / "data" / "reference" / "maps"
MAP_FILES = (
    MAP_DIRECTORY / "Erangel_2017-11-03.jpg",
    MAP_DIRECTORY / "Miramar_2017-12-23.jpg",
)


def to_json_value(value: Any) -> Any:
    """Convert DuckDB result values into JSON-safe values."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def query_heatmap_rows(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Execute the checked-in spatial metric SQL and return named rows."""

    cursor = conn.execute(SQL_PATH.read_text(encoding="utf-8"))
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
        rows = query_heatmap_rows(conn)
    finally:
        conn.close()

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "grid_size_m": 100,
        "map_image_extent_m": 8192,
        "coordinate_valid_max_m": 8160,
        "rows": rows,
    }
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = template.replace(
        "__HEATMAP_PAYLOAD__",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
    OUTPUT_PATH.write_text(html, encoding="utf-8")

    print("Heatmap panels: 4")
    print(f"Heatmap cells: {len(rows):,}")
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
