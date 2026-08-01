from __future__ import annotations

import json
import statistics
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = PROJECT_ROOT / "sql" / "weapon_kill_distance_profiles.sql"
TEMPLATE_PATH = PROJECT_ROOT / "reports" / "templates" / "weapon_kill_distance.html"
OUTPUT_PATH = PROJECT_ROOT / "reports" / "weapon_kill_distance.html"


def to_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def query_rows(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
) -> list[dict[str, Any]]:
    result = conn.execute(sql)
    columns = [description[0] for description in result.description]
    return [
        {
            column: to_json_value(value)
            for column, value in zip(columns, row, strict=True)
        }
        for row in result.fetchall()
    ]


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_weapons = [
        row for row in rows if row["scope"] == "ALL" and row["killed_by"] is not None
    ]
    class_rows = [
        row for row in rows if row["scope"] == "ALL" and row["killed_by"] is None
    ]
    map_rows = {
        (row["killed_by"], row["scope"]): row
        for row in rows
        if row["scope"] in {"ERANGEL", "MIRAMAR"} and row["killed_by"] is not None
    }

    map_comparisons: list[dict[str, Any]] = []
    for weapon in sorted({row["killed_by"] for row in all_weapons}):
        erangel = map_rows.get((weapon, "ERANGEL"))
        miramar = map_rows.get((weapon, "MIRAMAR"))
        if erangel is None or miramar is None:
            continue
        gap = round(float(miramar["median_distance_m"] - erangel["median_distance_m"]), 1)
        map_comparisons.append(
            {
                "weapon": weapon,
                "weapon_class": erangel["weapon_class"],
                "erangel_event_count": erangel["event_count"],
                "miramar_event_count": miramar["event_count"],
                "erangel_median_m": erangel["median_distance_m"],
                "miramar_median_m": miramar["median_distance_m"],
                "median_gap_m": gap,
                "absolute_gap_m": abs(gap),
            }
        )

    class_lookup = {row["weapon_class"]: row for row in class_rows}
    dmr_rows = [row for row in all_weapons if row["weapon_class"] == "DMR"]
    shortest_dmr = min(dmr_rows, key=lambda row: row["median_distance_m"])
    longest_dmr = max(dmr_rows, key=lambda row: row["median_distance_m"])
    longest_weapon = max(all_weapons, key=lambda row: row["median_distance_m"])
    map_gap_values = [row["absolute_gap_m"] for row in map_comparisons]

    return {
        "valid_event_count": rows[0]["valid_event_count"],
        "weapon_count": len(all_weapons),
        "class_count": len(class_rows),
        "map_comparison_count": len(map_comparisons),
        "median_map_gap_m": round(statistics.median(map_gap_values), 1),
        "shotgun_median_m": class_lookup["Shotgun"]["median_distance_m"],
        "sr_median_m": class_lookup["SR"]["median_distance_m"],
        "role_median_spread_m": round(
            class_lookup["SR"]["median_distance_m"]
            - class_lookup["Shotgun"]["median_distance_m"],
            1,
        ),
        "shortest_dmr": shortest_dmr,
        "longest_dmr": longest_dmr,
        "longest_weapon": longest_weapon,
        "map_comparisons": sorted(
            map_comparisons,
            key=lambda row: row["absolute_gap_m"],
            reverse=True,
        ),
    }


def main() -> None:
    started_at = time.perf_counter()
    conn = duckdb.connect()

    try:
        rows = query_rows(conn, SQL_PATH.read_text(encoding="utf-8"))
    finally:
        conn.close()

    if not rows:
        raise RuntimeError("무기 거리 프로파일 결과가 비어 있습니다.")

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "profiles": rows,
        "summary": build_summary(rows),
    }
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    report = template.replace(
        "__WEAPON_DISTANCE_PAYLOAD__",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    elapsed = time.perf_counter() - started_at
    print("\n[무기별 사망 시점 거리 보고서 생성 완료]")
    print(f"유효 이벤트: {payload['summary']['valid_event_count']:,}건")
    print(f"분석 무기: {payload['summary']['weapon_count']}종")
    print(f"저장 위치: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"실행 시간: {elapsed:.2f}초")


if __name__ == "__main__":
    main()
