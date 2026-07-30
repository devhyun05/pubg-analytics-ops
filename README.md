# PUBG Analytics Operations

PUBG 경기 및 사망 이벤트 데이터를 분석가가 안정적으로 사용할 수 있도록 프로파일링, 정제, 품질 검사, 지표 계산과 운영 상태 보고를 자동화하는 포트폴리오 프로젝트다.

현재 저장소에는 전체 deaths·aggregate 입력 프로파일러와 환경 사망 정제
파이프라인이 구현되어 있다. 공간 집중 지표, PostgreSQL 적재, Superset
대시보드와 AI 운영 보고서는 아직 구현하지 않았으며 완료 여부를 구분해
기록한다.

## Architecture

```text
Kaggle raw CSV
→ DuckDB profiling
→ Python processing
→ curated Parquet
→ data quality checks
→ DuckDB SQL metrics
→ PostgreSQL result tables
→ Superset dashboards
→ AI operations report
```

- 원본과 상세 데이터: 로컬 파일 및 Parquet
- 대규모 조회와 변환: DuckDB
- 실행 이력, 품질 결과, 집계 지표: PostgreSQL
- 시각화: Apache Superset

## Dataset

- 이름: PUBG Match Deaths and Statistics
- Kaggle 식별자: `skihikingkevin/pubg-match-deaths`
- 표시 라이선스: CC0: Public Domain
- 공개 논리 파일 크기: 약 20.28 GB
- 원천 후보: `pubg.op.gg`

원본 데이터와 인증 토큰은 Git에 커밋하지 않는다. 출처와 재배포 주의사항은 [데이터 출처 문서](docs/01_DATA_SOURCE_AND_INPUT.md)를 따른다.

## Local setup

Python 3.12를 사용한다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,download]"
```

환경변수 파일이 필요하면 비밀값이 없는 예시를 기준으로 로컬 `.env`를 만든다. `.env`는 Git에서 제외된다.

## Dataset download

다운로드 전에 Kaggle 계정 인증과 디스크 여유 공간을 확인한다.

```bash
df -h .
kaggle auth login
kaggle datasets files skihikingkevin/pubg-match-deaths
kaggle datasets download \
  -d skihikingkevin/pubg-match-deaths \
  -p data/raw
```

다운로드한 압축 파일은 `data/raw/`에 보관하고 수정하지 않는다. 압축 해제본은
`data/staged/`, 재생성 가능한 정제 결과는 `data/processed/`, 품질 검증을
통과해 최종 채택한 데이터는 `data/curated/`에 저장한다.

## Environmental death pipeline

현재 구현은 deaths CSV 5개에서 `Falling`과 `Drown`을 선택하고 완전 중복,
맵, 좌표, `0,0`, 공식 좌표 범위와 날짜 연결 규칙을 적용한다.

```bash
python scripts/build_environmental_deaths.py
```

2026-07-31 전체 입력 실행 결과:

| 항목 | 결과 |
|---|---:|
| 환경 사망 원본 후보 | 980,079행 |
| 완전 중복 추가분 | 65행 |
| 최종 분석 가능 | 793,356행 |
| 전체 제외 | 186,723행 |
| Parquet 출력 크기 | 37.58 MB |
| 실행 시간 | 19.17초 |

출력은 `data/processed/environmental_deaths.parquet`에 생성되며 실제 데이터
파일은 Git에 커밋하지 않는다. Parquet의 성능 우위는 아직 측정하지 않았으므로
CSV와의 조회 시간 비교 전에는 개선 효과를 주장하지 않는다.

## Quality checks

프로젝트 기반 코드의 기본 검사는 다음과 같다.

```bash
ruff check .
pytest
```

실제 데이터 품질 규칙과 테스트는 데이터 프로파일링 후 확정한다.

## Documentation

- [전체 프로세스 흐름](docs/00_END_TO_END_FLOW.md)
- [데이터 출처 및 입력](docs/01_DATA_SOURCE_AND_INPUT.md)
- [데이터 프로파일링](docs/02_DATA_PROFILING.md)
- [Python 처리](docs/03_PYTHON_PROCESSING.md)
- [데이터 품질](docs/04_DATA_QUALITY.md)
- [SQL 지표](docs/05_SQL_METRICS.md)
- [결과 저장](docs/06_RESULT_STORAGE.md)
- [BI 대시보드](docs/07_BI_DASHBOARD.md)
- [AI 보고서](docs/08_AI_REPORT_AUTOMATION.md)

구현 순서와 현재 상태는 [PLAN.md](PLAN.md)를 참고한다.
