"""Mapping utilities for the Department for Infrastructure spending dataset."""

import json
import csv
from pathlib import Path



from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256


DFI_ENCODING = "cp1252"
DFI_CURRENCY = "GBP"
DFI_DATE_FORMAT = "%d/%m/%Y"

DFI_SOURCE_COLUMNS = [
    "Department",
    "Organisation",
    "Check Date",
    "Expense type",
    "Supplier",
    "Invoice number",
    "Invoice Amount",
    "Postcode",
]

def map_dfi_file(
    file_path: Path,
    source_file_id: str,
    encoding: str = DFI_ENCODING,
) -> tuple[list[dict], list[dict]]:
    """Map a DfI CSV file into canonical SpendFlow transactions."""

    file_path = Path(file_path)

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Source file does not exist: {file_path}"
        )

    transactions = []
    validation_errors = []

    with file_path.open(
        "r",
        encoding=encoding,
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("Source CSV does not contain a header row")

        missing_columns = [
            column
            for column in DFI_SOURCE_COLUMNS
            if column not in reader.fieldnames
        ]

        if missing_columns:
            raise ValueError(
                "Source CSV is missing expected columns: "
                + ", ".join(missing_columns)
            )

        for source_row_number, row in enumerate(
            reader,
            start=2,
        ):
            transaction, row_errors = map_dfi_row(
                row=row,
                source_file_id=source_file_id,
                source_row_number=source_row_number,
            )

            transactions.append(transaction)
            validation_errors.extend(row_errors)

    return transactions, validation_errors

def normalise_name(value: str | None) -> str | None:
    """Return a conservative normalised version of an organisation name."""

    if value is None:
        return None

    normalised = " ".join(value.split())

    if not normalised:
        return None

    return normalised.casefold()


def parse_date(value: str | None) -> date | None:
    """Parse a DfI date, returning None for blank or invalid values."""

    if value is None or not value.strip():
        return None

    try:
        return datetime.strptime(
            value.strip(),
            DFI_DATE_FORMAT,
        ).date()
    except ValueError:
        return None


def parse_amount(value: str | None) -> Decimal | None:
    """Parse a DfI invoice amount without inventing invalid values."""

    if value is None or not value.strip():
        return None

    cleaned_value = (
        value.strip()
        .replace("£", "")
        .replace(",", "")
    )

    try:
        return Decimal(cleaned_value)
    except InvalidOperation:
        return None


def calculate_raw_record_hash(row: dict[str, str | None]) -> str:
    """Return a reproducible SHA-256 hash of the source values."""

    source_values = {
        column: row.get(column)
        for column in DFI_SOURCE_COLUMNS
    }

    serialised_row = json.dumps(
        source_values,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return sha256(
        serialised_row.encode(DFI_ENCODING)
    ).hexdigest()


def generate_transaction_id(
    source_file_id: str,
    source_row_number: int,
    raw_record_hash: str,
) -> str:
    """Generate a reproducible transaction identifier."""

    identity = (
        f"{source_file_id}:"
        f"{source_row_number}:"
        f"{raw_record_hash}"
    )

    return sha256(identity.encode("utf-8")).hexdigest()

def create_validation_error(
    source_row_number: int,
    field: str,
    error_type: str,
    raw_value: str | None,
) -> dict:
    """Create a structured validation error for a source value."""

    return {
        "source_row_number": source_row_number,
        "field": field,
        "error_type": error_type,
        "raw_value": raw_value,
    }


def map_dfi_row(
    row: dict[str, str | None],
    source_file_id: str,
    source_row_number: int,
) -> tuple[dict, list[dict]]:
    """Map one DfI source row into a canonical SpendFlow transaction."""

    validation_errors = []

    raw_record_hash = calculate_raw_record_hash(row)

    transaction_date_raw = row.get("Check Date")
    amount_raw = row.get("Invoice Amount")

    transaction_date = parse_date(transaction_date_raw)
    amount = parse_amount(amount_raw)

    if transaction_date_raw is None or not transaction_date_raw.strip():
        validation_errors.append(
            create_validation_error(
                source_row_number,
                "transaction_date",
                "missing_value",
                transaction_date_raw,
            )
        )
    elif transaction_date is None:
        validation_errors.append(
            create_validation_error(
                source_row_number,
                "transaction_date",
                "invalid_date",
                transaction_date_raw,
            )
        )

    if amount_raw is None or not amount_raw.strip():
        validation_errors.append(
            create_validation_error(
                source_row_number,
                "amount",
                "missing_value",
                amount_raw,
            )
        )
    elif amount is None:
        validation_errors.append(
            create_validation_error(
                source_row_number,
                "amount",
                "invalid_amount",
                amount_raw,
            )
        )

    supplier_name_raw = row.get("Supplier")
    buyer_name_raw = row.get("Organisation")

    transaction = {
        "transaction_id": generate_transaction_id(
            source_file_id,
            source_row_number,
            raw_record_hash,
        ),
        "source_file_id": source_file_id,
        "source_row_number": source_row_number,
        "source_record_id": None,
        "buyer_name_raw": buyer_name_raw,
        "buyer_name_normalised": normalise_name(
            buyer_name_raw
        ),
        "supplier_name_raw": supplier_name_raw,
        "supplier_name_normalised": normalise_name(
            supplier_name_raw
        ),
        "transaction_date": transaction_date,
        "amount": amount,
        "currency": DFI_CURRENCY,
        "description": None,
        "department": row.get("Department"),
        "category": row.get("Expense type"),
        "invoice_reference": row.get("Invoice number"),
        "payment_reference": None,
        "raw_record_hash": raw_record_hash,
        "loaded_at": datetime.now(timezone.utc),
    }

    return transaction, validation_errors