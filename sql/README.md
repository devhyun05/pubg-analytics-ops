# SQL

이 디렉터리는 버전 관리 가능한 SQL을 저장한다.

예정 구분은 다음과 같다.

- 프로파일링 SQL
- 데이터 품질 검사 SQL
- 게임 분석 지표 SQL
- 데이터 운영 지표 SQL
- PostgreSQL 조회용 뷰

실제 컬럼과 조인 키를 확인하기 전에는 지표 SQL을 확정하지 않는다.

## 구현된 SQL

| 파일 | 입력 | 집계 단위 | 목적 |
|---|---|---|---|
| `environmental_death_grid_metrics.sql` | `data/processed/environmental_deaths.parquet` | 맵 + 환경 사망 원인 + 250m 격자 | 반복적인 공간 집중 후보 탐색 |
| `environmental_death_grid_metrics_100m.sql` | `data/processed/environmental_deaths.parquet` | 맵 + 환경 사망 원인 + 전역 100m 격자 | 더 세밀한 공간 집중 후보 탐색 |
| `environmental_death_resolution_comparison.sql` | 250m·100m 상위 후보 TEMP VIEW | 100m 후보 격자 | 두 해상도 후보의 공간 겹침 비교 |
| `environmental_death_hotspot_report.sql` | 250m 상위 후보 TEMP VIEW | 후보 격자 | 사람이 읽을 수 있는 보고서 필드와 요약 문장 생성 |

250m 격자는 전체 맵에서 후보 지역을 찾기 위한 1차 탐색 단위다. 상위 후보는
100m와 50m 격자 또는 원본 좌표로 다시 확인한다.

최종 출력은 맵과 환경 사망 원인 조합별 상위 10순위 후보만 표시한다.
`DENSE_RANK`의 공동 순위가 있으면 조합별 출력 행 수가 10개를 넘을 수 있다.

보고서용 결과는 다음 명령으로 생성한다.

```bash
python scripts/build_environmental_death_hotspot_report.py
```

전체 후보는 CSV와 Parquet으로 저장하고, 터미널에는 맵과 원인별 상위 3개
요약 문장을 출력한다.

100m 전역 재격자와 250m 후보 비교 결과는 다음 명령으로 생성한다.

```bash
python scripts/build_environmental_death_hotspot_detail.py
```

250m는 100m로 균등하게 나누어지지 않으므로 100m 격자는 전체 맵에서
독립적으로 계산한다. 이후 100m 상위 후보와 가장 많이 겹치는 250m 상위 후보를
연결해 해상도가 달라져도 집중 후보가 유지되는지 확인한다.
