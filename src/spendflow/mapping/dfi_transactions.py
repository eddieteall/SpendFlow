"""Mapping utilities for the Department for Infrastructure spending dataset."""

import csv
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path

import pandas as pd


DFI_ENCODING = "cp1252"
DFI_CURRENCY = "GBP"
DFI_DATE_FORMAT = "%d/%m/%Y"
SYNTHETIC_COLUMNS = ["Currency", "Description", "Payment reference"]
SUPPORTED_CURRENCIES = ("GBP", "EUR", "USD")
AMOUNT_PATTERN = re.compile(r"(?:[+-]?£|£[+-]?|[+-]?)(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?")

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
    *, synthetic: bool = False,
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
        reader = csv.DictReader(file, strict=True)

        if reader.fieldnames is None:
            raise ValueError("Source CSV does not contain a header row")

        missing_columns = [
            column
            for column in DFI_SOURCE_COLUMNS + (SYNTHETIC_COLUMNS if synthetic else [])
            if column not in reader.fieldnames
        ]

        if missing_columns:
            raise ValueError(
                "Source CSV is missing expected columns: "
                + ", ".join(missing_columns)
            )

        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("Source CSV contains duplicate column names")

        # DictReader retains the distinction between an empty field and a short
        # record, including existing record numbering and raw-row hashes.
        records, extra_fields = [], {}
        for number, row in enumerate(reader, start=2):
            if None in row:
                extra_fields[number] = row.pop(None)
            records.append(row)

    frame = pd.DataFrame(records, columns=reader.fieldnames, dtype=object)
    # Vectorised standardisation retains raw cells for validation and hashing.
    for column in ("Supplier", "Organisation"):
        frame[f"_normalised_{column}"] = (
            frame[column].str.split().str.join(" ").str.casefold().replace("", None)
            if len(frame) and frame[column].notna().any() else None
        )
    for number, row in enumerate(frame.to_dict("records"), start=2):
        if number in extra_fields:
            row[None] = extra_fields[number]
        transaction, errors = map_dfi_row(row, source_file_id, number)
        for source, target in (("Supplier", "supplier"), ("Organisation", "buyer")):
            value = row[f"_normalised_{source}"]
            transaction[f"{target}_name_normalised"] = value if isinstance(value, str) else None
        if synthetic:
            apply_synthetic_fields(row, transaction, errors)
        if number in extra_fields or any(row.get(key) is None for key in reader.fieldnames):
            overflow = json.dumps(extra_fields[number]) if number in extra_fields else None
            errors.append(create_validation_error(number, "record", "wrong_column_count", overflow))
        transactions.append(transaction)
        validation_errors.extend(errors)

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

    value = value.strip()
    if not AMOUNT_PATTERN.fullmatch(value):
        return None
    try:
        amount = Decimal(value.replace("£", "").replace(",", ""))
        return amount if abs(amount) < Decimal("10000000000000000") else None
    except InvalidOperation:
        return None


def calculate_raw_record_hash(row: dict) -> str:
    """Return a reproducible SHA-256 hash of the source values."""

    source_values = {
        column: row.get(column)
        for column in DFI_SOURCE_COLUMNS + [key for key in SYNTHETIC_COLUMNS if key in row]
    }

    for column, value in row.items():
        if column not in source_values and column not in ("_normalised_Supplier", "_normalised_Organisation"):
            source_values[column] = value

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
    row: dict,
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

    if normalise_name(supplier_name_raw) is None:
        validation_errors.append(create_validation_error(
            source_row_number, "supplier_name_raw", "missing_value", supplier_name_raw,
        ))

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

def apply_synthetic_fields(row: dict, transaction: dict, errors: list[dict]) -> None:
    """Label the richer synthetic source explicitly; DfI supplies none of these fields."""
    raw_currency = row.get("Currency")
    currency = (raw_currency or "").strip().upper() or None
    transaction.update(
        currency=currency,
        description=row.get("Description") or None,
        payment_reference=row.get("Payment reference") or None,
    )
    if currency not in SUPPORTED_CURRENCIES:
        errors.append(create_validation_error(
            transaction["source_row_number"], "currency",
            "unsupported_currency" if currency else "missing_value", raw_currency,
        ))
