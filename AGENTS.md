# AGENTS.md

## Project purpose

이 저장소는 KRAFTON Data Analytics Operation 인턴 지원을 위한
3일 포트폴리오 프로젝트다.

프로젝트 목표는 대규모 PUBG 경기·사망 이벤트를 분석하는 것이 아니라,
분석가가 데이터를 안정적으로 사용할 수 있도록 다음 업무를 자동화하는 것이다.

- 대규모 원본 데이터 프로파일링
- 데이터 정제 및 Parquet 변환
- 데이터 품질 검사
- SQL 지표 생성
- 파이프라인 실행 이력 관리
- Superset 대시보드 제공
- 이상 데이터 및 운영 상태 리포트 자동 생성

## Target job requirements

구현과 문서는 다음 역량을 명확하게 증명해야 한다.

- Python 데이터 처리 및 반복 작업 자동화
- SQL 집계·필터·조인
- 데이터 품질 검토
- 이벤트 스키마 문서화
- BI 도구 사용
- 지표 모니터링 및 이상값 감지
- LLM을 활용한 운영 효율 개선
- Git 기반 개발 및 문서화

## Fixed architecture

- Python 3.12
- DuckDB
- Parquet
- PostgreSQL
- Apache Superset
- Docker Compose
- pytest
- Ruff

원본 CSV 전체를 PostgreSQL에 적재하지 않는다.

- 원본·상세 이벤트: Parquet
- 대규모 조회 및 정제: DuckDB
- 품질 검사 결과·실행 이력·집계 테이블: PostgreSQL
- BI 대시보드: Superset

## Data rules

- 실제 데이터 파일은 Git에 커밋하지 않는다.
- 데이터셋 컬럼과 의미를 추측하지 않는다.
- 실제 샘플 파일을 확인한 뒤 스키마를 정의한다.
- 전체 데이터셋 규모와 실제 처리한 행 수를 구분해 기록한다.
- 처리하지 않은 데이터를 처리했다고 표현하지 않는다.
- 데이터 라이선스와 출처를 docs/DATA_SOURCE.md에 기록한다.
- 개인정보나 API 키를 코드에 하드코딩하지 않는다.
- 분석·조회 쿼리는 `analyst_ro` 계정을 사용한다. 적재 계정으로 조회하지 않는다.

### Deaths CSV glossary

쿼리를 작성할 때 deaths CSV 컬럼의 의미를 다음 기준으로 해석한다.

원본 컬럼 순서는 다음과 같다.

`killed_by`, `killer_name`, `killer_placement`, `killer_position_x`,
`killer_position_y`, `map`, `match_id`, `time`, `victim_name`,
`victim_placement`, `victim_position_x`, `victim_position_y`

- `killed_by`: 피해자를 사망 처리한 무기 또는 원인을 의미한다. 총기·투척 무기뿐 아니라 `Falling`, `Drown`, `Down and Out` 같은 원인도 포함한다.
- `killer_name`: 사망 이벤트에서 가해자로 기록된 player 이름을 의미한다. 환경 사망이나 자기 사망에서는 다른 player의 이름이 아닐 수 있다.
- `killer_placement`: 가해자로 기록된 player의 해당 경기 최종 순위를 의미한다. 사망 이벤트 발생 시점의 실시간 순위가 아니다.
- `killer_position_x`: 사망 이벤트 발생 시점에 가해자로 기록된 player의 X좌표를 의미한다.
- `killer_position_y`: 사망 이벤트 발생 시점에 가해자로 기록된 player의 Y좌표를 의미한다.
- `map`: 사망 이벤트가 발생한 경기의 맵을 의미한다.
- `match_id`: 사망 이벤트가 속한 경기를 식별하는 ID를 의미한다. 같은 경기에서 발생한 이벤트는 같은 `match_id`를 가진다.
- `time`: 경기 시작 후 사망 이벤트가 발생하기까지의 경과 시간을 초 단위로 의미한다.
- `victim_name`: 해당 사망 이벤트에서 사망한 player의 이름을 의미한다.
- `victim_placement`: 사망한 player의 해당 경기 최종 순위를 의미한다. 사망 시점의 생존 인원 순위와 동일하다고 단정하지 않는다.
- `victim_position_x`: 사망 이벤트 발생 시점에 피해자로 기록된 player의 X좌표를 의미한다.
- `victim_position_y`: 사망 이벤트 발생 시점에 피해자로 기록된 player의 Y좌표를 의미한다.

컬럼명의 `killer`와 `victim`은 원본 스키마의 구분이다. 컬럼명만 보고
모든 사망 이벤트에 실제 가해자가 존재한다고 추정하지 않는다.
특히 `Falling`, `Drown`처럼 사람에게 사살된 이벤트가 아닌 경우에는
`killer_name`, `killer_placement`, `killer_position_x`,
`killer_position_y`를 실제 가해자 정보라고 해석하지 않는다.

## Engineering rules

- 함수와 모듈에 타입 힌트를 사용한다.
- 큰 CSV를 pandas로 한 번에 메모리에 올리지 않는다.
- 동일 배치를 재실행해도 결과가 중복되지 않도록 구현한다.
- 각 파이프라인 실행의 입력 행 수, 출력 행 수, 실패 수, 소요 시간을 기록한다.
- 예외를 무시하거나 빈 except 문을 사용하지 않는다.
- 핵심 데이터 품질 규칙에는 pytest를 작성한다.
- 새로운 의존성을 추가하기 전 필요성을 설명한다.
- 구현 후 Ruff와 pytest를 실행한다.
- 사용자 승인 없이 commit 또는 push하지 않는다.

## Documentation

다음 문서를 유지한다.

- README.md: 프로젝트 목적, 실행 방법, 핵심 결과
- PLAN.md: 구현 단계와 진행 상태
- docs/ARCHITECTURE.md: 전체 구조
- docs/DATA_SOURCE.md: 데이터 출처와 사용 범위
- docs/DATA_DICTIONARY.md: 이벤트 스키마
- docs/QUALITY_RULES.md: 품질 검사 정의
- docs/RUNBOOK.md: 오류 발생 시 운영 절차
- docs/DECISIONS.md: 기술 선택과 이유

### Continuous documentation workflow

- 각 사용자 프롬프트를 처리할 때 현재 작업과 가장 관련된 문서를 식별한다.
- 새 측정값, 결정, 범위, 용어 또는 진행 상태가 생기면 같은 작업 내에 문서를 갱신한다.
- `PLAN.md`에는 현재 단계, 완료한 작업, 다음 작업과 미완료 항목을 반영한다.
- 대화 내용을 그대로 복사하지 않고 확인된 사실, 결정 근거, 한계와 다음 행동만 통합한다.
- 측정 결과에는 입력 범위, 처리 행 수, 제외 행 수, 실행 시간과 실행 방법을 기록한다.
- 구현하거나 측정하지 않은 내용은 완료 상태 또는 실제 결과로 기록하지 않는다.
- 최종 응답에는 이번 프롬프트에서 갱신한 문서를 명시한다.

작업별 주요 문서는 다음과 같다.

- 데이터 출처와 입력: `docs/01_DATA_SOURCE_AND_INPUT.md`
- 원본 프로파일링: `docs/02_DATA_PROFILING.md`
- Python 처리: `docs/03_PYTHON_PROCESSING.md`
- 데이터 품질 규칙: `docs/04_DATA_QUALITY.md`
- SQL 지표: `docs/05_SQL_METRICS.md`
- 결과 저장과 실행 이력: `docs/06_RESULT_STORAGE.md`
- BI 대시보드: `docs/07_BI_DASHBOARD.md`
- AI 운영 리포트: `docs/08_AI_REPORT_AUTOMATION.md`
- 문제 정의와 분석 범위: `docs/09_HISTORICAL_CONTEXT_AND_PLAYER_ISSUES.md`
- 공통 용어: `docs/10_GLOSSARY.md`

## Definition of done

작업 완료라고 보고하기 전에 다음을 확인한다.

- 코드가 실제 샘플 데이터에서 실행되는가
- pytest가 통과하는가
- Ruff 검사가 통과하는가
- 실행 명령이 README에 기록됐는가
- 처리 행 수와 실행 시간이 측정됐는가
- 구현하지 않은 기능을 완료했다고 표현하지 않았는가
