"""Read models for the dashboard, separate from the assistant's tool interface."""

from spendflow.tools.investigate import Investigation, PAGE_SIZE


class DashboardData(Investigation):
    def summary(self):
        return self._query("""
            SELECT (SELECT count(*) FROM findings WHERE status = 'open') AS open_findings,
                   (SELECT count(DISTINCT supplier_identity) FROM spend_records) AS suppliers
        """)[0]

    def opportunity_values(self):
        return self._query("""
            SELECT currency, sum(estimated_value) AS amount FROM findings
            WHERE finding_classification = 'possible_savings' AND status = 'open'
              AND estimated_value IS NOT NULL AND currency IS NOT NULL
            GROUP BY currency ORDER BY currency
        """)

    def monthly_spend(self):
        return self._query("""
            SELECT CAST(date_trunc('month', transaction_date) AS DATE) AS month,
                   currency, sum(amount) AS amount
            FROM spend_records WHERE transaction_date IS NOT NULL
            GROUP BY ALL ORDER BY month, currency
        """)

    def finding_register(self, kind, classification, severity, status, supplier, search, page):
        return self._query("""
            WITH linked AS (
                SELECT ft.finding_id,
                       string_agg(DISTINCT t.supplier_name_raw, ', ' ORDER BY t.supplier_name_raw)
                           FILTER (WHERE ft.evidence_role NOT IN ('comparison', 'baseline')) AS supplier,
                       min(t.transaction_date)
                           FILTER (WHERE ft.evidence_role NOT IN ('comparison', 'baseline')) AS first_date
                FROM finding_transactions ft JOIN transactions t USING (transaction_id)
                GROUP BY ft.finding_id
            )
            SELECT f.finding_id, f.title, f.finding_type, f.finding_classification,
                   f.rule_name, f.severity, f.status, f.estimated_value, f.currency,
                   linked.first_date, linked.supplier
            FROM findings f LEFT JOIN linked USING (finding_id)
            WHERE (? IS NULL OR f.finding_type = ?)
              AND (? IS NULL OR f.finding_classification = ?)
              AND (? IS NULL OR coalesce(f.severity, 'Unassigned') = ?)
              AND (? IS NULL OR f.status = ?)
              AND (? IS NULL OR EXISTS (
                  SELECT 1 FROM finding_transactions ft JOIN transactions t USING (transaction_id)
                  WHERE ft.finding_id = f.finding_id AND t.supplier_name_raw = ?
                    AND ft.evidence_role NOT IN ('comparison', 'baseline')
              ))
              AND contains(lower(concat_ws(' ', f.title, f.rule_name, f.finding_id, linked.supplier)), lower(?))
            ORDER BY f.finding_type, f.finding_id LIMIT ? OFFSET ?
        """, [kind, kind, classification, classification, severity, severity, status, status,
              supplier, supplier, search, PAGE_SIZE + 1, (page - 1) * PAGE_SIZE])

    def finding_options(self):
        return self._query("SELECT DISTINCT coalesce(severity, 'Unassigned') AS severity, status FROM findings")

    def transaction_options(self):
        return self._query("SELECT DISTINCT department, supplier_name_raw FROM transactions")

    def transactions(self, search, department, with_findings, page):
        return self._query("""
            WITH linked AS (
                SELECT transaction_id, count(*) AS finding_count FROM finding_transactions GROUP BY 1
            )
            SELECT t.*, s.file_name, coalesce(linked.finding_count, 0) AS finding_count
            FROM transactions t JOIN source_files s USING (source_file_id)
            LEFT JOIN linked USING (transaction_id)
            WHERE (? IS NULL OR t.department = ?)
              AND (? IS NULL OR (linked.finding_count IS NOT NULL) = ?)
              AND contains(lower(concat_ws(' ', supplier_name_raw, description, category, transaction_id)), lower(?))
            ORDER BY transaction_date NULLS LAST, s.file_name, source_row_number
            LIMIT ? OFFSET ?
        """, [department, department, with_findings, with_findings, search,
              PAGE_SIZE + 1, (page - 1) * PAGE_SIZE])

    def suppliers(self, search, page):
        return self._query("""
            SELECT sp.supplier_identity, sp.currency, sum(sp.amount) AS amount,
                   count(*) AS transactions,
                   (SELECT count(DISTINCT f.finding_id)
                    FROM spend_records linked
                    JOIN finding_transactions ft USING (transaction_id)
                    JOIN findings f USING (finding_id)
                    WHERE linked.supplier_identity = sp.supplier_identity
                      AND linked.currency = sp.currency AND f.status = 'open') AS open_findings
            FROM spend_records sp
            WHERE contains(lower(sp.supplier_identity), lower(?))
            GROUP BY sp.supplier_identity, sp.currency ORDER BY amount DESC, supplier_identity, currency
            LIMIT ? OFFSET ?
        """, [search, PAGE_SIZE + 1, (page - 1) * PAGE_SIZE])

    def aliases(self):
        return self._query("""
            SELECT supplier_name_raw, canonical_supplier_name, supplier_name_normalised,
                   review_status, review_notes
            FROM supplier_aliases ORDER BY supplier_name_normalised, review_status, supplier_name_raw
        """)

    def quality(self):
        return self._query("""
            SELECT count(*) AS total, count(transaction_date) AS dates, count(amount) AS amounts,
                   count(*) FILTER (WHERE trim(supplier_name_raw) <> '') AS suppliers,
                   count(*) FILTER (WHERE trim(description) <> '') AS descriptions,
                   count(*) FILTER (WHERE trim(department) <> '') AS departments
            FROM transactions
        """)[0]

    def affected(self, page):
        return self._query("""
            SELECT coalesce(v.source_row_number, t.source_row_number) AS source_row,
                   s.file_name, f.title, coalesce(v.field, 'source row') AS field,
                   f.description, v.raw_value
            FROM findings f JOIN source_files s USING (source_file_id)
            LEFT JOIN validation_evidence v USING (finding_id)
            LEFT JOIN finding_transactions ft USING (finding_id)
            LEFT JOIN transactions t ON t.transaction_id = ft.transaction_id
            WHERE f.finding_type = 'missing_data'
            ORDER BY source_row NULLS FIRST, f.finding_id
            LIMIT ? OFFSET ?
        """, [PAGE_SIZE + 1, (page - 1) * PAGE_SIZE])
