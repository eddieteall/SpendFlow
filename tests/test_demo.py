import json
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

from spendflow.analysis.rules import Findings
from spendflow.load import PUBLIC, load_dataset
from spendflow.mapping.dfi_transactions import map_dfi_file, parse_amount
from spendflow.tools.agent import NO_EVIDENCE, investigate
from spendflow.tools.investigate import Investigation

REVIEWS = json.loads(Path("data/synthetic-alias-reviews.json").read_text())
PUBLIC_HASH = "5d77ab3552991b2558b3988a3e953013bcca57aa09ac437becf4016fb44c18ab"
RECURRING_ID = "603578fb68df70b99e36a591d06009ca91b8892d6cf4c69001f557f6c484c5f3"


def snapshot(db):
    with duckdb.connect(str(db), read_only=True, config={"threads": "2"}) as con:
        return [
            con.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall()
            for table in ("source_files", "transactions", "findings", "finding_transactions",
                          "validation_evidence", "supplier_aliases")
        ]


@pytest.fixture(scope="module")
def synthetic_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("synthetic") / "demo.duckdb"
    load_dataset("synthetic", db, decisions=REVIEWS)
    return db


def test_public_exact_amount_trace_and_rerun(tmp_path):
    db = tmp_path / "public.duckdb"
    result = load_dataset("public", db)
    assert result["transactions"] == 292
    assert result["findings"] == 36
    assert result["file_sha256"] == sha256(PUBLIC.read_bytes()).hexdigest() == PUBLIC_HASH
    with duckdb.connect(str(db), read_only=True, config={"threads": "2"}) as con:
        actual = con.execute("""
            SELECT amount, transaction_date, description, payment_reference, typeof(amount),
                   s.file_path, supplier_name_raw
            FROM transactions JOIN source_files s USING(source_file_id) WHERE source_row_number = 2
        """).fetchone()
        assert actual[:5] == (Decimal("336631.50"), date(2026, 7, 1), None, None, "DECIMAL(18,2)")
        assert actual[-1] == "GIBSON QUARRIES"
        assert Path(actual[5]).read_bytes() == PUBLIC.read_bytes()
        assert con.execute("SELECT source_row_number FROM transactions ORDER BY 1").fetchall() == [
            (row,) for row in range(2, 294)]
    before = snapshot(db)
    assert load_dataset("public", db) == result
    assert snapshot(db) == before


def test_csv_text_encoding_blank_and_record_position(tmp_path):
    source = tmp_path / "example.csv"
    source.write_bytes((
        "Department,Organisation,Check Date,Expense type,Supplier,Invoice number,Invoice Amount,Postcode\r\n"
        'D,Buyer,01/07/2026,C,"Café\r\nServices",00042,"-£1,234.50",\r\n'
        "\r\n"
        "D,Buyer,01/07/2026,C,,,100.00,\r\n"
        "D,Buyer,01/07/2026,C,Supplier\r\n"
    ).encode("cp1252"))
    records, errors = map_dfi_file(source, "id")
    first, blank, short = records
    assert first["supplier_name_raw"] == "Café\r\nServices"
    assert first["supplier_name_normalised"] == "café services"
    assert first["invoice_reference"] == "00042" and first["amount"] == Decimal("-1234.50")
    assert first["transaction_id"] == "d5a5e17dee2ccd173d9eb1d4f7df6fa42632a946fce49cd586b36f5f534ce512"
    assert [r["source_row_number"] for r in records] == [2, 3, 4]
    assert blank["invoice_reference"] == "" and short["invoice_reference"] is None
    assert {(e["source_row_number"], e["error_type"]) for e in errors} == {
        (3, "missing_value"), (4, "missing_value"), (4, "wrong_column_count")}


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "1e4", "1,2", "££2",
                                  "2.345", "10000000000000000.00", "--1", "10£"])
def test_reject_bad_amount(value):
    assert parse_amount(value) is None


def test_decimal_range_boundary():
    assert parse_amount("£9,999,999,999,999,999.99") == Decimal("9999999999999999.99")


def test_bad_header_persists_source_evidence(tmp_path):
    path = tmp_path / "malformed.csv"
    path.write_text("Supplier,Invoice number\nSup,0001\n")
    database = tmp_path / "bad.duckdb"
    result = load_dataset("public", database, input_path=path)
    assert "missing expected columns" in result["mapping_error"]
    tools = Investigation(database)
    finding_id = tools.list_findings("missing_data", "confirmed")["findings"][0]["finding_id"]
    detail = tools.get_finding(finding_id)
    assert detail["finding"]["file_name"] == path.name
    assert detail["transactions"] == []
    assert "No linked transaction evidence" in tools.compare_records(finding_id)["error"]
    with duckdb.connect(str(database), read_only=True) as con:
        assert con.execute("SELECT source_file_id, transaction_id FROM validation_evidence").fetchone() == (
            result["source_file_id"], None)
    assert load_dataset("public", database, input_path=path) == result


def test_atomic_load_retry(tmp_path, monkeypatch):
    db = tmp_path / "retry.duckdb"
    with monkeypatch.context() as patch:
        original = Findings.detect

        def fail_after_inserts(self, *args):
            original(self, *args)
            raise RuntimeError("test rollback")

        patch.setattr(Findings, "detect", fail_after_inserts)
        with pytest.raises(RuntimeError, match="test rollback"):
            load_dataset("synthetic", db, decisions=REVIEWS)
    with duckdb.connect(str(db), read_only=True, config={"threads": "2"}) as con:
        assert con.execute("SHOW TABLES").fetchall() == []
    result = load_dataset("synthetic", db, decisions=REVIEWS)
    assert (result["transactions"], result["findings"]) == (23, 11)


def test_synthetic_exact_evidence_and_alias_rollup(synthetic_db, tmp_path):
    tools = Investigation(synthetic_db)
    found = tools.list_findings(limit=50)["findings"]
    details = {d["finding"]["rule_name"]: d
               for d in (tools.get_finding(f["finding_id"]) for f in found)}

    def linked(rule):
        return {t["source_row_number"]: t["evidence_role"] for t in details[rule]["transactions"]}

    assert len(found) == len(details) == 11
    assert linked("strong_same_date") == {10: "candidate", 11: "candidate"}
    assert linked("strong_near_date") == {12: "candidate", 13: "candidate"}
    assert linked("repeated_publication_row") == {14: "repeated_row", 15: "repeated_row"}
    for rule in ("invalid_date", "invalid_amount", "missing_value", "unsupported_currency"):
        assert linked(rule) == {16: "affected"}
    assert linked("positive_peer_median") == {**dict.fromkeys(range(2, 9), "comparison"), 9: "candidate"}
    assert linked("monthly_description_baseline") == {2: "baseline", 3: "baseline", 4: "baseline", 5: "candidate"}
    recurring = details["monthly_description_baseline"]["finding"]
    assert recurring["finding_id"] == RECURRING_ID
    assert recurring["evidence"]["increase"] == "30.00"
    assert recurring["evidence"]["increase_pct"] == "30.00"
    assert linked("exact_alias_key") == dict.fromkeys(range(2, 8), "variant")
    assert details["exact_alias_key"]["finding"]["evidence"]["review_status_by_name"] == {
        "Demo Services Ltd": "proposed", "Demo Services Limited": "accepted", "Demo Services Ltd.": "rejected"}
    assert linked("multiple_departments") == dict.fromkeys(range(2, 7), "department_spend")
    assert details["multiple_departments"]["finding"]["evidence"]["net_by_department"] == {
        "D1": "430.00", "D2": "100.00"}
    assert tools.supplier_spend("Demo Services Limited", "GBP")["net_spend"] == Decimal("530.00")
    assert tools.supplier_spend("Demo Services Ltd.", "GBP")["net_spend"] == Decimal("100.00")
    assert tools.supplier_spend("Demo Services North Ltd", "GBP")["net_spend"] == Decimal("100.00")
    assert tools.supplier_spend("Demo Repairs Ltd", "GBP")["net_spend"] == Decimal("700.00")
    assert tools.supplier_spend("Demo Repairs Ltd", "EUR")["net_spend"] == Decimal("10000.00")
    assert tools.supplier_spend("Demo Parts Ltd", "GBP")["net_spend"] == Decimal("385.00")
    assert tools.list_findings("potential_duplicate", "confirmed")["findings"] == []
    assert tools.list_findings(limit=1)["has_more"]
    proposed_db = tmp_path / "proposed.duckdb"
    load_dataset("synthetic", proposed_db)
    assert Investigation(proposed_db).list_findings("fragmented_spend")["findings"] == []
    before = snapshot(synthetic_db)
    load_dataset("synthetic", synthetic_db, decisions=REVIEWS)
    assert snapshot(synthetic_db) == before
    fresh_dir = tmp_path / "fresh"
    independent = fresh_dir / "new.duckdb"
    load_dataset("synthetic", independent, decisions=REVIEWS)
    assert Investigation(independent).get_finding(RECURRING_ID)["transactions"] == (
        details["monthly_description_baseline"]["transactions"])


def test_fake_provider_dispatch_and_read_only(synthetic_db):
    read = Investigation(synthetic_db)
    before = sha256(synthetic_db.read_bytes()).hexdigest()

    class Fake:
        def __init__(self, calls, answer):
            self.calls, self.answer = calls, answer
            self.results = []

        def complete(self, messages, tools):
            assert {t["function"]["name"] for t in tools} == {
                "list_findings", "get_finding", "compare_records", "supplier_spend"}
            if messages[-1]["role"] == "user":
                return {"tool_calls": [
                    {"type": "function", "id": str(i),
                     "function": {"name": name, "arguments": json.dumps(args)}}
                    for i, (name, args) in enumerate(self.calls)
                ]}
            self.results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            return {"content": self.answer}

    provider = Fake([
        ("run_sql", {"sql": "DELETE FROM transactions"}),
        ("list_findings", {"limit": True}),
        ("get_finding", {"finding_id": "0" * 64}),
        ("get_finding", {"finding_id": RECURRING_ID, "database": "/tmp/another.duckdb"}),
    ], "Unsupported conclusion")
    result = investigate("Is there any evidence?", read, provider)
    assert result["answer"] == NO_EVIDENCE
    assert provider.results == [{"error": message} for message in (
        "Unknown tool", "Invalid tool arguments", "Finding not found", "Invalid tool arguments")]
    transaction = read.get_finding(RECURRING_ID)["transactions"][0]["transaction_id"]
    provider = Fake([("compare_records", {"finding_id": RECURRING_ID})],
                    f"Finding {RECURRING_ID}, transaction {transaction}: review the higher amount.")
    result = investigate("Why was the monthly equipment payment flagged?", read, provider)
    assert result["tools_called"] == ["compare_records"]
    assert transaction in result["answer"]
    assert provider.results[0]["comparison_by_role_and_currency"][0]["min_amount"] == "100.00"
    assert sha256(synthetic_db.read_bytes()).hexdigest() == before


def test_streamlit_demo_opens_evidence(tmp_path, monkeypatch):
    root = Path.cwd()
    dashboard = root / "src/spendflow/app/dashboard.py"
    folder = tmp_path / "data" / "processed"
    load_dataset("public", folder / "public.duckdb", input_path=root / PUBLIC)
    load_dataset("synthetic", folder / "synthetic.duckdb",
                 input_path=root / "data/synthetic-spend.csv", decisions=REVIEWS)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = AppTest.from_file(str(dashboard), default_timeout=20).run()
    assert not app.exception
    assert {m.label: m.value for m in app.metric}["Transactions"] == "292"
    assert {m.label: m.value for m in app.metric}["Open findings"] == "36"
    app.button(key="view-unusual_transaction").click().run()
    assert not app.exception
    assert app.selectbox(key="filter-kind").value == "unusual_transaction"
    candidate = app.dataframe[-1].value.iloc[0]
    assert candidate["source_row_number"] == 83
    assert candidate["evidence_role"] == "candidate"
    assert candidate["transaction_id"] == "499dde9a5b9ef93cbdf2c6e1e7a79883c25671ca34b54f7c391e5158d15958f0"
    app.radio[0].set_value("synthetic").run()
    app.selectbox(key="filter-kind").set_value("price_increase").run()
    assert not app.exception
    assert app.code[0].value == RECURRING_ID
    assert app.dataframe[-1].value.source_row_number.tolist() == [5, 2, 3, 4]
    for page in ("Transactions", "Suppliers", "Data Quality", "Dataset", "How SpendFlow Works", "Settings"):
        next(button for button in app.button if button.label == page).click().run()
        assert not app.exception
        assert app.title[0].value == page
    next(button for button in app.button if button.label == "AI Investigation").click().run()
    assert not app.exception
    assert any("Optional AI assistant unavailable" in item.value for item in app.info)
