# 리포트

## 환경 사망 공간 리포트

- 인터랙티브 결과: `reports/environmental_death_heatmaps.html`
- 해석 및 QA 후보: `reports/environmental_death_hotspot_findings.md`
- 생성 스크립트: `scripts/build_environmental_death_heatmaps.py`
- 집계 SQL: `sql/environmental_death_heatmap_cells.sql`

생성 순서:

```bash
python scripts/download_map_assets.py
python scripts/build_environmental_death_heatmaps.py
docker compose up -d --wait heatmap-report
```

브라우저에서
`http://localhost:8000/reports/environmental_death_heatmaps.html`을 연다.
Superset 대시보드의 `당시 지도 기반 히트맵 열기` 링크도 같은 주소를 사용한다.

히트맵은 Erangel·Miramar와 Drown·Falling의 네 조합을 100m 격자로 보여준다. 맵·원인별 상위 3개 격자를 강조하고 사망 건수, 고유 경기 수, 날짜 수, 원인 내 비중을 툴팁으로 제공한다.

배경 지도는 현행 PUBG API 지도가 아니라 2017년 제3자 WebMap 저장소의 고정 커밋에서 내려받는다. 파일 해시를 검증하며 지도 바이너리는 Git에 포함하지 않는다. 이 지도는 공간 가설을 세우는 참고 자료이고, 오브젝트 수준의 원인 확정에는 QA 재현이 필요하다.

`heatmap-report`는 `reports/`와 `data/reference/maps/`만 읽기 전용으로
공개한다. `.env`, 원본 CSV와 Parquet은 HTTP 서비스 경로에 포함하지 않는다.
