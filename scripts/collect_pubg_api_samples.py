import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from getpass import getpass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE_URL = "https://api.pubg.com"
DEFAULT_OUTPUT_DIR = Path("data/raw/pubg_api/samples")
MIN_REQUEST_INTERVAL_SECONDS = 6.2


@dataclass(frozen=True)
class SampleWindow:
    """PUBG samples API에서 조회할 24시간 표본 구간을 나타낸다."""

    label: str
    start_time: str | None


def parse_args() -> argparse.Namespace:
    """명령행 인자를 읽고 수집 범위를 검증한다."""

    parser = argparse.ArgumentParser(
        description="PUBG 공식 API의 최근 경기 표본 목록을 안전하게 저장합니다.",
    )
    parser.add_argument(
        "--platform",
        choices=("steam", "kakao", "console"),
        default="steam",
        help="조회할 PUBG 플랫폼 shard입니다. 기본값은 steam입니다.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="수집할 일별 표본 구간 수입니다. 1부터 14까지 지정합니다.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="원본 표본 응답을 저장할 디렉터리입니다.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="같은 구간의 로컬 응답이 있어도 API에서 다시 조회합니다.",
    )

    args = parser.parse_args()

    if not 1 <= args.days <= 14:
        parser.error("--days는 1부터 14 사이여야 합니다.")

    return args


def get_api_key() -> str:
    """환경 변수 또는 숨김 입력으로 API 키를 받는다."""

    api_key = os.environ.get("PUBG_API_KEY", "").strip()

    if not api_key:
        api_key = getpass("PUBG API Key (입력값은 표시되지 않음): ").strip()

    if not api_key:
        raise RuntimeError("PUBG API 키가 입력되지 않았습니다.")

    return api_key


def build_sample_windows(days: int) -> list[SampleWindow]:
    """최신 표본과 이전 UTC 일자별 표본 구간을 만든다."""

    now = datetime.now(UTC)
    windows = [
        SampleWindow(
            label=f"latest_{now:%Y-%m-%d}",
            start_time=None,
        )
    ]

    for day_offset in range(1, days):
        window_end = (now - timedelta(days=day_offset)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        windows.append(
            SampleWindow(
                label=f"ending_{window_end:%Y-%m-%d}",
                start_time=window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )

    return windows


def build_samples_url(platform: str, window: SampleWindow) -> str:
    """플랫폼과 조회 구간으로 samples API URL을 만든다."""

    url = f"{API_BASE_URL}/shards/{platform}/samples"

    if window.start_time is None:
        return url

    query = urlencode(
        {"filter[createdAt-start]": window.start_time},
    )
    return f"{url}?{query}"


def fetch_json(url: str, api_key: str) -> dict[str, Any]:
    """PUBG API에서 JSON 응답을 받아 객체 형태인지 검증한다."""

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.api+json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=60) as response:
            raw_response = response.read()
    except HTTPError as error:
        detail = error.read(500).decode("utf-8", errors="replace")

        if error.code == 401:
            raise RuntimeError(
                "PUBG API 인증에 실패했습니다. 발급한 키를 다시 확인하세요."
            ) from error

        raise RuntimeError(
            f"PUBG API 요청 실패: HTTP {error.code}, 응답={detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"PUBG API 연결 실패: {error.reason}") from error

    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise RuntimeError("PUBG API 응답이 올바른 JSON이 아닙니다.") from error

    if not isinstance(payload, dict):
        raise RuntimeError("PUBG API 최상위 응답이 객체가 아닙니다.")

    return payload


def load_json(path: Path) -> dict[str, Any]:
    """이미 저장된 JSON 응답을 불러온다."""

    try:
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"기존 표본 파일을 읽지 못했습니다: {path}") from error

    if not isinstance(payload, dict):
        raise RuntimeError(f"기존 표본 파일의 최상위 값이 객체가 아닙니다: {path}")

    return payload


def save_json_atomic(payload: dict[str, Any], path: Path) -> None:
    """JSON을 임시 파일에 쓴 뒤 원자적으로 교체한다."""

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


def extract_match_ids(payload: dict[str, Any]) -> list[str]:
    """samples API 응답에서 유효한 경기 ID만 추출한다."""

    try:
        matches = payload["data"]["relationships"]["matches"]["data"]
    except (KeyError, TypeError) as error:
        raise RuntimeError("samples API 응답에서 경기 목록을 찾지 못했습니다.") from error

    if not isinstance(matches, list):
        raise RuntimeError("samples API의 경기 목록이 배열이 아닙니다.")

    match_ids: list[str] = []

    for match in matches:
        if not isinstance(match, dict):
            continue

        match_id = match.get("id")

        if isinstance(match_id, str) and match_id:
            match_ids.append(match_id)

    return match_ids


def wait_for_rate_limit(last_request_at: float | None) -> None:
    """기본 10 RPM 제한을 넘지 않도록 API 요청 사이를 조절한다."""

    if last_request_at is None:
        return

    elapsed = time.monotonic() - last_request_at
    remaining = MIN_REQUEST_INTERVAL_SECONDS - elapsed

    if remaining > 0:
        time.sleep(remaining)


def collect_samples(args: argparse.Namespace) -> None:
    """지정 범위의 표본 응답을 저장하고 경기 ID 수를 요약한다."""

    started_at = time.perf_counter()
    collected_at = datetime.now(UTC)
    output_dir = args.output_dir / args.platform
    windows = build_sample_windows(args.days)
    api_key: str | None = None
    last_request_at: float | None = None
    unique_match_ids: set[str] = set()
    window_summaries: list[dict[str, Any]] = []

    print("\n[PUBG API 경기 표본 목록 수집]")
    print(f"플랫폼: {args.platform}")
    print(f"표본 구간 수: {args.days}일")

    for index, window in enumerate(windows, start=1):
        output_path = output_dir / f"{window.label}.json"

        if output_path.exists() and not args.refresh:
            payload = load_json(output_path)
            source = "local_cache"
        else:
            if api_key is None:
                api_key = get_api_key()

            wait_for_rate_limit(last_request_at)
            payload = fetch_json(
                build_samples_url(args.platform, window),
                api_key,
            )
            last_request_at = time.monotonic()
            save_json_atomic(payload, output_path)
            source = "pubg_api"

        match_ids = extract_match_ids(payload)
        unique_match_ids.update(match_ids)
        window_summaries.append(
            {
                "window_order": index,
                "window_label": window.label,
                "requested_start_time": window.start_time,
                "match_reference_count": len(match_ids),
                "source": source,
                "output_path": output_path.as_posix(),
            }
        )

        print(
            f"[{index}/{len(windows)}] {window.label}: "
            f"{len(match_ids):,}개 경기 ID ({source})"
        )

    total_references = sum(
        int(summary["match_reference_count"])
        for summary in window_summaries
    )
    elapsed_seconds = time.perf_counter() - started_at
    summary = {
        "collected_at_utc": collected_at.isoformat(),
        "platform": args.platform,
        "requested_days": args.days,
        "window_count": len(windows),
        "match_reference_count": total_references,
        "unique_match_id_count": len(unique_match_ids),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "scope_notice": (
            "PUBG samples API의 무작위 경기 표본이며 전체 경기 데이터가 아닙니다."
        ),
        "windows": window_summaries,
    }
    summary_path = output_dir / "collection_summary.json"
    save_json_atomic(summary, summary_path)

    print("\n[수집 결과]")
    print(f"경기 ID 참조 수: {total_references:,}")
    print(f"고유 경기 ID 수: {len(unique_match_ids):,}")
    print(f"요약 저장 위치: {summary_path}")
    print(f"실행 시간: {elapsed_seconds:.2f}초")
    print("텔레메트리는 아직 다운로드하지 않았습니다.")


def main() -> None:
    args = parse_args()
    collect_samples(args)


if __name__ == "__main__":
    main()
