# SpendFlow Data Model

## Purpose

SpendFlow uses a canonical transaction model: a standard internal representation of a purchasing transaction.

Each source dataset may use different column names and formats. A source-specific mapping step converts those fields into the canonical model before validation, analysis or storage.

This allows SpendFlow to support additional public, anonymised or synthetic datasets without rewriting the core detection logic.

## Data-Modelling Principles

1. Raw source files remain unchanged.
2. Every canonical transaction remains traceable to its original source file and source row.
3. Source-specific fields are mapped into standard internal field names.
4. Missing values remain explicit rather than being silently invented.
5. Original values may be preserved alongside cleaned or normalised values.
6. Monetary amounts must include a currency.
7. Findings are stored separately from transactions because a transaction may have zero, one or several findings.

## Canonical Transaction Table

The `transactions` table stores one canonical record for each source transaction.

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `transaction_id` | `VARCHAR` | Yes | SpendFlow-generated unique identifier for the canonical transaction. |
| `source_file_id` | `VARCHAR` | Yes | Identifies the source file from which the record originated. |
| `source_row_number` | `BIGINT` | Yes | Original row number within the source file, used for traceability. |
| `source_record_id` | `VARCHAR` | No | Transaction identifier supplied by the original dataset, when available. |
| `buyer_name_raw` | `VARCHAR` | No | Buyer or public body name exactly as supplied by the source. |
| `buyer_name_normalised` | `VARCHAR` | No | Standardised buyer name used for comparison and grouping. |
| `supplier_name_raw` | `VARCHAR` | No | Supplier name exactly as supplied by the source. |
| `supplier_name_normalised` | `VARCHAR` | No | Standardised supplier name used for matching and analysis. |
| `transaction_date` | `DATE` | No | Date associated with the payment or transaction. |
| `amount` | `DECIMAL(18,2)` | No | Parsed monetary value of the transaction. |
| `currency` | `VARCHAR` | Yes | Currency code, such as `GBP`. |
| `description` | `VARCHAR` | No | Available description of the goods, services or payment. |
| `department` | `VARCHAR` | No | Department, cost centre or organisational unit, when available. |
| `category` | `VARCHAR` | No | Procurement or spending category, when supplied or reliably mapped. |
| `invoice_reference` | `VARCHAR` | No | Invoice number or invoice reference, when available. |
| `payment_reference` | `VARCHAR` | No | Payment or transaction reference, when available. |
| `raw_record_hash` | `VARCHAR` | Yes | Hash of the original source row used to support traceability and repeatable ingestion. |
| `loaded_at` | `TIMESTAMP` | Yes | Time at which the canonical record was loaded into SpendFlow. |

A nullable field is allowed to contain no value. Public datasets often omit invoice references, categories or descriptions, so SpendFlow must record these fields as missing rather than inventing replacement values.

The raw and normalised supplier names are stored separately. This preserves the source evidence while allowing records such as `ACME LTD` and `Acme Limited` to be compared during supplier-identity analysis.

## Source Files Table

The `source_files` table records metadata about every dataset imported into SpendFlow.

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `source_file_id` | `VARCHAR` | Yes | SpendFlow-generated unique identifier for the source file. |
| `source_name` | `VARCHAR` | Yes | Human-readable name of the organisation or dataset provider. |
| `source_url` | `VARCHAR` | No | Web address from which the file was downloaded. |
| `file_name` | `VARCHAR` | Yes | Original file name. |
| `file_path` | `VARCHAR` | Yes | Location of the preserved raw file within the project. |
| `file_hash` | `VARCHAR` | Yes | Hash of the complete raw file used to detect changes and confirm file integrity. |
| `downloaded_at` | `TIMESTAMP` | No | Time at which the file was downloaded. |
| `loaded_at` | `TIMESTAMP` | Yes | Time at which SpendFlow processed the file. |
| `row_count` | `BIGINT` | No | Number of data rows observed in the source file. |
| `mapping_name` | `VARCHAR` | Yes | Name or version of the source-specific mapping used to create canonical transactions. |

A file hash is a reproducible digital fingerprint calculated from the file contents. If the raw file changes, its hash will normally change as well.

The `source_files` table has a one-to-many relationship with `transactions`: one source file may produce many canonical transaction records.

## Supplier Aliases Table

The `supplier_aliases` table records relationships between supplier-name variations and a canonical supplier identity.

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `supplier_alias_id` | `VARCHAR` | Yes | Unique identifier for the alias record. |
| `supplier_name_raw` | `VARCHAR` | Yes | Supplier name exactly as it appeared in the source data. |
| `supplier_name_normalised` | `VARCHAR` | Yes | Standardised form used for comparison. |
| `canonical_supplier_name` | `VARCHAR` | No | Preferred supplier name when an identity match has been accepted. |
| `match_method` | `VARCHAR` | Yes | Method used to propose the match, such as exact normalisation, manual review or fuzzy matching. |
| `match_score` | `DECIMAL(5,4)` | No | Similarity score produced by a matching method, when applicable. |
| `review_status` | `VARCHAR` | Yes | Status such as `proposed`, `accepted` or `rejected`. |
| `review_notes` | `VARCHAR` | No | Explanation or evidence supporting the review decision. |
| `created_at` | `TIMESTAMP` | Yes | Time at which the alias record was created. |

A proposed alias must not be treated as a confirmed supplier identity until it has been accepted through a defined rule or review process.

The original supplier name remains stored in the `transactions` table. The alias table adds an interpretation layer without overwriting source evidence.

## Findings Table

The `findings` table stores issues and opportunities produced by deterministic Python or SQL analysis.

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `finding_id` | `VARCHAR` | Yes | Unique identifier for the finding. |
| `finding_type` | `VARCHAR` | Yes | Category such as `potential_duplicate`, `supplier_identity`, `price_increase`, `unusual_transaction`, `fragmented_spend` or `missing_data`. |
| `finding_classification` | `VARCHAR` | Yes | Classification such as `confirmed`, `suspicious` or `possible_savings`. |
| `title` | `VARCHAR` | Yes | Short human-readable summary of the finding. |
| `description` | `VARCHAR` | Yes | Explanation of what was detected and why it may require investigation. |
| `severity` | `VARCHAR` | No | Indicative priority such as `low`, `medium` or `high`. |
| `confidence_score` | `DECIMAL(5,4)` | No | Optional score showing the strength of the detection evidence. |
| `estimated_value` | `DECIMAL(18,2)` | No | Possible financial value associated with the finding. |
| `currency` | `VARCHAR` | No | Currency code for the estimated value, such as `GBP`. |
| `rule_name` | `VARCHAR` | Yes | Name of the deterministic rule or query that created the finding. |
| `rule_version` | `VARCHAR` | No | Version of the detection rule used. |
| `status` | `VARCHAR` | Yes | Investigation status such as `open`, `reviewed`, `dismissed` or `resolved`. |
| `created_at` | `TIMESTAMP` | Yes | Time at which the finding was generated. |
| `reviewed_at` | `TIMESTAMP` | No | Time at which a human reviewed the finding. |
| `review_notes` | `VARCHAR` | No | Notes explaining the review outcome. |

A finding must include evidence linking it to the relevant transactions. This can be represented using a separate linking table:

| Field | Type | Required | Purpose |
|---|---|---:|---|
| `finding_id` | `VARCHAR` | Yes | References the associated finding. |
| `transaction_id` | `VARCHAR` | Yes | References a transaction supporting the finding. |
| `evidence_role` | `VARCHAR` | No | Describes how the transaction supports the finding, such as `candidate`, `comparison` or `baseline`. |

The `estimated_value` field represents a possible opportunity only. It must not be interpreted as a guaranteed saving.

A suspicious finding remains an investigative signal until evidence or human review confirms the underlying issue.

## Source-Specific Mapping Contract

Each supported dataset must have an explicit mapping from its source columns to SpendFlow’s canonical transaction fields.

A source mapping should define:

- the source dataset name;
- the expected source column names;
- the corresponding canonical fields;
- date and number formats;
- the assumed currency;
- required and optional source columns;
- rules for handling blank or invalid values;
- any source-specific transformations;
- a mapping version for traceability.

Example:

| Source column | Canonical field | Transformation |
|---|---|---|
| `Supplier` | `supplier_name_raw` | Preserve the original text. |
| `Payment Date` | `transaction_date` | Parse using the documented source date format. |
| `Amount Paid` | `amount` | Remove valid formatting characters and parse as a decimal value. |
| `Description` | `description` | Preserve the supplied text. |
| `Department` | `department` | Preserve the supplied text. |

The mapping process must not modify the raw CSV file. It creates a separate canonical representation derived from that file.

When a source field is unavailable, the corresponding nullable canonical field should remain empty. SpendFlow must not invent invoice references, categories, descriptions or other missing values.

If a required source column is missing or cannot be interpreted reliably, the problem should be recorded as a data-quality issue rather than silently ignored.

Source-specific transformations must occur before canonical validation, but general analysis rules must operate only on canonical fields.