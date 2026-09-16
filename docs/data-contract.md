# Initial Dataset Data Contract

## Source

Dataset: Department for Infrastructure departmental spend over £25,000
Sample file: `dfi-departmental-spend-over-25000-for-july-2026-csv-format.csv`

This file is used as SpendFlow's first real public-spending input.

The raw CSV must remain unchanged in `data/raw/`.

## Observed File Properties

* Encoding: `cp1252` / Windows-1252
* Rows: 292
* Columns: 8
* Missing values observed: 0
* Invalid dates observed: 0
* Invalid monetary amounts observed: 0
* Unique suppliers: 75
* Repeated invoice-number occurrences: 19
* Exact duplicate rows: 0

Repeated invoice numbers do not by themselves prove that duplicate payments exist.

## Expected Source Columns

| Source column    | Meaning                                         |
| ---------------- | ----------------------------------------------- |
| `Department`     | Department identifier supplied by the source    |
| `Organisation`   | Organisation making the payment                 |
| `Check Date`     | Date associated with the payment                |
| `Expense type`   | Spending or expense category                    |
| `Supplier`       | Supplier name as published                      |
| `Invoice number` | Source invoice reference                        |
| `Invoice Amount` | Published monetary amount                       |
| `Postcode`       | Postcode associated with the supplier or record |

All eight columns are expected for this initial source.

## Source-to-Canonical Mapping

| Source column    | Canonical field              | Transformation                                             |
| ---------------- | ---------------------------- | ---------------------------------------------------------- |
| `Department`     | `department`                 | Preserve source text                                       |
| `Organisation`   | `buyer_name_raw`             | Preserve source text                                       |
| `Check Date`     | `transaction_date`           | Parse using `DD/MM/YYYY`                                   |
| `Expense type`   | `category`                   | Preserve source text                                       |
| `Supplier`       | `supplier_name_raw`          | Preserve source text                                       |
| `Invoice number` | `invoice_reference`          | Preserve source text                                       |
| `Invoice Amount` | `amount`                     | Remove `£` and thousands separators, then parse as decimal |
| `Postcode`       | No canonical field currently | Preserve in the unchanged raw source                       |

The canonical `currency` value is `GBP` because monetary values in this source are published using the `£` symbol.

## Fields Created by SpendFlow

The following canonical fields are not directly supplied by this CSV and will be generated or populated during later processing:

* `transaction_id`
* `source_file_id`
* `source_row_number`
* `supplier_name_normalised`
* `buyer_name_normalised`
* `raw_record_hash`
* `loaded_at`
* `currency`

Fields for which this source provides no reliable value should remain null rather than being invented.

## Parsing Rules

### Dates

`Check Date` is expected in:

`DD/MM/YYYY`

Example:

`01/07/2026`

It will later be converted to the canonical `DATE` type.

### Monetary Amounts

`Invoice Amount` is supplied as formatted text.

Example:

`£336,631.50`

Before canonical storage:

1. remove the `£` symbol;
2. remove comma thousands separators;
3. parse the remaining value as a decimal monetary amount;
4. store the currency separately as `GBP`.

The raw value must not be overwritten.

## Data-Quality Observations

The sample contains no missing values in its eight published columns.

All observed `Check Date` values could be parsed using the expected date format.

All observed `Invoice Amount` values could be converted to numeric amounts using the documented transformation.

There are 19 repeated invoice-number occurrences. Therefore, `Invoice number` must not be treated as a globally unique transaction identifier.

There are no exact duplicate rows in the sample.

These observations describe this particular July 2026 file. Future files must still be validated rather than assumed to have the same quality.

## Traceability

Every canonical transaction created from this source must eventually retain:

* the source file it came from;
* its original row number;
* its original supplier value;
* enough information to trace a finding back to the published record.

No transformation may modify the original file stored in `data/raw/`.
