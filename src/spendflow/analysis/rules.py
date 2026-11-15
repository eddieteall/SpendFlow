"""Deterministic rules over one source snapshot."""

import json
import re
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
from statistics import median

VERSION = "1"
TYPES = (
    "missing_data", "potential_duplicate", "supplier_identity",
    "unusual_transaction", "price_increase", "fragmented_spend",
)
CLASSIFICATIONS = ("confirmed", "suspicious", "possible_savings")


def key(*parts):
    return sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def rows(db, query, params=()):
    cursor = db.execute(query, params)
    names = [field[0] for field in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def groups(records, *fields):
    grouped = defaultdict(list)
    for record in records:
        grouped[tuple(record[field] for field in fields)].append(record)
    return grouped


def alias_key(raw):
    text = " ".join(re.sub(r"[^\w\s]", " ", raw.casefold()).split())
    return re.sub(r"\s+limited$", " ltd", text)


class Findings:
    def __init__(self, db, source_id):
        self.db, self.source_id = db, source_id

    def add(self, kind, classification, rule, title, explanation, evidence, links=()):
        ids = sorted((record["transaction_id"], role) for record, role in links)
        finding_id = key(self.source_id, rule, VERSION, ids, evidence)
        self.db.execute("""
            INSERT INTO findings (finding_id, source_file_id, finding_type,
              finding_classification, title, description, evidence, rule_name, rule_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [finding_id, self.source_id, kind, classification, title, explanation,
              json.dumps(evidence, sort_keys=True, default=str), rule, VERSION])
        if ids:
            self.db.executemany("INSERT INTO finding_transactions VALUES (?, ?, ?)",
                                [(finding_id, tx, role) for tx, role in ids])
        return finding_id

    def validation(self, errors, records):
        by_row = {r["source_row_number"]: r for r in records}
        for error in errors:
            number, field, problem, value = (error[k] for k in
                ("source_row_number", "field", "error_type", "raw_value"))
            record = by_row.get(number)
            finding_id = self.add(
                "missing_data", "confirmed", problem, f"Data quality: {field}",
                error.get("message", f"The source value for {field} has condition {problem.replace('_', ' ')}."),
                error, [(record, "affected")] if record else [],
            )
            self.db.execute("INSERT INTO validation_evidence VALUES (?, ?, ?, ?, ?, ?, ?)",
                [finding_id, self.source_id, record["transaction_id"] if record else None,
                 number, field, problem, value])

    def detect(self, records, decisions):
        for (raw_hash,), matched in groups(records, "raw_record_hash").items():
            if len(matched) > 1:
                self.add("missing_data", "confirmed", "repeated_publication_row",
                         "Repeated source values", "The published field values repeat. Check the original records before drawing a payment conclusion.",
                         {"raw_record_hash": raw_hash}, [(r, "repeated_row") for r in matched])
        self.aliases(records, decisions)
        eligible = rows(self.db, "SELECT * FROM spend_records ORDER BY source_row_number")
        self.duplicates(eligible)
        self.unusual(eligible)
        self.recurring(eligible)
        self.fragmented()

    def aliases(self, records, decisions):
        names = sorted({r["supplier_name_raw"] for r in records if r["supplier_name_normalised"]})
        buckets = defaultdict(list)
        for raw in names:
            buckets[alias_key(raw)].append(raw)
        candidates = {raw for names in buckets.values() if len(names) > 1 for raw in names}
        if not decisions.keys() <= candidates:
            raise ValueError("Alias decisions must name an exact raw supplier in a proposed group")
        for normal, names in buckets.items():
            if len(names) < 2:
                continue
            states = {}
            for raw in names:
                choice = decisions.get(raw, {})
                status = choice.get("status", "proposed")
                canonical = choice.get("canonical")
                if status == "accepted" and (canonical not in names or
                    decisions.get(canonical, {}).get("status", "proposed") == "rejected" or
                    (decisions.get(canonical, {}).get("status") == "accepted" and
                     decisions[canonical].get("canonical") != canonical)):
                    raise ValueError("Accepted aliases must point to a local, non-rejected root name")
                states[raw] = status
                self.db.execute("""
                    INSERT INTO supplier_aliases (supplier_alias_id, supplier_name_raw,
                      supplier_name_normalised, canonical_supplier_name, match_method,
                      match_score, review_status, review_notes)
                    VALUES (?, ?, ?, ?, 'exact_alias_key', 1.0000, ?, ?)
                """, [key(self.source_id, raw), raw, normal, canonical, status, choice.get("notes")])
            match = [r for r in records if r["supplier_name_raw"] in names]
            self.add("supplier_identity", "suspicious", "exact_alias_key", "Supplier name variants",
                     "Different raw supplier names share a normalised key. Review the identity before combining spend.",
                     {"normalised_key": normal, "review_status_by_name": states}, [(r, "variant") for r in match])

    def duplicates(self, records):
        fields = ("buyer_name_normalised", "supplier_identity", "currency", "amount", "invoice_reference")
        eligible = [r for r in records if r["amount"] > 0 and all(
            r[f] for f in ("buyer_name_normalised", "transaction_date"))
            and (r["invoice_reference"] or "").strip()]
        for signature, match in groups(eligible, *fields).items():
            def emit(cohort, gap):
                references = {r["payment_reference"] for r in cohort if r["payment_reference"]}
                missing = [] if all(r["payment_reference"] for r in cohort) else ["payment_reference"]
                self.add("potential_duplicate", "suspicious",
                         "strong_same_date" if gap == 0 else "strong_near_date",
                         "Potential duplicate payment",
                         "Buyer, supplier identity, currency, positive amount and invoice reference match. "
                         f"Dates are {gap} days apart. Verify with invoice and payment-system evidence.",
                         {"matched": dict(zip(fields, signature)), "date_gap_days": gap,
                          "missing": missing, "payment_references": sorted(references)},
                         [(r, "candidate") for r in cohort])
            ordered = sorted(match, key=lambda r: r["transaction_date"])
            by_date = groups(ordered, "transaction_date")
            for same_date in by_date.values():
                if len(same_date) > 1:
                    emit(same_date, 0)
            # Keep near-date findings to isolated pairs; avoid chaining nearby dates.
            if len(ordered) == 2:
                gap = (ordered[1]["transaction_date"] - ordered[0]["transaction_date"]).days
                if 1 <= gap <= 2:
                    emit(ordered, gap)

    def unusual(self, records):
        fields = ("buyer_name_normalised", "category", "currency")
        eligible = [r for r in records if r["buyer_name_normalised"] and r["category"]
                    and r["transaction_date"] and r["amount"] > 0]
        for signature, cohort in groups(eligible, *fields).items():
            if len(cohort) < 6:
                continue
            for candidate in cohort:
                peers = [r for r in cohort if r is not candidate]
                baseline = median(r["amount"] for r in peers)
                threshold = baseline * 3
                if candidate["amount"] > threshold:
                    self.add("unusual_transaction", "suspicious", "positive_peer_median",
                             "High amount for this peer group",
                             "The amount exceeds three times the median of other positive payments in the same buyer, category and currency.",
                             {"cohort": dict(zip(fields, signature)), "peer_count": len(peers),
                              "median": baseline, "threshold": threshold, "amount": candidate["amount"]},
                             [(candidate, "candidate")] + [(r, "comparison") for r in peers])

    def recurring(self, records):
        fields = ("buyer_name_normalised", "supplier_identity", "currency", "department", "description")
        eligible = [r for r in records if r["transaction_date"] and r["amount"] > 0
                    and r["buyer_name_normalised"] and r["department"]
                    and (r["description"] or "").strip() and (r["invoice_reference"] or "").strip()]
        for signature, cohort in groups(eligible, *fields).items():
            ordered = sorted(cohort, key=lambda r: r["transaction_date"])
            for end in range(4, len(ordered) + 1):
                window = ordered[end-4:end]
                dates = [r["transaction_date"] for r in window]
                if (not all(27 <= (b - a).days <= 33 for a, b in zip(dates, dates[1:]))
                    or len({r["invoice_reference"] for r in window}) != 4
                    or (end > 4 and ordered[end-5]["transaction_date"] == dates[0])
                    or (end < len(ordered) and ordered[end]["transaction_date"] == dates[-1])):
                    continue
                baseline = median(r["amount"] for r in window[:3])
                if any(abs(r["amount"] - baseline) > baseline * Decimal("0.05") for r in window[:3]):
                    continue
                delta = window[-1]["amount"] - baseline
                if delta < baseline * Decimal("0.20"):
                    continue
                self.add("price_increase", "suspicious", "monthly_description_baseline",
                         "Recurring payment amount increased",
                         "Four distinct invoices show a monthly cadence for the same described service. "
                         "The latest payment is at least 20% above the earlier median. Quantity and contract evidence are unavailable; check before inferring unit price.",
                         {"series": dict(zip(fields, signature)), "baseline": baseline,
                          "latest": window[-1]["amount"], "increase": delta,
                          "increase_pct": (delta * 100 / baseline).quantize(Decimal("0.01"))},
                         [(r, "baseline") for r in window[:3]] + [(window[-1], "candidate")])

    def fragmented(self):
        totals = rows(self.db, """
            SELECT supplier_identity, currency, department, sum(amount) AS net
            FROM spend_records WHERE department IS NOT NULL AND trim(department) <> ''
            GROUP BY ALL ORDER BY supplier_identity, currency, department
        """)
        for (supplier, currency), breakdown in groups(totals, "supplier_identity", "currency").items():
            if sum(r["net"] > 0 for r in breakdown) < 2:
                continue
            evidence = rows(self.db, """
                SELECT transaction_id FROM spend_records WHERE supplier_identity = ? AND currency = ?
                  AND department IS NOT NULL AND trim(department) <> ''
            """, [supplier, currency])
            self.add("fragmented_spend", "possible_savings", "multiple_departments",
                     "Supplier spend across departments",
                     "At least two departments have positive net spend with this supplier. Check whether consolidation is practical.",
                     {"supplier": supplier, "currency": currency,
                      "net_by_department": {r["department"]: r["net"] for r in breakdown}},
                     [(r, "department_spend") for r in evidence])
