"""Download period-matched PUBG map images for local spatial reports."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAP_DIRECTORY = PROJECT_ROOT / "data" / "reference" / "maps"
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class MapAsset:
    """A map asset pinned to an immutable source revision."""

    map_name: str
    observed_date: str
    file_name: str
    source_url: str
    expected_sha256: str


MAP_ASSETS = (
    MapAsset(
        map_name="Erangel",
        observed_date="2017-11-03",
        file_name="Erangel_2017-11-03.jpg",
        source_url=(
            "https://raw.githubusercontent.com/moonspell99c/WebMap/"
            "ff1802a5c4139f29535771eb3b37258e6eff1e16/static/map.jpg"
        ),
        expected_sha256=(
            "47a8c688c4e564f7b69d9cc0283e8bd89cab6794e25e40be26e343984cbda3db"
        ),
    ),
    MapAsset(
        map_name="Miramar",
        observed_date="2017-12-23",
        file_name="Miramar_2017-12-23.jpg",
        source_url=(
            "https://raw.githubusercontent.com/moonspell99c/WebMap/"
            "717c33f43e068ff0e856ef7111ab109cfd58c538/static/mapMiramar.jpg"
        ),
        expected_sha256=(
            "1a14b6e00b57bce7c6b22e47baecec830cab1ce23e5d56dffb0f42ea9b0b93d0"
        ),
    ),
)


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a local file."""

    digest = sha256()
    with path.open("rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(asset: MapAsset) -> Path:
    """Download and verify one map without replacing a valid file prematurely."""

    destination = MAP_DIRECTORY / asset.file_name
    if destination.exists() and file_sha256(destination) == asset.expected_sha256:
        print(f"[skip] {asset.map_name}: verified {destination}")
        return destination

    temporary_path = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary_path.unlink(missing_ok=True)
    request = Request(
        asset.source_url,
        headers={"User-Agent": "pubg-analytics-ops-map-downloader/1.0"},
    )

    try:
        with urlopen(request, timeout=120) as response, temporary_path.open("wb") as file:
            while chunk := response.read(CHUNK_SIZE):
                file.write(chunk)

        with temporary_path.open("rb") as file:
            if file.read(3) != b"\xff\xd8\xff":
                raise ValueError(f"Downloaded file is not a JPEG: {asset.source_url}")

        actual_sha256 = file_sha256(temporary_path)
        if actual_sha256 != asset.expected_sha256:
            raise ValueError(
                f"SHA-256 mismatch for {asset.map_name}: "
                f"expected {asset.expected_sha256}, got {actual_sha256}"
            )

        temporary_path.replace(destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    print(
        f"[downloaded] {asset.map_name} ({asset.observed_date}): {destination}"
    )
    return destination


def main() -> None:
    """Download every pinned historical map asset."""

    MAP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for asset in MAP_ASSETS:
        download_asset(asset)

    print("Map images are local reference files and remain excluded from Git.")


if __name__ == "__main__":
    main()
