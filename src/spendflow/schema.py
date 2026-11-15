"""Local schema for a reproducible investigation snapshot."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_files (
    source_file_id VARCHAR PRIMARY KEY, source_name VARCHAR NOT NULL,
    source_url VARCHAR, file_name VARCHAR NOT NULL, file_path VARCHAR NOT NULL,
    file_hash VARCHAR NOT NULL, downloaded_at TIMESTAMPTZ, loaded_at TIMESTAMPTZ NOT NULL,
    row_count BIGINT, mapping_name VARCHAR NOT NULL, snapshot_key VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id VARCHAR PRIMARY KEY, source_file_id VARCHAR NOT NULL REFERENCES source_files(source_file_id),
    source_row_number BIGINT NOT NULL, source_record_id VARCHAR,
    buyer_name_raw VARCHAR, buyer_name_normalised VARCHAR,
    supplier_name_raw VARCHAR, supplier_name_normalised VARCHAR,
    transaction_date DATE, amount DECIMAL(18,2), currency VARCHAR,
    description VARCHAR, department VARCHAR, category VARCHAR,
    invoice_reference VARCHAR, payment_reference VARCHAR, raw_record_hash VARCHAR NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL, UNIQUE(source_file_id, source_row_number)
);
CREATE TABLE IF NOT EXISTS supplier_aliases (
    supplier_alias_id VARCHAR PRIMARY KEY, supplier_name_raw VARCHAR NOT NULL UNIQUE,
    supplier_name_normalised VARCHAR NOT NULL, canonical_supplier_name VARCHAR,
    match_method VARCHAR NOT NULL, match_score DECIMAL(5,4),
    review_status VARCHAR NOT NULL CHECK (review_status IN ('proposed','accepted','rejected')),
    review_notes VARCHAR, created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS findings (
    finding_id VARCHAR PRIMARY KEY, source_file_id VARCHAR NOT NULL REFERENCES source_files(source_file_id),
    finding_type VARCHAR NOT NULL, finding_classification VARCHAR NOT NULL
        CHECK (finding_classification IN ('confirmed','suspicious','possible_savings')),
    title VARCHAR NOT NULL, description VARCHAR NOT NULL, evidence JSON NOT NULL,
    severity VARCHAR, confidence_score DECIMAL(5,4), estimated_value DECIMAL(18,2), currency VARCHAR,
    rule_name VARCHAR NOT NULL, rule_version VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'open', created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    reviewed_at TIMESTAMPTZ, review_notes VARCHAR
);
CREATE TABLE IF NOT EXISTS finding_transactions (
    finding_id VARCHAR REFERENCES findings(finding_id),
    transaction_id VARCHAR REFERENCES transactions(transaction_id), evidence_role VARCHAR NOT NULL,
    PRIMARY KEY(finding_id, transaction_id)
);
CREATE TABLE IF NOT EXISTS validation_evidence (
    finding_id VARCHAR PRIMARY KEY REFERENCES findings(finding_id),
    source_file_id VARCHAR NOT NULL REFERENCES source_files(source_file_id),
    transaction_id VARCHAR REFERENCES transactions(transaction_id),
    source_row_number BIGINT, field VARCHAR NOT NULL, error_type VARCHAR NOT NULL, raw_value VARCHAR
);
CREATE VIEW IF NOT EXISTS spend_records AS
SELECT t.*, coalesce(a.canonical_supplier_name, t.supplier_name_raw) AS supplier_identity
FROM transactions t
LEFT JOIN supplier_aliases a
    ON t.supplier_name_raw = a.supplier_name_raw AND a.review_status = 'accepted'
WHERE length(trim(t.supplier_name_raw)) > 0
  AND t.supplier_name_normalised IS NOT NULL
  AND t.amount IS NOT NULL AND t.currency IN ('GBP', 'EUR', 'USD')
QUALIFY row_number() OVER (
    PARTITION BY t.source_file_id, t.raw_record_hash ORDER BY t.source_row_number
) = 1;
"""
