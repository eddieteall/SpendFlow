"""Raw source-file ingestion for SpendFlow."""

import csv
import json

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from shutil import copyfile
from uuid import uuid4


DEFAULT_RAW_DIRECTORY = Path("data/raw")
DEFAULT_REGISTRY_PATH = Path("data/processed/source_files.json")


def calculate_file_hash(file_path: Path) -> str:
    """Return the SHA-256 hash of a file's complete contents."""

    file_path = Path(file_path)

    if not file_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {file_path}")

    hasher = sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


def preserve_raw_file(
    input_path: Path,
    raw_directory: Path = DEFAULT_RAW_DIRECTORY,
) -> Path:
    """Copy a CSV into the raw-data directory without altering its contents."""

    input_path = Path(input_path)
    raw_directory = Path(raw_directory)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    if input_path.suffix.lower() != ".csv":
        raise ValueError(f"Input file must be a CSV: {input_path}")

    raw_directory.mkdir(parents=True, exist_ok=True)

    destination = raw_directory / input_path.name

    if destination.exists():
        input_hash = calculate_file_hash(input_path)
        destination_hash = calculate_file_hash(destination)

        if input_hash == destination_hash:
            return destination

        raise FileExistsError(
            f"A different raw file already exists at: {destination}"
        )

    copyfile(input_path, destination)

    return destination


def count_csv_rows(file_path: Path, encoding: str = "cp1252") -> int:
    """Count data rows in a CSV, excluding its header."""

    with Path(file_path).open(
        "r",
        encoding=encoding,
        newline="",
    ) as file:
        reader = csv.reader(file)
        row_count = sum(1 for _ in reader)

    return max(row_count - 1, 0)


def load_source_registry(
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> list[dict]:
    """Load registered source-file metadata."""

    registry_path = Path(registry_path)

    if not registry_path.exists():
        return []

    with registry_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_source_registry(
    records: list[dict],
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> None:
    """Write source-file metadata to the registry."""

    registry_path = Path(registry_path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    with registry_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2)


def register_source_file(
    input_path: Path,
    source_name: str,
    mapping_name: str,
    source_url: str | None = None,
    downloaded_at: str | None = None,
    encoding: str = "cp1252",
    raw_directory: Path = DEFAULT_RAW_DIRECTORY,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> dict:
    """Preserve and register a raw CSV source file."""

    input_path = Path(input_path)

    if not source_name.strip():
        raise ValueError("source_name must not be empty")

    if not mapping_name.strip():
        raise ValueError("mapping_name must not be empty")

    if not input_path.is_file():
        raise FileNotFoundError(
            f"Input file does not exist: {input_path}"
        )

    if input_path.suffix.lower() != ".csv":
        raise ValueError(f"Input file must be a CSV: {input_path}")

    file_hash = calculate_file_hash(input_path)

    records = load_source_registry(registry_path)

    for record in records:
        if record["file_hash"] == file_hash:
            return record

    preserved_path = preserve_raw_file(
        input_path,
        raw_directory,
    )

    record = {
        "source_file_id": str(uuid4()),
        "source_name": source_name,
        "source_url": source_url,
        "file_name": input_path.name,
        "file_path": preserved_path.as_posix(),
        "file_hash": file_hash,
        "downloaded_at": downloaded_at,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
        "row_count": count_csv_rows(
            preserved_path,
            encoding=encoding,
        ),
        "mapping_name": mapping_name,
    }

    records.append(record)
    save_source_registry(records, registry_path)

    return record