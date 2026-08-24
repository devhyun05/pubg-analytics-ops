# 데이터 사전

> 문서 상태: 현재 분석 컬럼 기준 초안
>
> 확인 기준: 로컬 deaths·aggregate CSV 전체 프로파일링

## 1. 목적

현재 환경 사망 집중 지역 분석에 사용하는 컬럼의 출처, 관측 타입, 역할과
품질 상태를 기록한다. 확인되지 않은 의미는 추정해 확정하지 않는다.

현재 데이터로 작성한 실무형 SDK 문서 예시는
[SDK_EVENT_SCHEMA.md](SDK_EVENT_SCHEMA.md)에서 확인한다. 이
예시는 공식 PUBG SDK 명세가 아니라 원본·파생·제안 필드를 구분한 설계안이다.

## 2. deaths 핵심 컬럼

deaths 원본의 한 행은 사망 이벤트 후보를 나타낸다. 중복 검사가 완료됐지만
상세값이 다른 이벤트 후보의 의미가 남아 있어 grain은 계속 검증한다.

| 컬럼 | 관측 형태 | 현재 역할 | 확인된 품질 상태 |
|---|---|---|---|
| `killed_by` | 문자열 | 사망 원인 분류 | NULL·빈 값 0 |
| `map` | 문자열 | 에란겔·미라마 구분 | NULL 783,392행 |
| `match_id` | 문자열 | 경기 식별과 날짜 연결 | NULL·빈 값 0 |
| `time` | 숫자 변환 가능 문자열 | 경기 내 사건 순서·분포 비교 후보 | 변환 실패 0, 시간 기준 의미 추가 확인 필요 |
| `victim_position_x` | 숫자 변환 가능 문자열 | 피해자 X 좌표 | NULL·변환 실패 0, 별도 좌표 규칙 적용 |
| `victim_position_y` | 숫자 변환 가능 문자열 | 피해자 Y 좌표 | NULL·변환 실패 0, 별도 좌표 규칙 적용 |

## 2.1. killed_by 분석 분류

`killed_by`에는 58개 값이 관측됐다. 현재 프로젝트는 다음 두 값만
`지형 기반 환경 사망`으로 정의한다.

| 값 | 원본 행 | 품질 규칙 통과 행 | 현재 역할 |
|---|---:|---:|---|
| `Falling` | 708,367 | 687,104 | 지형 낙하 위치 분석 |
| `Drown` | 271,712 | 106,252 | 물·익사 위치 보조 분석 |

이 분류는 PUBG의 공식 전체 환경 사망 분류가 아니라 현재 분석 질문을 위해
프로젝트가 정한 범위다.

`Bluezone`, `RedZone`, 차량과 화염 원인도 비총기 또는 비전투 후보가 될 수
있지만 발생 메커니즘과 필요한 분모가 다르므로 현재 메인 지표에 합치지 않는다.

## 3. map

### 확인된 값

```text
ERANGEL
MIRAMAR
NULL
```

| 값 | 행 수 | 고유 `match_id` |
|---|---:|---:|
| `ERANGEL` | 52,964,245 | 579,541 |
| `MIRAMAR` | 11,622,838 | 133,991 |
| NULL | 783,392 | 8,893 |

`map` NULL은 전체 deaths의 1.198388%다.

### 경기 단위 관계

- `map`이 NULL인 8,893개 경기에서는 모든 deaths 행의 `map`이 NULL이다.
- 같은 경기의 다른 행으로 복구 가능한 NULL은 0행이다.
- 하나의 `match_id`에 에란겔과 미라마가 함께 기록된 경기는 0개다.
- aggregate 원본에는 `map` 컬럼이 없어 aggregate에서 복구하지 않는다.

### 분석 사용 규칙

```text
전체 사망 원인 집계:
map NULL 포함 가능

맵별 집계·좌표 격자·핫스팟:
map NULL 제외

제외 사유:
MISSING_MAP
```

좌표, 파일명, 날짜 또는 다른 경기의 맵으로 NULL을 채우지 않는다. 원본 행과
NULL 값은 그대로 보존한다.

## 4. aggregate 날짜 연결

deaths에는 날짜가 없고 aggregate에는 `date`가 존재한다. 경기당 날짜가 하나인
것을 확인한 뒤 정확히 같은 `match_id`로만 연결해 `match_date`라는 분석용
이름을 사용한다. 연결되지 않은 행에는 날짜를 생성하지 않는다.

## 5. 미확정 항목

- `time`의 정확한 시작 기준과 단위에 대한 원본 제공자 설명
- 상세값이 다른 사망 이벤트 후보의 의미
- 현재 분석에 사용하지 않는 deaths·aggregate 컬럼의 전체 의미와 품질 상태

## 6. 파일별 확인 타입

deaths 5개와 aggregate 5개의 전체 값을 DuckDB로 읽어 추론한 결과, 각 파일
그룹 안에서 컬럼 이름, 순서와 타입이 모두 일치했다.

### deaths

```text
killed_by: VARCHAR
killer_name: VARCHAR
killer_placement: DOUBLE
killer_position_x: DOUBLE
killer_position_y: DOUBLE
map: VARCHAR
match_id: VARCHAR
time: BIGINT
victim_name: VARCHAR
victim_placement: DOUBLE
victim_position_x: DOUBLE
victim_position_y: DOUBLE
```

### aggregate

```text
date: TIMESTAMP WITH TIME ZONE
game_size: BIGINT
match_id: VARCHAR
match_mode: VARCHAR
party_size: BIGINT
player_assists: BIGINT
player_dbno: BIGINT
player_dist_ride: DOUBLE
player_dist_walk: DOUBLE
player_dmg: BIGINT
player_kills: BIGINT
player_name: VARCHAR
player_survive_time: DOUBLE
team_id: BIGINT
team_placement: BIGINT
```

## 7. 현재 분석 가능 범위

확정한 날짜, 맵, 좌표와 완전 중복 규칙을 함께 적용한 결과:

| 맵 | 원인 | 분석 가능 행 |
|---|---|---:|
| 에란겔 | `Drown` | 97,272 |
| 에란겔 | `Falling` | 583,724 |
| 미라마 | `Drown` | 8,980 |
| 미라마 | `Falling` | 103,380 |
| 합계 | | **793,356** |

이 값은 프로파일링에서 측정한 현재 기준선이다. 정제 출력이 구현되면 동일
건수인지 대조해야 한다.
