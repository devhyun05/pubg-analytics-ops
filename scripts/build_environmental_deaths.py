from pathlib import Path
from time import perf_counter

import duckdb


DEATHS_GLOB = "data/staged/deaths/kill_match_stats_final_*.csv"
AGGREGATE_GLOB = "data/staged/aggregate/agg_match_stats_*.csv"

OUTPUT_PATH = Path("data/processed/environmental_deaths.parquet")

MIN_COORD = 0.0
MAX_COORD = 816_000.0


def fetch_count(
    conn: duckdb.DuckDBPyConnection,
    query: str,
) -> int:
    """쿼리 결과의 첫 번째 행과 컬럼을 정수로 반환한다."""

    row = conn.execute(query).fetchone()

    if row is None:
        raise RuntimeError("행 수 조회 결과가 없습니다.")

    return int(row[0])


def build_environmental_source(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """원본에서 Falling과 Drown 이벤트를 선택한다."""

    print("\n[1] 환경 사망 원본 생성")

    conn.execute(f"""
        CREATE OR REPLACE TEMP TABLE environmental_deaths_raw AS

        SELECT *
        FROM read_csv_auto(
            '{DEATHS_GLOB}',
            union_by_name = true
        )
        WHERE killed_by IN ('Falling', 'Drown')
    """)


def show_environmental_counts(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """환경 사망 원인별 행 수를 확인한다."""

    print("\n[2] 환경 사망 원인별 건수")

    conn.sql("""
        SELECT
            killed_by,
            COUNT(*) AS death_count
        FROM environmental_deaths_raw
        GROUP BY killed_by
        ORDER BY death_count DESC
    """).show()


def show_quality_profile(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """환경 사망 원본의 주요 품질 문제를 독립적으로 측정한다."""

    print("\n[3] 환경 사망 데이터 품질 검사")

    conn.sql(f"""
        SELECT
            COUNT(*) AS environmental_rows,

            COUNT(*) FILTER (
                WHERE map IS NULL
                   OR TRIM(map) = ''
            ) AS missing_map_rows,

            COUNT(*) FILTER (
                WHERE match_id IS NULL
                   OR TRIM(match_id) = ''
            ) AS missing_match_id_rows,

            COUNT(*) FILTER (
                WHERE victim_position_x IS NULL
                   OR victim_position_y IS NULL
            ) AS missing_coordinate_rows,

            COUNT(*) FILTER (
                WHERE victim_position_x = 0
                  AND victim_position_y = 0
            ) AS zero_zero_rows,

            COUNT(*) FILTER (
                WHERE victim_position_x < {MIN_COORD}
                   OR victim_position_y < {MIN_COORD}
                   OR victim_position_x > {MAX_COORD}
                   OR victim_position_y > {MAX_COORD}
            ) AS out_of_bounds_rows

        FROM environmental_deaths_raw
    """).show()


def build_quality_classification(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """완전 중복을 제거하고 행마다 품질 상태를 부여한다."""

    print("\n[4] 완전 중복 제거 및 품질 규칙 적용")

    conn.execute("""
        CREATE OR REPLACE TEMP TABLE
            environmental_deaths_deduplicated AS

        SELECT DISTINCT *
        FROM environmental_deaths_raw
    """)

    conn.execute(f"""
        CREATE OR REPLACE TEMP TABLE
            environmental_deaths_classified AS

        SELECT
            killed_by,
            UPPER(TRIM(map)) AS map,
            TRIM(match_id) AS match_id,
            victim_position_x,
            victim_position_y,

            CASE
                WHEN map IS NULL
                  OR TRIM(map) = ''
                    THEN 'missing_map'

                WHEN UPPER(TRIM(map)) NOT IN (
                    'ERANGEL',
                    'MIRAMAR'
                )
                    THEN 'unsupported_map'

                WHEN match_id IS NULL
                  OR TRIM(match_id) = ''
                    THEN 'missing_match_id'

                WHEN victim_position_x IS NULL
                  OR victim_position_y IS NULL
                    THEN 'missing_coordinates'

                -- 0,0은 범위 밖이 아니라 위치 해석이 모호한 좌표다.
                WHEN victim_position_x = 0
                 AND victim_position_y = 0
                    THEN 'zero_zero'

                WHEN victim_position_x < {MIN_COORD}
                  OR victim_position_y < {MIN_COORD}
                  OR victim_position_x > {MAX_COORD}
                  OR victim_position_y > {MAX_COORD}
                    THEN 'out_of_bounds'

                ELSE 'quality_valid'
            END AS quality_status

        FROM environmental_deaths_deduplicated
    """)

    conn.execute("""
        CREATE OR REPLACE TEMP TABLE
            environmental_deaths_quality_filtered AS

        SELECT
            killed_by,
            map,
            match_id,
            victim_position_x,
            victim_position_y
        FROM environmental_deaths_classified
        WHERE quality_status = 'quality_valid'
    """)


def build_match_dates(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """aggregate에서 match_id별 날짜 품질 테이블을 만든다."""

    print("\n[5] match_id별 날짜 테이블 생성")

    conn.execute(f"""
        CREATE OR REPLACE TEMP TABLE match_date_quality AS

        WITH aggregate_date_candidates AS (
            SELECT
                TRIM(match_id) AS match_id,

                TRY_CAST(
                    LEFT(CAST(date AS VARCHAR), 10)
                    AS DATE
                ) AS match_date

            FROM read_csv_auto(
                '{AGGREGATE_GLOB}',
                union_by_name = true
            )
            WHERE match_id IS NOT NULL
              AND TRIM(match_id) <> ''
        )

        SELECT
            match_id,
            MIN(match_date) AS match_date,
            COUNT(DISTINCT match_date) AS distinct_date_count

        FROM aggregate_date_candidates
        GROUP BY match_id
    """)


def build_environmental_deaths_with_date(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """품질 규칙을 통과한 사망 이벤트에 기존 날짜를 연결한다."""

    print("\n[6] 환경 사망 데이터와 날짜 연결")

    conn.execute("""
        CREATE OR REPLACE TEMP TABLE
            environmental_deaths_with_date AS

        SELECT
            deaths.killed_by,
            deaths.map,
            deaths.match_id,

            CASE
                WHEN dates.distinct_date_count = 1
                THEN dates.match_date
                ELSE NULL
            END AS date,

            deaths.victim_position_x,
            deaths.victim_position_y,

            CASE
                WHEN dates.match_id IS NULL
                    THEN 'unmatched_match_id'

                WHEN dates.distinct_date_count = 0
                  OR dates.match_date IS NULL
                    THEN 'missing_or_unparseable_date'

                WHEN dates.distinct_date_count > 1
                    THEN 'ambiguous_date'

                ELSE 'valid_date'
            END AS date_status

        FROM environmental_deaths_quality_filtered AS deaths

        LEFT JOIN match_date_quality AS dates
            ON deaths.match_id = dates.match_id
    """)

    quality_filtered_rows = fetch_count(
        conn,
        """
        SELECT COUNT(*)
        FROM environmental_deaths_quality_filtered
        """,
    )

    joined_rows = fetch_count(
        conn,
        """
        SELECT COUNT(*)
        FROM environmental_deaths_with_date
        """,
    )

    if quality_filtered_rows != joined_rows:
        raise RuntimeError(
            "날짜 조인 후 행 수가 변경됐습니다. "
            f"조인 전={quality_filtered_rows}, 조인 후={joined_rows}"
        )


def build_final_environmental_deaths(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """날짜가 정상적으로 연결된 최종 분석 데이터를 만든다."""

    print("\n[7] 최종 분석 데이터 생성")

    conn.execute("""
        CREATE OR REPLACE TEMP TABLE
            environmental_deaths_clean AS

        SELECT
            killed_by,
            map,
            match_id,
            date,
            victim_position_x,
            victim_position_y

        FROM environmental_deaths_with_date
        WHERE date_status = 'valid_date'
    """)


def show_day1_summary(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """중복되지 않는 단계별 처리 결과를 출력한다."""

    print("\n[8] 1일 차 처리 결과")

    conn.sql("""
        SELECT
            stage_order,
            metric,
            row_count

        FROM (
            SELECT
                1 AS stage_order,
                'environmental_input_rows' AS metric,
                (
                    SELECT COUNT(*)
                    FROM environmental_deaths_raw
                ) AS row_count

            UNION ALL

            SELECT
                2,
                'exact_duplicate_rows_removed',
                (
                    SELECT COUNT(*)
                    FROM environmental_deaths_raw
                ) - (
                    SELECT COUNT(*)
                    FROM environmental_deaths_deduplicated
                )

            UNION ALL

            SELECT
                3,
                'rows_after_deduplication',
                (
                    SELECT COUNT(*)
                    FROM environmental_deaths_deduplicated
                )

            UNION ALL

            SELECT
                4,
                'missing_map_rows',
                COUNT(*) FILTER (
                    WHERE quality_status = 'missing_map'
                )
            FROM environmental_deaths_classified

            UNION ALL

            SELECT
                5,
                'unsupported_map_rows',
                COUNT(*) FILTER (
                    WHERE quality_status = 'unsupported_map'
                )
            FROM environmental_deaths_classified

            UNION ALL

            SELECT
                6,
                'missing_match_id_rows',
                COUNT(*) FILTER (
                    WHERE quality_status = 'missing_match_id'
                )
            FROM environmental_deaths_classified

            UNION ALL

            SELECT
                7,
                'missing_coordinate_rows',
                COUNT(*) FILTER (
                    WHERE quality_status = 'missing_coordinates'
                )
            FROM environmental_deaths_classified

            UNION ALL

            SELECT
                8,
                'zero_zero_rows',
                COUNT(*) FILTER (
                    WHERE quality_status = 'zero_zero'
                )
            FROM environmental_deaths_classified

            UNION ALL

            SELECT
                9,
                'out_of_bounds_rows',
                COUNT(*) FILTER (
                    WHERE quality_status = 'out_of_bounds'
                )
            FROM environmental_deaths_classified

            UNION ALL

            SELECT
                10,
                'quality_valid_rows',
                COUNT(*) FILTER (
                    WHERE quality_status = 'quality_valid'
                )
            FROM environmental_deaths_classified

            UNION ALL

            SELECT
                11,
                'unmatched_match_id_rows',
                COUNT(*) FILTER (
                    WHERE date_status = 'unmatched_match_id'
                )
            FROM environmental_deaths_with_date

            UNION ALL

            SELECT
                12,
                'missing_or_unparseable_date_rows',
                COUNT(*) FILTER (
                    WHERE date_status =
                        'missing_or_unparseable_date'
                )
            FROM environmental_deaths_with_date

            UNION ALL

            SELECT
                13,
                'ambiguous_date_rows',
                COUNT(*) FILTER (
                    WHERE date_status = 'ambiguous_date'
                )
            FROM environmental_deaths_with_date

            UNION ALL

            SELECT
                14,
                'final_analysis_rows',
                (
                    SELECT COUNT(*)
                    FROM environmental_deaths_clean
                )

            UNION ALL

            SELECT
                15,
                'total_excluded_rows',
                (
                    SELECT COUNT(*)
                    FROM environmental_deaths_raw
                ) - (
                    SELECT COUNT(*)
                    FROM environmental_deaths_clean
                )
        ) AS summary

        ORDER BY stage_order
    """).show()


def save_clean_data(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """최종 데이터를 Parquet 파일로 안전하게 교체 저장한다."""

    print("\n[9] Parquet 결과 저장")

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = OUTPUT_PATH.with_suffix(".tmp.parquet")
    temporary_path.unlink(missing_ok=True)

    escaped_path = temporary_path.as_posix().replace(
        "'",
        "''",
    )

    try:
        conn.execute(f"""
            COPY environmental_deaths_clean
            TO '{escaped_path}'
            (
                FORMAT PARQUET,
                COMPRESSION ZSTD
            )
        """)

        temporary_path.replace(OUTPUT_PATH)

    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    output_size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)

    print(f"저장 위치: {OUTPUT_PATH}")
    print(f"파일 크기: {output_size_mb:.2f} MB")


def main() -> None:
    started_at = perf_counter()
    conn = duckdb.connect()

    try:
        build_environmental_source(conn)
        show_environmental_counts(conn)
        show_quality_profile(conn)

        build_quality_classification(conn)
        build_match_dates(conn)
        build_environmental_deaths_with_date(conn)
        build_final_environmental_deaths(conn)

        show_day1_summary(conn)
        save_clean_data(conn)

        elapsed_seconds = perf_counter() - started_at

        print("\n[완료]")
        print(f"총 실행 시간: {elapsed_seconds:.2f}초")

    except Exception:
        elapsed_seconds = perf_counter() - started_at

        print("\n[실패]")
        print(f"실패 전 실행 시간: {elapsed_seconds:.2f}초")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()