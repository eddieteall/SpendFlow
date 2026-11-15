"""Register, map, validate and load one dataset snapshot."""

import argparse
import csv
import json
from pathlib import Path

import duckdb

from spendflow.analysis.rules import Findings, VERSION, key
from spendflow.ingestion import calculate_file_hash, register_source_file
from spendflow.mapping.dfi_transactions import map_dfi_file
from spendflow.schema import SCHEMA

PUBLIC = Path("data/raw/dfi-departmental-spend-over-25000-for-july-2026-csv-format.csv")
SYNTHETIC = Path("data/synthetic-spend.csv")
DATASETS = {
    "public": (PUBLIC, "OpenDataNI — DfI July 2026", "dfi_spend_v1",
        "https://www.data.gov.uk/dataset/5ed9b600-46d6-48ba-a023-2559d41523e3/"
        "department-for-infrastructure-dfi-departmental-spend-over-f25-000-2026-27"),
    "synthetic": (SYNTHETIC, "Synthetic demo — invented payments", "synthetic_spend_v1", None),
}


def validate_decisions(decisions):
    if not isinstance(decisions, dict):
        raise ValueError("Alias reviews must be a JSON object keyed by exact raw supplier name")
    for raw, choice in decisions.items():
        if (not isinstance(raw, str) or not isinstance(choice, dict)
            or choice.keys() - {"status", "canonical", "notes"}
            or choice.get("status") not in ("accepted", "rejected", "proposed")
            or any(not isinstance(choice[k], str) for k in ("canonical", "notes") if k in choice)
            or ("canonical" in choice) != (choice["status"] == "accepted")):
            raise ValueError(f"Invalid alias review for {raw!r}")


def load_dataset(dataset: str, database: Path, *, input_path: Path | None = None,
                 decisions: dict | None = None) -> dict:
    database = Path(database)
    decisions = {} if decisions is None else decisions
    validate_decisions(decisions)
    bundled, name, mapping, url = DATASETS[dataset]
    raw = database.parent / "sources"
    input_path = input_path or bundled
    file_hash = calculate_file_hash(input_path)
    archive = raw / f"{dataset}-{file_hash[:24]}"
    source = register_source_file(input_path, name, mapping,
        source_url=url if input_path == bundled else None,
        raw_directory=archive, registry_path=archive / "registry.json", storage_name="source.csv")
    snapshot = key(dataset, source["source_file_id"], decisions, VERSION)
    mapping_error = None
    try:
        records, errors = map_dfi_file(source["file_path"], source["source_file_id"],
                                       synthetic=dataset == "synthetic")
    except (ValueError, csv.Error) as exc:
        mapping_error = str(exc)
        records, errors = [], [{"source_row_number": None, "field": "source_csv",
            "error_type": "source_mapping_failed", "raw_value": mapping_error,
            "message": mapping_error}]
    if mapping_error is None:
        source["row_count"] = len(records)
    with duckdb.connect(str(database), config={"threads": "2"}) as db:
        db.execute("BEGIN")
        try:
            db.execute(SCHEMA)
            previous = db.execute("SELECT snapshot_key FROM source_files").fetchone()
            if previous and previous[0] != snapshot:
                raise ValueError("Database already contains a different snapshot. Choose a new --db for a different input or alias configuration.")
            if previous is None:
                metadata = dict(source, snapshot_key=snapshot)
                # Column names here come from the internal registry contract.
                fields = ("source_file_id", "source_name", "source_url", "file_name", "file_path",
                          "file_hash", "downloaded_at", "loaded_at", "row_count", "mapping_name", "snapshot_key")
                db.execute("INSERT INTO source_files (" + ", ".join(fields) + ") VALUES (" +
                           ", ".join("?" for _ in fields) + ")", [metadata[k] for k in fields])
                if records:
                    columns = tuple(records[0])
                    db.executemany("INSERT INTO transactions (" + ", ".join(columns) +
                        ") VALUES (" + ", ".join("?" for _ in columns) + ")",
                        [[r[k] for k in columns] for r in records])
                engine = Findings(db, source["source_file_id"])
                engine.validation(errors, records)
                if mapping_error is None:
                    engine.detect(records, decisions)
            result = {
                "dataset": dataset, "source_file_id": source["source_file_id"],
                "file_sha256": source["file_hash"], "transactions": len(records),
                "findings": db.execute("SELECT count(*) FROM findings").fetchone()[0],
                "mapping_error": mapping_error,
            }
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=DATASETS)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--alias-reviews", type=Path)
    args = parser.parse_args()
    try:
        decisions = json.loads(args.alias_reviews.read_text(encoding="utf-8")) if args.alias_reviews else None
        result = load_dataset(args.dataset, args.db, input_path=args.input, decisions=decisions)
    except (OSError, ValueError, duckdb.Error) as exc:
        parser.exit(1, f"SpendFlow: {exc}\n")
    print(json.dumps(result, indent=2))
    if result["mapping_error"] is not None:
        parser.exit(1, "Source mapping failed; source-level evidence is stored in DuckDB.\n")


if __name__ == "__main__":
    main()
