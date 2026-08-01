import argparse
import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_URL = "https://api.pubg.com"
DEFAULT_SAMPLE_DIR = Path("data/raw/pubg_api/samples")
DEFAULT_OUTPUT_DIR = Path("data/raw/pubg_api/pilot")
KILL_EVENT_TYPES = {"LogPlayerKill", "LogPlayerKillV2"}
DAMAGE_INFO_FIELDS = (
    "killerDamageInfo",
    "finishDamageInfo",
    "dBNODamageInfo",
)


def parse_args() -> argparse.Namespace:
    """명령행 인자를 읽고 파일럿 범위를 검증한다."""

    parser = argparse.ArgumentParser(
        description="PUBG 경기·텔레메트리 스키마를 소규모로 프로파일링합니다.",
    )
    parser.add_argument(
        "--platform",
        choices=("steam", "kakao", "console"),
        default="steam",
        help="경기 상세를 조회할 플랫폼 shard입니다.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="조회할 경기 수입니다. 기본값은 10입니다.",
    )
    parser.add_argument(
        "--sample-file",
        type=Path,
        help="사용할 samples API 원본 JSON입니다. 생략하면 최신 파일을 찾습니다.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="집계 프로파일을 저장할 디렉터리입니다.",
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit은 1 이상이어야 합니다.")

    return args


def resolve_sample_file(
    platform: str,
    sample_file: Path | None,
) -> Path:
    """명시된 파일 또는 가장 최근에 저장된 최신 표본 파일을 선택한다."""

    if sample_file is not None:
        if not sample_file.is_file():
            raise FileNotFoundError(f"표본 파일을 찾지 못했습니다: {sample_file}")
        return sample_file

    platform_dir = DEFAULT_SAMPLE_DIR / platform
    candidates = list(platform_dir.glob("latest_*.json"))

    if not candidates:
        raise FileNotFoundError(
            "최신 표본 파일을 찾지 못했습니다. "
            "collect_pubg_api_samples.py를 먼저 실행하세요."
        )

    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_json(path: Path) -> dict[str, Any]:
    """로컬 JSON 객체를 불러온다."""

    try:
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"JSON 파일을 읽지 못했습니다: {path}") from error

    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON 최상위 값이 객체가 아닙니다: {path}")

    return payload


def fetch_json(url: str) -> tuple[Any, int, int]:
    """키가 필요 없는 경기·텔레메트리 JSON과 전송 크기를 반환한다."""

    request = Request(
        url,
        headers={
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=120) as response:
            wire_data = response.read()
            content_encoding = response.headers.get(
                "Content-Encoding",
                "",
            ).lower()
    except HTTPError as error:
        detail = error.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(
            f"PUBG API 요청 실패: HTTP {error.code}, 응답={detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"PUBG API 연결 실패: {error.reason}") from error

    if content_encoding == "gzip" or wire_data[:2] == b"\x1f\x8b":
        decoded_data = gzip.decompress(wire_data)
    else:
        decoded_data = wire_data

    try:
        payload = json.loads(decoded_data)
    except json.JSONDecodeError as error:
        raise RuntimeError("PUBG API 응답이 올바른 JSON이 아닙니다.") from error

    return payload, len(wire_data), len(decoded_data)


def extract_match_ids(
    sample_payload: dict[str, Any],
    limit: int,
) -> list[str]:
    """표본 응답에서 중복 없는 경기 ID를 요청 수만큼 선택한다."""

    try:
        matches = sample_payload["data"]["relationships"]["matches"]["data"]
    except (KeyError, TypeError) as error:
        raise RuntimeError("표본 응답에서 경기 목록을 찾지 못했습니다.") from error

    if not isinstance(matches, list):
        raise RuntimeError("표본 응답의 경기 목록이 배열이 아닙니다.")

    match_ids: list[str] = []
    seen: set[str] = set()

    for match in matches:
        if not isinstance(match, dict):
            continue

        match_id = match.get("id")

        if not isinstance(match_id, str) or not match_id or match_id in seen:
            continue

        seen.add(match_id)
        match_ids.append(match_id)

        if len(match_ids) == limit:
            break

    if len(match_ids) < limit:
        raise RuntimeError(
            f"요청한 {limit}개보다 적은 {len(match_ids)}개 경기 ID만 찾았습니다."
        )

    return match_ids


def find_telemetry_url(match_payload: dict[str, Any]) -> str:
    """경기 상세 응답에서 텔레메트리 asset URL을 찾는다."""

    included = match_payload.get("included", [])

    if not isinstance(included, list):
        raise RuntimeError("경기 상세 응답의 included가 배열이 아닙니다.")

    for item in included:
        if not isinstance(item, dict) or item.get("type") != "asset":
            continue

        attributes = item.get("attributes")

        if not isinstance(attributes, dict):
            continue

        if attributes.get("name") != "telemetry":
            continue

        telemetry_url = attributes.get("URL")

        if isinstance(telemetry_url, str) and telemetry_url:
            return telemetry_url

    raise RuntimeError("경기 상세 응답에서 텔레메트리 URL을 찾지 못했습니다.")


def save_json_atomic(payload: dict[str, Any], path: Path) -> None:
    """집계 결과 JSON을 임시 파일에 쓴 뒤 원자적으로 교체한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")

        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def profile_kill_event(
    event: dict[str, Any],
    counters: dict[str, Counter[str]],
    key_sets: dict[str, set[str]],
) -> tuple[bool, bool]:
    """사망 이벤트의 좌표와 피해정보 필드 출현을 집계한다."""

    key_sets["kill_event"].update(event)
    has_victim_location = False
    is_zero_zero = False
    victim = event.get("victim")

    if isinstance(victim, dict):
        location = victim.get("location")

        if isinstance(location, dict):
            x = location.get("x")
            y = location.get("y")

            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                has_victim_location = True
                is_zero_zero = x == 0 and y == 0

    for field in DAMAGE_INFO_FIELDS:
        damage_info = event.get(field)

        if not isinstance(damage_info, dict):
            continue

        key_sets["damage_info"].update(damage_info)

        for source_key, counter_key in (
            ("damageTypeCategory", "damage_type"),
            ("damageCauserName", "damage_causer"),
            ("damageReason", "damage_reason"),
        ):
            value = damage_info.get(source_key)

            if value:
                counters[counter_key][str(value)] += 1

    return has_victim_location, is_zero_zero


def profile_match(
    platform: str,
    match_id: str,
    counters: dict[str, Counter[str]],
    key_sets: dict[str, set[str]],
) -> dict[str, Any]:
    """한 경기의 상세와 텔레메트리를 조회하고 집계값을 반환한다."""

    match_url = f"{API_BASE_URL}/shards/{platform}/matches/{match_id}"
    match_payload, match_wire_bytes, match_decoded_bytes = fetch_json(match_url)

    if not isinstance(match_payload, dict):
        raise RuntimeError("경기 상세 응답의 최상위 값이 객체가 아닙니다.")

    data = match_payload.get("data")

    if not isinstance(data, dict):
        raise RuntimeError("경기 상세 응답의 data가 객체가 아닙니다.")

    attributes = data.get("attributes")

    if not isinstance(attributes, dict):
        raise RuntimeError("경기 상세 응답의 attributes가 객체가 아닙니다.")

    map_name = str(attributes.get("mapName") or "UNKNOWN")
    game_mode = str(attributes.get("gameMode") or "UNKNOWN")
    created_at = attributes.get("createdAt")
    telemetry_url = find_telemetry_url(match_payload)
    telemetry, telemetry_wire_bytes, telemetry_decoded_bytes = fetch_json(
        telemetry_url
    )

    if not isinstance(telemetry, list):
        raise RuntimeError("텔레메트리 최상위 값이 배열이 아닙니다.")

    kill_event_count = 0
    victim_location_count = 0
    zero_zero_count = 0

    for event in telemetry:
        if not isinstance(event, dict):
            continue

        event_type = str(event.get("_T") or "UNKNOWN")
        counters["event_type"][event_type] += 1

        if event_type not in KILL_EVENT_TYPES:
            continue

        kill_event_count += 1
        has_location, is_zero_zero = profile_kill_event(
            event,
            counters,
            key_sets,
        )
        victim_location_count += int(has_location)
        zero_zero_count += int(is_zero_zero)

    counters["map"][map_name] += 1
    counters["game_mode"][game_mode] += 1

    return {
        "match_id": match_id,
        "map_name": map_name,
        "game_mode": game_mode,
        "created_at": created_at,
        "event_count": len(telemetry),
        "kill_event_count": kill_event_count,
        "victim_location_count": victim_location_count,
        "zero_zero_count": zero_zero_count,
        "wire_bytes": match_wire_bytes + telemetry_wire_bytes,
        "decoded_bytes": match_decoded_bytes + telemetry_decoded_bytes,
    }


def run_pilot(args: argparse.Namespace) -> None:
    """경기 상세·텔레메트리 파일럿을 실행하고 비식별 집계를 저장한다."""

    started_at = perf_counter()
    sample_file = resolve_sample_file(args.platform, args.sample_file)
    sample_payload = load_json(sample_file)
    match_ids = extract_match_ids(sample_payload, args.limit)
    counters = {
        "map": Counter[str](),
        "game_mode": Counter[str](),
        "event_type": Counter[str](),
        "damage_type": Counter[str](),
        "damage_causer": Counter[str](),
        "damage_reason": Counter[str](),
    }
    key_sets = {
        "kill_event": set[str](),
        "damage_info": set[str](),
    }
    match_results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    print("\n[PUBG API 경기·텔레메트리 파일럿]")
    print(f"표본 파일: {sample_file}")
    print(f"요청 경기 수: {args.limit}")

    for index, match_id in enumerate(match_ids, start=1):
        try:
            result = profile_match(
                args.platform,
                match_id,
                counters,
                key_sets,
            )
            match_results.append(result)
            print(
                f"[{index}/{args.limit}] map={result['map_name']}, "
                f"events={result['event_count']:,}, "
                f"kill_events={result['kill_event_count']:,}, "
                f"wire={result['wire_bytes'] / 1024 / 1024:.2f} MB"
            )
        except Exception as error:
            failures.append(
                {
                    "match_id": match_id,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )
            print(
                f"[{index}/{args.limit}] 실패: "
                f"{type(error).__name__}: {error}"
            )

    if not match_results:
        raise RuntimeError("성공한 파일럿 경기가 없습니다.")

    created_at_values = [
        str(result["created_at"])
        for result in match_results
        if result["created_at"]
    ]
    total_wire_bytes = sum(int(result["wire_bytes"]) for result in match_results)
    total_decoded_bytes = sum(
        int(result["decoded_bytes"])
        for result in match_results
    )
    elapsed_seconds = perf_counter() - started_at
    summary = {
        "profiled_at_utc": datetime.now(UTC).isoformat(),
        "platform": args.platform,
        "sample_file": sample_file.as_posix(),
        "requested_match_count": args.limit,
        "successful_match_count": len(match_results),
        "failed_match_count": len(failures),
        "map_counts": dict(counters["map"]),
        "game_mode_counts": dict(counters["game_mode"]),
        "created_at_min": min(created_at_values) if created_at_values else None,
        "created_at_max": max(created_at_values) if created_at_values else None,
        "event_count": sum(counters["event_type"].values()),
        "kill_event_count": sum(
            int(result["kill_event_count"])
            for result in match_results
        ),
        "victim_location_count": sum(
            int(result["victim_location_count"])
            for result in match_results
        ),
        "zero_zero_count": sum(
            int(result["zero_zero_count"])
            for result in match_results
        ),
        "wire_bytes": total_wire_bytes,
        "decoded_bytes": total_decoded_bytes,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "kill_event_keys": sorted(key_sets["kill_event"]),
        "damage_info_keys": sorted(key_sets["damage_info"]),
        "event_type_counts": counters["event_type"].most_common(),
        "damage_type_occurrences": counters["damage_type"].most_common(),
        "damage_causer_occurrences": counters["damage_causer"].most_common(),
        "damage_reason_occurrences": counters["damage_reason"].most_common(),
        "damage_count_notice": (
            "피해정보 3개 객체의 필드 출현 횟수이며 최종 사망 건수가 아닙니다."
        ),
        "failures": failures,
    }
    output_path = args.output_dir / args.platform / "profile_summary.json"
    save_json_atomic(summary, output_path)

    print("\n[파일럿 결과]")
    print(f"성공 경기: {len(match_results):,}")
    print(f"실패 경기: {len(failures):,}")
    print(f"전체 이벤트: {summary['event_count']:,}")
    print(f"사망 이벤트: {summary['kill_event_count']:,}")
    print(f"피해자 좌표 확인: {summary['victim_location_count']:,}")
    print(f"전송 크기: {total_wire_bytes / 1024 / 1024:.2f} MB")
    print(f"압축 해제 크기: {total_decoded_bytes / 1024 / 1024:.2f} MB")
    print(f"실행 시간: {elapsed_seconds:.2f}초")
    print(f"집계 저장 위치: {output_path}")


def main() -> None:
    args = parse_args()
    run_pilot(args)


if __name__ == "__main__":
    main()
