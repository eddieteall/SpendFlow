from hashlib import sha256

import pytest

from spendflow.ingestion import (
    calculate_file_hash,
    preserve_raw_file,
    register_source_file,
)


def create_test_csv(path):
    content = (
        b"Supplier,Invoice Amount\n"
        b"Example Ltd,100.00\n"
        b"Another Ltd,250.00\n"
    )

    path.write_bytes(content)

    return content


def test_calculate_file_hash_is_reproducible(tmp_path):
    source_file = tmp_path / "sample.csv"
    expected_bytes = create_test_csv(source_file)

    expected_hash = sha256(expected_bytes).hexdigest()

    first_hash = calculate_file_hash(source_file)
    second_hash = calculate_file_hash(source_file)

    assert first_hash == expected_hash
    assert second_hash == expected_hash


def test_preserve_raw_file_keeps_contents_unchanged(tmp_path):
    source_file = tmp_path / "sample.csv"
    expected_bytes = create_test_csv(source_file)

    raw_directory = tmp_path / "raw"

    stored_file = preserve_raw_file(
        source_file,
        raw_directory=raw_directory,
    )

    assert stored_file.exists()
    assert stored_file.read_bytes() == expected_bytes


def test_register_source_file_records_metadata(tmp_path):
    source_file = tmp_path / "sample.csv"
    create_test_csv(source_file)

    raw_directory = tmp_path / "raw"
    registry_path = tmp_path / "processed" / "source_files.json"

    record = register_source_file(
        source_file,
        source_name="Test Source",
        mapping_name="test_mapping_v1",
        source_url="https://example.com/sample.csv",
        raw_directory=raw_directory,
        registry_path=registry_path,
        encoding="utf-8",
    )

    assert record["source_file_id"]
    assert record["source_name"] == "Test Source"
    assert record["source_url"] == "https://example.com/sample.csv"
    assert record["file_name"] == "sample.csv"
    assert record["file_hash"] == calculate_file_hash(source_file)
    assert record["row_count"] == 2
    assert record["mapping_name"] == "test_mapping_v1"
    assert record["loaded_at"]
    assert registry_path.exists()


def test_registering_same_file_twice_does_not_duplicate(tmp_path):
    source_file = tmp_path / "sample.csv"
    create_test_csv(source_file)

    raw_directory = tmp_path / "raw"
    registry_path = tmp_path / "processed" / "source_files.json"

    first_record = register_source_file(
        source_file,
        source_name="Test Source",
        mapping_name="test_mapping_v1",
        raw_directory=raw_directory,
        registry_path=registry_path,
        encoding="utf-8",
    )

    second_record = register_source_file(
        source_file,
        source_name="Test Source",
        mapping_name="test_mapping_v1",
        raw_directory=raw_directory,
        registry_path=registry_path,
        encoding="utf-8",
    )

    assert first_record["source_file_id"] == second_record["source_file_id"]

    import json

    with registry_path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    assert len(records) == 1


def test_missing_input_file_raises_clear_error(tmp_path):
    missing_file = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError, match="does not exist"):
        register_source_file(
            missing_file,
            source_name="Test Source",
            mapping_name="test_mapping_v1",
        )


def test_non_csv_input_is_rejected(tmp_path):
    source_file = tmp_path / "sample.txt"
    source_file.write_text("not a csv", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a CSV"):
        register_source_file(
            source_file,
            source_name="Test Source",
            mapping_name="test_mapping_v1",
        )