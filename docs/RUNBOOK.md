# 운영 및 오류 복구 Runbook

## 목적

환경 사망 분석 파이프라인, PostgreSQL, Superset과 역사 지도 히트맵을
로컬에서 재실행하고 실패 지점을 확인하는 절차를 기록한다.

## 시작 전 확인

```bash
source .venv/bin/activate
df -h .
python --version
docker compose version
```

Python은 3.12를 사용한다. `.env`는 `.env.example`을 기준으로 생성하고
비밀번호와 비밀키를 저장소, 로그, 스크린샷에 포함하지 않는다.

## 전체 실행 순서

```bash
python scripts/build_environmental_deaths.py
python scripts/build_environmental_death_hotspot_detail.py
python scripts/build_environmental_death_hotspot_report.py
python scripts/download_map_assets.py
python scripts/build_environmental_death_heatmaps.py
docker compose up -d --wait postgres superset heatmap-report
python scripts/load_analytics_to_postgres.py
ruff check .
pytest
```

## 서비스 주소

| 서비스 | 주소 | 정상 신호 |
|---|---|---|
| Superset | `http://localhost:8088` | 로그인 화면 또는 대시보드 |
| Superset 상태 | `http://localhost:8088/health` | `OK` |
| 역사 지도 히트맵 | `http://localhost:8000/reports/environmental_death_heatmaps.html` | 지도 패널 4개 |
| PostgreSQL | 로컬 기본 `5433` | `pg_isready` 성공 |

## 상태 확인

```bash
docker compose ps
curl --fail --silent http://localhost:8088/health
curl --fail --silent \
  http://localhost:8000/reports/environmental_death_heatmaps.html \
  > /dev/null
```

## 실패별 대응

| 증상 | 확인 | 복구 |
|---|---|---|
| PostgreSQL 연결 실패 | `.env`의 호스트·포트와 `docker compose ps` | `docker compose up -d --wait postgres` |
| Superset 로그인 실패 | `.env`의 로컬 관리자 변수와 `superset-init` 로그 | 비밀값을 출력하지 말고 초기화 로그 확인 |
| 대시보드에 최신 값이 없음 | `pipeline_runs` 최신 상태와 품질 결과 | `python scripts/load_analytics_to_postgres.py` 재실행 |
| 품질 상태가 `FAIL` | `quality_check_results` 실패 규칙 | 원본·정제 규칙을 확인하고 정상화 전 게시 금지 |
| 히트맵 HTML이 열리지 않음 | `heatmap-report` 상태와 8000 포트 | `docker compose up -d --wait heatmap-report` |
| 히트맵 배경 지도가 없음 | `data/reference/maps/` 파일 존재와 해시 | `python scripts/download_map_assets.py` |
| Superset 차트가 사라짐 | `superset_metadata` 볼륨 존재 | `down -v` 사용 여부 확인 후 BI 문서 기준 재구성 |

## 재실행 원칙

- 원본 CSV는 수정하지 않는다.
- 같은 Parquet의 `batch_id`는 체크섬으로 동일하게 계산한다.
- 실행 이력은 새 `run_id`로 남기고 같은 배치의 공간 집계는 교체한다.
- 품질 검사 하나라도 실패하면 공간 집계를 게시하지 않는다.
- 실패한 실행을 성공으로 수정하지 않고 새 실행으로 복구 결과를 남긴다.

## 안전한 종료와 재시작

```bash
docker compose stop
docker compose up -d --wait
```

`docker compose down`은 명명된 볼륨을 유지하지만 다음 명령은 사용하지 않는다.

```bash
docker compose down -v
docker volume prune
```

위 명령은 PostgreSQL 결과와 Superset 대시보드 메타데이터를 삭제할 수 있다.

## 확인 결과 기록

최종 실행에서는 다음을 README와 단계별 문서에 기록한다.

- 입력·출력·제외 행 수
- 품질 검사 수와 실패 수
- 파이프라인 실행 시간
- 공간 집계 게시 행 수
- Ruff와 pytest 결과
- 구현하지 않은 기능과 남은 제한
