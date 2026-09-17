import pandas as pd


def test_source_columns_match_data_contract():
    df = pd.read_csv(
        "data/raw/dfi-departmental-spend-over-25000-for-july-2026-csv-format.csv",
        encoding="cp1252",
    )

    expected_columns = [
        "Department",
        "Organisation",
        "Check Date",
        "Expense type",
        "Supplier",
        "Invoice number",
        "Invoice Amount",
        "Postcode",
    ]

    assert list(df.columns) == expected_columns

def test_check_dates_match_expected_format():
    df = pd.read_csv(
        "data/raw/dfi-departmental-spend-over-25000-for-july-2026-csv-format.csv",
        encoding="cp1252",
    )

    parsed_dates = pd.to_datetime(
        df["Check Date"],
        format="%d/%m/%Y",
        errors="coerce",
    )

    assert parsed_dates.notna().all()

def test_invoice_amounts_can_be_parsed():
    df = pd.read_csv(
        "data/raw/dfi-departmental-spend-over-25000-for-july-2026-csv-format.csv",
        encoding="cp1252",
    )

    cleaned_amounts = (
        df["Invoice Amount"]
        .str.replace("£", "", regex=False)
        .str.replace(",", "", regex=False)
    )

    parsed_amounts = pd.to_numeric(cleaned_amounts, errors="coerce")

    assert parsed_amounts.notna().all()