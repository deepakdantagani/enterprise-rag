"""DATA-1: import a source's archives from the release and write its manifest.json.

Gmail's data/gmail/manifest.json lists every zip of the release with its sha256 and
document count. This does the same for every other source: download the zips that are
missing, check each against the sha256 the release publishes, count the .txt files inside,
write manifest.json, and (optionally) unzip into raw/. Nothing is re-downloaded if the
zip is already there and its sha256 matches.

Run: uv run python -m tools.import_sources fireflies github google_drive hubspot jira
     uv run python -m tools.import_sources --no-raw linear slack

    >>> archives_of("hubspot", [{"name": "hubspot_slice_0002.zip"}, {"name": "jira_slice_0001.zip"},
    ...                          {"name": "hubspot_slice_0001.zip"}])
    [{'name': 'hubspot_slice_0001.zip'}, {'name': 'hubspot_slice_0002.zip'}]
"""
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

RELEASE_TAG = "v1.0.0"
RELEASE_API = f"https://api.github.com/repos/onyx-dot-app/EnterpriseRAG-Bench/releases/tags/{RELEASE_TAG}"
DATA_DIR = Path("data")


def archives_of(source: str, assets: list[dict]) -> list[dict]:
    """The release assets that are slices of this source, in slice order."""
    return sorted((a for a in assets if a["name"].startswith(f"{source}_slice_")), key=lambda a: a["name"])


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def count_documents(zip_path: Path) -> int:
    with zipfile.ZipFile(zip_path) as archive:
        return sum(name.endswith(".txt") for name in archive.namelist())


def fetch_archive(asset: dict, zip_path: Path) -> None:
    """Download one zip unless it is already there; fail if its sha256 is not the published one."""
    if not zip_path.exists():
        urllib.request.urlretrieve(asset["browser_download_url"], zip_path)
    if sha256_of_file(zip_path) != asset["digest"]:
        raise ValueError(f"{zip_path.name}: sha256 differs from the release")


def import_source(source: str, assets: list[dict], data_dir: Path = DATA_DIR, extract: bool = True) -> dict:
    """Fetch and verify every slice, write data/<source>/manifest.json, optionally unzip to raw/."""
    archives_dir = data_dir / source / "archives"
    archives_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for asset in archives_of(source, assets):
        zip_path = archives_dir / asset["name"]
        fetch_archive(asset, zip_path)
        if extract:
            zipfile.ZipFile(zip_path).extractall(data_dir / source / "raw")
        entries.append({"name": asset["name"], "url": asset["browser_download_url"],
                        "sha256": asset["digest"], "documents": count_documents(zip_path)})
    manifest = {"release": RELEASE_TAG, "archives": entries}
    (data_dir / source / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    extract = "--no-raw" not in sys.argv
    sources = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    with urllib.request.urlopen(RELEASE_API) as response:
        release_assets = json.load(response)["assets"]
    for source in sources:
        manifest = import_source(source, release_assets, extract=extract)
        print(source, len(manifest["archives"]), sum(a["documents"] for a in manifest["archives"]))
