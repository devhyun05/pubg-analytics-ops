import os
from pathlib import Path
from time import perf_counter

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
METRIC_250M_SQL_PATH = (
    PROJECT_ROOT / "sql/environmental_death_grid_metrics.sql"
)
METRIC_100M_SQL_PATH = (
    PROJECT_ROOT / "sql/environmental_death_grid_metrics_100m.sql"
)
COMPARISON_SQL_PATH = (
    PROJECT_ROOT / "sql/environmental_death_resolution_comparison.sql"
)
OUTPUT_CSV_PATH = (
    PROJECT_ROOT
    / "data/processed/environmental_death_resolution_comparison_100m.csv"
)
OUTPUT_PARQUET_PATH = (
    PROJECT_ROOT
    / "data/processed/environmental_death_resolution_comparison_100m.parquet"
)

METRIC_250M_VIEW = "environmental_death_grid_candidates_250m"
METRIC_100M_VIEW = "environmental_death_grid_candidates_100m"
COMPARISON_VIEW = "environmental_death_resolution_comparison"


def read_query(path: Path) -> str:
    """SQL 파일을 TEMP VIEW 정의에 사용할 수 있는 쿼리로 읽는다."""

    return path.read_text(encoding="utf-8").strip().removesuffix(";")


def sql_path(path: Path) -> str:
    """파일 경로를 DuckDB SQL 문자열에 안전하게 넣을 수 있도록 변환한다."""

    return path.as_posix().replace("'", "''")


def create_views(conn: duckdb.DuckDBPyConnection) -> None:
    """250m, 100m 지표와 해상도 비교 TEMP VIEW를 생성한다."""

    metric_250m_query = read_query(METRIC_250M_SQL_PATH)
    metric_100m_query = read_query(METRIC_100M_SQL_PATH)
    comparison_query = read_query(COMPARISON_SQL_PATH)

    conn.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW {METRIC_250M_VIEW}
        AS {metric_250m_query}
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW {METRIC_100M_VIEW}
        AS {metric_100m_query}
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW {COMPARISON_VIEW}
        AS {comparison_query}
        """
    )


def replace_export(
    conn: duckdb.DuckDBPyConnection,
    output_path: Path,
    copy_options: str,
) -> None:
    """비교 VIEW를 임시 파일에 쓴 뒤 최종 결과를 교체한다."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")

    if temporary_path.exists():
        temporary_path.unlink()

    try:
        conn.execute(
            f"""
            COPY (SELECT * FROM {COMPARISON_VIEW})
            TO '{sql_path(temporary_path)}'
            ({copy_options})
            """
        )
        temporary_path.replace(output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def show_priority_summaries(conn: duckdb.DuckDBPyConnection) -> None:
    """맵과 원인별 100m 상위 3개 후보 요약을 출력한다."""

    rows = conn.execute(
        f"""
        SELECT report_summary
        FROM {COMPARISON_VIEW}
        WHERE candidate_rank_100m <= 3
        ORDER BY map, killed_by, candidate_rank_100m
        """
    ).fetchall()

    print("\n[100m 상세 분석] 맵·원인별 상위 3개 후보")
    for (summary,) in rows:
        print(f"- {summary}")


def main() -> None:
    started_at = perf_counter()
    os.chdir(PROJECT_ROOT)
    conn = duckdb.connect()

    try:
        create_views(conn)
        candidate_count = conn.execute(
            f"SELECT COUNT(*) FROM {COMPARISON_VIEW}"
        ).fetchone()[0]

        show_priority_summaries(conn)
        replace_export(
            conn,
            OUTPUT_CSV_PATH,
            "HEADER, DELIMITER ','",
        )
        replace_export(
            conn,
            OUTPUT_PARQUET_PATH,
            "FORMAT PARQUET, COMPRESSION ZSTD",
        )
    finally:
        conn.close()

    elapsed_seconds = perf_counter() - started_at

    print(f"\n전체 100m 후보 수: {candidate_count:,}개")
    print(f"CSV 저장 위치: {OUTPUT_CSV_PATH.relative_to(PROJECT_ROOT)}")
    print(
        "Parquet 저장 위치: "
        f"{OUTPUT_PARQUET_PATH.relative_to(PROJECT_ROOT)}"
    )
    print(f"총 실행 시간: {elapsed_seconds:.2f}초")


if __name__ == "__main__":
    main()
