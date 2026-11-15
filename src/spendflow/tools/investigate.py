"""Read-only, bounded investigation queries. File selection belongs to the app."""

import json
import re
from pathlib import Path

import duckdb

from spendflow.analysis.rules import CLASSIFICATIONS, TYPES, rows
from spendflow.mapping.dfi_transactions import SUPPORTED_CURRENCIES

PAGE_SIZE = 50


def _page(limit, offset):
    if type(limit) is not int or not 1 <= limit <= PAGE_SIZE:
        raise ValueError(f"limit must be an integer from 1 to {PAGE_SIZE}")
    if type(offset) is not int or not 0 <= offset <= 10000:
        raise ValueError("offset must be an integer from 0 to 10000")


def _finding_id(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("finding_id must be a 64-character lowercase hexadecimal ID")


class Investigation:
    """The application selects the database once; tool calls cannot override it."""

    def __init__(self, database: Path):
        self._database = Path(database).resolve()

    def _query(self, sql, params=()):
        with duckdb.connect(str(self._database), read_only=True,
                            config={"enable_external_access": "false", "threads": "2"}) as db:
            return rows(db, sql, params)

    def overview(self) -> dict:
        sources = self._query("SELECT source_name, file_name, file_hash FROM source_files LIMIT 1")
        counts = self._query("""
            SELECT finding_type, finding_classification, count(*) AS findings
            FROM findings GROUP BY ALL ORDER BY 1, 2
        """)
        return {"sources": sources,
                "transactions": self._query("SELECT count(*) AS n FROM transactions")[0]["n"],
                "finding_counts": counts}

    def list_findings(self, finding_type: str | None = None,
                      classification: str | None = None, limit: int = 20,
                      offset: int = 0) -> dict:
        _page(limit, offset)
        if finding_type is not None and finding_type not in TYPES:
            raise ValueError("Unknown finding type")
        if classification is not None and classification not in CLASSIFICATIONS:
            raise ValueError("Unknown classification")
        found = self._query("""
            SELECT finding_id, finding_type, finding_classification, title
            FROM findings WHERE (? IS NULL OR finding_type = ?)
                AND (? IS NULL OR finding_classification = ?)
            ORDER BY finding_type, finding_id LIMIT ? OFFSET ?
        """, [finding_type, finding_type, classification, classification, limit + 1, offset])
        return {"findings": found[:limit], "has_more": len(found) > limit}

    def get_finding(self, finding_id: str, limit: int = 20, offset: int = 0) -> dict:
        _finding_id(finding_id)
        _page(limit, offset)
        findings = self._query("""
            SELECT f.*, s.source_name, s.file_name, s.file_hash
            FROM findings f JOIN source_files s USING (source_file_id) WHERE f.finding_id = ?
        """, [finding_id])
        if not findings:
            return {"error": "Finding not found"}
        finding = findings[0]
        finding["evidence"] = json.loads(finding["evidence"])
        evidence = self._query("""
            SELECT ft.evidence_role, t.transaction_id, s.file_name, t.source_row_number,
                   t.transaction_date, t.buyer_name_raw, t.supplier_name_raw, t.department,
                   t.category, t.invoice_reference, t.payment_reference, t.amount,
                   t.currency, t.description
            FROM finding_transactions ft JOIN transactions t USING (transaction_id)
            JOIN source_files s USING (source_file_id)
            WHERE ft.finding_id = ?
            ORDER BY CASE ft.evidence_role WHEN 'candidate' THEN 0 ELSE 1 END,
                     t.source_row_number LIMIT ? OFFSET ?
        """, [finding_id, limit + 1, offset])
        return {"finding": finding, "transactions": evidence[:limit], "has_more": len(evidence) > limit}

    def compare_records(self, finding_id: str) -> dict:
        _finding_id(finding_id)
        detail = self.get_finding(finding_id)
        if "error" in detail:
            return detail
        statistics = self._query("""
            SELECT evidence_role, currency, count(*) AS total_records,
                   count(amount) AS records_with_amount, min(amount) AS min_amount,
                   max(amount) AS max_amount
            FROM finding_transactions JOIN transactions USING (transaction_id)
            WHERE finding_id = ? GROUP BY ALL ORDER BY 1, 2 LIMIT 50
        """, [finding_id])
        if not statistics:
            return {"error": "No linked transaction evidence; inspect the source-level finding."}
        return {**detail, "comparison_by_role_and_currency": statistics}

    def supplier_spend(self, supplier: str, currency: str) -> dict:
        if not isinstance(supplier, str) or not supplier.strip() or len(supplier) > 200:
            raise ValueError("supplier must be an exact raw or accepted canonical name of 1–200 characters")
        if currency not in SUPPORTED_CURRENCIES:
            raise ValueError("Unsupported currency")
        results = self._query("""
            SELECT supplier_identity, currency, count(*) AS transactions, sum(amount) AS net_spend
            FROM spend_records WHERE supplier_identity = coalesce(
                (SELECT canonical_supplier_name FROM supplier_aliases
                 WHERE supplier_name_raw = ? AND review_status = 'accepted'), ?)
                AND currency = ? GROUP BY ALL
        """, [supplier, supplier, currency])
        return results[0] if results else {"error": "No matching spend records for this supplier and currency"}
