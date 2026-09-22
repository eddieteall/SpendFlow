"""Raw-data ingestion functionality for SpendFlow."""

from spendflow.ingestion.source_files import (
    calculate_file_hash,
    count_csv_rows,
    preserve_raw_file,
    register_source_file,
)

__all__ = [
    "calculate_file_hash",
    "count_csv_rows",
    "preserve_raw_file",
    "register_source_file",
]