# PUBG 공개 사망 이벤트 스키마

## 1. 문서 범위

이 문서는 Kaggle의 PUBG Match Deaths and Statistics 데이터에서 직접 확인한
deaths CSV와 aggregate CSV의 스키마를 정리한 문서다.

이 데이터가 PUBG 클라이언트나 게임 서버의 실제 SDK payload라는 근거는
확인하지 못했다. 따라서 공식 PUBG SDK 스키마라고 표현하지 않고, 공개된
사망 이벤트 데이터를 SDK 이벤트 스키마를 검토하는 방식으로 문서화했다.

문서에는 실제 CSV에 존재하는 컬럼과 실제 파이프라인에서 사용한 관계만
기록한다. 원본에 없는 이벤트 ID, 발생 UTC 시각, 게임 빌드, 맵 버전,
Z축 좌표를 새로 만들어 원본 필드처럼 설명하지 않는다.

## 2. 필요한 컬럼을 고른 과정

처음에는 사망 원인과 피해자 좌표만 있으면 환경 사망 위치를 찾을 수 있다고
생각했다. 하지만 좌표만으로는 어느 맵인지 구분할 수 없고, 같은 장소의
사망이 한 경기에서만 나온 것인지 여러 경기에서 반복된 것인지도 알 수 없었다.

그래서 다음 순서로 필요한 컬럼을 정했다.

| 확인하려는 내용 | 필요한 실제 컬럼 | 선택 이유 |
|---|---|---|
| 추락과 익사 구분 | killed_by | Falling과 Drown을 정확히 구분한다. |
| 맵 구분 | map | 에란겔과 미라마 좌표를 섞지 않는다. |
| 경기 반복 여부 | match_id | 같은 위치가 여러 경기에서 반복됐는지 센다. |
| 사망 위치 | victim_position_x, victim_position_y | 피해자가 사망한 위치를 격자로 계산한다. |
| 날짜 반복 여부 | aggregate의 date | 여러 날짜에서 반복됐는지 확인한다. |
| 경기 진행 시점 | time | 경기 초반·중반·후반을 나눈다. |
| 경기 중 이동량 | player_dist_walk, player_dist_ride | 정지 상태나 착지 직후라는 해석을 다시 확인한다. |

killer_name, killer_placement, killer_position_x, killer_position_y,
victim_placement는 환경 사망의 위치 집중도를 계산하는 데 직접 필요하지 않아
핵심 분석 컬럼에서 제외했다.

victim_name은 공개 결과에 사용하지 않았다. deaths의 피해자와 aggregate의
플레이어 통계를 연결해 누적 이동 거리를 확인할 때만 사용했다.

## 3. 원본 파일과 행 단위

### 3.1 deaths CSV

파일 패턴은 kill_match_stats_final_*.csv다.

한 행은 데이터에 기록된 사망 이벤트 한 건이다. 다만 원본에는 event_id가
없으므로 서로 다른 두 행이 실제로 같은 사건인지 완전히 확인할 수는 없다.

### 3.2 aggregate CSV

파일 패턴은 agg_match_stats_*.csv다.

한 행은 한 경기에서 한 플레이어가 기록한 경기 통계다. 한 match_id에 여러
플레이어 행이 존재하므로 match_id만으로 aggregate 한 행을 고유하게 식별할
수 없다.

## 4. deaths CSV 실제 스키마

| 순서 | 컬럼 | DuckDB 논리 타입 | 값의 의미 | 환경 사망 분석 사용 |
|---:|---|---|---|---:|
| 1 | killed_by | VARCHAR | 데이터에 기록된 사망 원인 또는 무기명 | Y |
| 2 | killer_name | VARCHAR | 가해자로 기록된 플레이어 이름 | N |
| 3 | killer_placement | DOUBLE | 가해자의 경기 순위 값 | N |
| 4 | killer_position_x | DOUBLE | 가해자 X 좌표 | N |
| 5 | killer_position_y | DOUBLE | 가해자 Y 좌표 | N |
| 6 | map | VARCHAR | 맵 이름 | Y |
| 7 | match_id | VARCHAR | 경기 식별자 | Y |
| 8 | time | BIGINT | 경기 안에서 사망이 기록된 경과 시간 | 보조 |
| 9 | victim_name | VARCHAR | 피해자로 기록된 플레이어 이름 | 조인에만 사용 |
| 10 | victim_placement | DOUBLE | 피해자의 경기 순위 값 | N |
| 11 | victim_position_x | DOUBLE | 피해자 X 좌표 | Y |
| 12 | victim_position_y | DOUBLE | 피해자 Y 좌표 | Y |

위 12개 컬럼이 deaths CSV에서 직접 확인한 전체 컬럼이다.

## 5. aggregate CSV 실제 스키마

| 순서 | 컬럼 | DuckDB 논리 타입 | 값의 의미 | 현재 사용 |
|---:|---|---|---|---:|
| 1 | date | VARCHAR, 파싱 후 DATE | 경기 날짜 | Y |
| 2 | game_size | BIGINT | 경기 참여 인원 수 | N |
| 3 | match_id | VARCHAR | 경기 식별자 | Y |
| 4 | match_mode | VARCHAR | 경기 모드 | N |
| 5 | party_size | BIGINT | 팀 크기 | N |
| 6 | player_assists | BIGINT | 어시스트 수 | N |
| 7 | player_dbno | BIGINT | DBNO 횟수 | N |
| 8 | player_dist_ride | DOUBLE | 차량 누적 이동 거리 | 보조 |
| 9 | player_dist_walk | DOUBLE | 도보 누적 이동 거리 | 보조 |
| 10 | player_dmg | DOUBLE | 플레이어가 가한 피해량 | N |
| 11 | player_kills | BIGINT | 플레이어 킬 수 | N |
| 12 | player_name | VARCHAR | 플레이어 이름 | 조인에만 사용 |
| 13 | player_survive_time | DOUBLE | 생존 시간 | 보조 |
| 14 | team_id | BIGINT | 경기 안의 팀 식별값 | N |
| 15 | team_placement | BIGINT | 팀 순위 | N |

위 15개 컬럼이 aggregate CSV에서 직접 확인한 전체 컬럼이다.

## 6. 두 파일의 관계

deaths와 aggregate에는 공통으로 match_id가 있다. 이 값을 이용해 사망
이벤트에 경기 날짜를 연결했다.

deaths에는 date 컬럼이 없다. 분석 결과에 사용한 날짜는 새로 만든 날짜가
아니라 aggregate에 실제 존재하는 date를 match_id로 연결한 값이다.

날짜 연결 규칙은 다음과 같다.

1. aggregate에서 match_id와 date만 읽는다.
2. 같은 match_id에 유효한 날짜가 몇 개인지 확인한다.
3. 날짜가 정확히 하나인 match_id만 날짜 테이블에 남긴다.
4. deaths의 match_id와 정확히 같은 경우에만 날짜를 연결한다.
5. 연결되지 않거나 날짜가 여러 개인 행은 날짜 기반 분석에서 제외한다.

파일명, 행 위치, 앞뒤 경기의 날짜를 이용해 누락된 날짜를 추정하지 않았다.

## 7. 이동 거리 연결

피해자의 누적 이동 거리는 match_id와 플레이어 이름을 함께 사용해 연결했다.

| deaths | aggregate |
|---|---|
| match_id | match_id |
| victim_name | player_name |

같은 match_id와 이름에 해당하는 aggregate 행이 하나일 때만 이동 거리를
사용한다. 일치하는 행이 없거나 여러 행이 생기면 자동으로 합산하지 않고
연결 실패 또는 모호한 연결로 분리한다.

player_dist_walk와 player_dist_ride는 경기 전체에서 누적된 이동 거리다.
사망 직전 몇 초 동안의 이동 거리나 실제 이동 경로가 아니므로, 이 값만으로
추락 직전 행동을 확정하지 않았다.

## 8. 사망 원인 선택

현재 분석에서 환경 사망으로 사용한 값은 다음 두 개다.

| killed_by 원본 값 | 분석 표현 | 포함 |
|---|---|---:|
| Falling | 추락 | Y |
| Drown | 익사 | Y |
| 그 외 값 | 현재 분석 범위 밖 | N |

Falling과 Drown은 killed_by에 실제 존재하는 값이다. 별도의 사망 원인 컬럼을
만들어 원본인 것처럼 사용하지 않았다.

Bluezone, RedZone, Vehicle, Down and Out 등은 이름만 보고 환경 사망으로
합치지 않았다. 각 값의 이벤트 의미를 확인하지 않은 상태에서 같은 범주로
묶으면 결과가 달라질 수 있기 때문이다.

## 9. 필수값 판단

원본 CSV에 컬럼이 존재하는 것과 각 행의 값이 분석에 필요한 것은 다른
문제다.

| 컬럼 | 환경 사망 위치 분석에서 필요한 이유 | 값이 없을 때 처리 |
|---|---|---|
| killed_by | 추락·익사 선택 | 분석 대상 여부를 정할 수 없어 제외 |
| map | 맵별 좌표 구분 | 위치 분석에서 제외 |
| match_id | 경기 수 계산과 날짜 연결 | 최종 분석에서 제외 |
| victim_position_x | X축 격자 계산 | 공간 분석에서 제외 |
| victim_position_y | Y축 격자 계산 | 공간 분석에서 제외 |
| date | 날짜 반복 확인 | 날짜 기반 최종 분석에서 제외 |

killer 관련 컬럼과 placement는 값이 없더라도 현재 환경 사망 위치 분석의
핵심 질문에는 영향을 주지 않으므로 필수값으로 두지 않았다.

## 10. 좌표 판단

victim_position_x와 victim_position_y는 원본 CSV에 실제 존재하는 숫자
컬럼이다. 반면 좌표 단위, 좌표계 버전, Z축은 CSV 컬럼으로 제공되지 않는다.

현재 공간 분석에서는 다음 규칙을 적용했다.

| 검사 | 현재 처리 |
|---|---|
| X 또는 Y가 NULL | 공간 분석에서 제외 |
| X와 Y가 모두 0 | 별도 집계 후 공간 분석에서 제외 |
| X 또는 Y가 0 미만 | 공간 분석에서 제외 |
| X 또는 Y가 816,000 초과 | 공간 분석에서 제외 |
| 나머지 좌표 | 격자 계산에 사용 |

0~816,000은 현재 에란겔·미라마 데이터를 분석할 때 사용한 품질 범위다.
모든 PUBG 맵에 적용되는 공식 SDK 제약이라고 표현하지 않는다.

(0,0)은 숫자 값이므로 NULL과 다르다. 하지만 실제 맵 위치로 해석하기
어려워 이번 공간 분석에서 제외했다. 이 값이 비행기 시작점, 잠수 플레이,
게임 이탈 또는 수집 오류라는 근거는 없으므로 원인을 단정하지 않았다.

원본 좌표 단위는 행 안에 기록되어 있지 않다. 격자를 미터로 표현할 때 사용한
좌표 변환 근거는 DATA_SOURCE.md와 DATA_DICTIONARY.md에서 출처와 함께
관리한다.

## 11. 시간과 날짜

time은 deaths에 실제 존재하지만 date는 deaths에 없다.

| 값 | 원본 위치 | 현재 해석 |
|---|---|---|
| time | deaths | 경기 안에서의 경과 시간 |
| date | aggregate | 경기 날짜 |

time은 UTC 시각이 아니다. date와 time을 더해 정확한 이벤트 발생 시각을
만들지 않았다. 원본에는 시간대와 경기 시작 UTC 시각이 없기 때문이다.

분석 결과에서 match_date라는 이름을 사용한 경우, 이는 aggregate의 date를
match_id로 연결한 뒤 의미를 분명히 하기 위해 이름을 바꾼 파생 컬럼이다.
원본 deaths 컬럼이라고 표현하지 않는다.

## 12. 중복 판단

deaths 원본에는 event_id가 없다. 따라서 event_id를 기준으로 재전송된
이벤트를 찾는 방식은 사용할 수 없었다.

현재 파이프라인은 deaths의 12개 원본 컬럼이 모두 같은 행만 완전 중복으로
판단한다.

일부 컬럼만 같은 경우는 자동으로 제거하지 않았다. 같은 경기, 같은 피해자,
같은 시간과 비슷한 좌표가 나타나더라도 나머지 값이 다르면 별도 사건일
가능성을 원본만으로 배제할 수 없기 때문이다.

분석 과정에서 확인한 중복 후보 그룹은 별도로 측정하고, 완전 중복과 같은
규칙으로 삭제하지 않았다.

## 13. 원본 컬럼과 파생값 구분

| 구분 | 값 | 설명 |
|---|---|---|
| 원본 deaths 컬럼 | killed_by, map, match_id, time, victim_position_x, victim_position_y 등 | deaths CSV에 직접 존재 |
| 원본 aggregate 컬럼 | date, match_mode, party_size, player_dist_walk, player_dist_ride 등 | aggregate CSV에 직접 존재 |
| 조인 파생값 | match_date | aggregate.date를 match_id로 연결한 값 |
| 공간 파생값 | grid_x, grid_y, grid_size_m | 피해자 좌표와 선택한 격자 크기로 계산 |
| 집계 지표 | death_count, match_count, active_date_count, cause_share | 원본 이벤트를 그룹화해 계산 |

파생값은 분석에 사용할 수 있지만 원본 컬럼이라고 부르지 않는다. 파생 규칙이
바뀌면 같은 원본에서도 결과가 달라질 수 있으므로 계산 방법을 SQL과 문서에
함께 남긴다.

## 14. 개인정보 처리

killer_name, victim_name, player_name은 공개 데이터에 포함되어 있지만
플레이어를 식별할 수 있는 값이다.

현재 프로젝트에서는 다음 기준을 적용했다.

- 플레이어 이름을 GitHub 데이터와 공개 리포트에 표시하지 않는다.
- 이름은 deaths와 aggregate를 연결하는 처리 과정에서만 사용한다.
- 개인 플레이어 순위나 의심 사용자 목록을 만들지 않는다.
- PostgreSQL 집계 결과와 Superset 대시보드에는 집계값만 제공한다.
- API 키와 인증 토큰은 데이터 파일과 저장소에 기록하지 않는다.

## 15. 스키마 변경 확인

새 CSV 파일을 처리할 때는 기존 컬럼이 그대로 있다고 가정하지 않는다.

| 확인 항목 | 이유 |
|---|---|
| 컬럼 이름과 개수 | 컬럼 추가·삭제·이름 변경 탐지 |
| DuckDB 추론 타입 | 숫자 컬럼의 문자열 변환 탐지 |
| NULL과 빈 문자열 | 필수 분석값 누락 탐지 |
| map 신규 값 | 지원하지 않는 맵의 잘못된 좌표 적용 방지 |
| killed_by 신규 값 | 사망 원인 분류 누락 확인 |
| 좌표 범위 | 기존 맵과 다른 좌표계 탐지 |
| match_id 날짜 유일성 | 잘못된 날짜 조인 방지 |

스키마가 달라지면 새 값을 조용히 버리지 않고 먼저 프로파일링 결과에 남긴다.
분석 규칙을 변경할 때는 변경 이유와 전후 행 수를 함께 기록한다.

## 16. 현재 스키마로 확인할 수 있는 범위

현재 컬럼으로 확인할 수 있는 내용은 다음과 같다.

- 추락과 익사가 어느 X·Y 좌표에서 반복됐는가
- 해당 위치가 몇 경기와 몇 날짜에서 관측됐는가
- 같은 격자의 전체 사망 중 추락 또는 익사의 비중은 얼마인가
- 해당 사망이 경기의 어느 시점에 기록됐는가
- 피해자가 경기 전체에서 얼마나 걷고 차량으로 이동했는가

현재 컬럼으로 확인할 수 없는 내용은 다음과 같다.

- 해당 위치를 방문한 전체 플레이어 수
- 방문자 기준 실제 사망 확률
- 사망 직전 이동 경로
- 추락한 높이
- 충돌한 지형이나 오브젝트
- 당시 게임 빌드와 정확한 맵 버전
- (0,0) 좌표가 기록된 실제 이유

확인할 수 없는 값을 추정해 결론을 만들지 않고, 분석 결과에서는 QA가 먼저
확인할 위치를 정하는 수준으로 사용했다.

## 17. 관련 문서

| 문서 | 역할 |
|---|---|
| DATA_SOURCE.md | 데이터 출처, 기간과 라이선스 |
| DATA_DICTIONARY.md | 원본 컬럼의 상세 의미 |
| 04_DATA_QUALITY.md | 실제 품질 검사 규칙과 측정 결과 |
| RUNBOOK.md | 파이프라인 오류와 운영 대응 |
| DECISIONS.md | 기술 선택과 변경 이유 |
