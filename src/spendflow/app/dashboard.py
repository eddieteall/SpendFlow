"""Streamlit workspace for reviewing SpendFlow evidence."""

import os
from collections import defaultdict
from decimal import Decimal
from html import escape
from pathlib import Path
from urllib.parse import urlencode

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from spendflow.analysis.rules import CLASSIFICATIONS
from spendflow.app.views import DashboardData
from spendflow.tools.agent import OpenAIProvider, TOOLS, investigate
from spendflow.tools.investigate import PAGE_SIZE

DATASETS = {"public": "Public DfI • July 2026", "synthetic": "Synthetic • invented payments"}
PAGES = {
    "Overview": "dashboard", "Findings": "flag", "Transactions": "receipt_long",
    "Suppliers": "apartment", "Data Quality": "verified_user", "AI Investigation": "forum",
    "Dataset": "database", "How SpendFlow Works": "menu_book", "Settings": "settings",
}
FAMILIES = {
    "potential_duplicate": ("Potential duplicate payment", "Payments with matching indicators that warrant review.", "high"),
    "supplier_identity": ("Supplier identity", "Supplier names that may refer to the same organisation.", "medium"),
    "unusual_transaction": ("Unusual transaction", "Payments that stand out against comparable records.", "medium"),
    "price_increase": ("Recurring payment increase", "Comparable recurring payments where the amount rose.", "medium"),
    "fragmented_spend": ("Fragmented supplier spend", "Spend across departments that may warrant consolidation review.", "low"),
    "missing_data": ("Data quality", "Conditions observed directly in the source data.", "low"),
}
COLORS = {"high": "red", "medium": "amber", "low": "", "suspicious": "amber",
          "confirmed": "green", "possible_savings": "green",
          "accepted": "green", "proposed": "amber", "rejected": ""}


def label(value):
    return str(value).replace("_", " ").capitalize()


def text(value):
    return "—" if value is None or value == "" else escape(str(value))


def money(amount, currency):
    if amount is None:
        return "—"
    symbol = {"GBP": "£", "EUR": "€", "USD": "$"}.get(currency)
    return f"{symbol}{amount:,.2f}" if symbol else f"{amount:,.2f} {currency or ''}".strip()


def pill(value, caption=None, *, priority=False):
    classes = ["sf-pill", COLORS.get(value, "")]
    if priority:
        classes.append("priority")
    return f'<span class="{" ".join(classes)}">{text(caption or label(value))}</span>'


def heading(title, subtitle):
    st.title(title)
    st.html(f'<p class="sf-intro">{text(subtitle)}</p>')


def table(headers, records):
    """Render prepared cells. Callers escape all values from the database."""
    if not records:
        st.info("No records match this view.")
        return
    head = "".join(f"<th scope='col'>{text(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in records)
    st.html(f'<div class="sf-table-wrap"><table class="sf-table"><thead><tr>{head}</tr>'
            f'</thead><tbody>{body}</tbody></table></div>')


def page_number(key):
    return st.number_input("Page", 1, 201, step=1, key=f"page-{key}")


def page_rows(records):
    if len(records) > PAGE_SIZE:
        st.caption("More records are available on the next page.")
    return records[:PAGE_SIZE]


def choices(label_text, values, key, display=label, default=None):
    options = [None, *values]
    return st.selectbox(label_text, options, index=options.index(default) if default in options else 0,
                        format_func=lambda value: "All" if value is None else display(value), key=key)


def navigate(page, kind=None):
    st.session_state["page"] = page
    st.session_state["requested_kind"] = kind
    if "finding" in st.query_params:
        del st.query_params["finding"]


def sidebar(name, page):
    with st.sidebar:
        st.html('<div class="sf-brand"><span class="sf-mark" aria-hidden="true">↗</span>'
                '<div><strong>SpendFlow</strong><small>Procurement intelligence</small></div></div>')
        st.caption("Analysis")
        for index, (item, icon) in enumerate(PAGES.items()):
            if index == 6:
                st.divider()
            st.button(item, icon=f":material/{icon}:", width="stretch",
                      type="primary" if page == item else "secondary", on_click=navigate, args=(item,))
        st.divider()
        selected = st.radio("Dataset", list(DATASETS), index=list(DATASETS).index(name),
                            format_func=DATASETS.get)
        if selected != name:
            st.query_params["dataset"] = selected
            if "finding" in st.query_params:
                del st.query_params["finding"]
            st.rerun()


def overview(read, info):
    heading("Overview", "Review procurement activity and investigate signals from the selected dataset.")
    summary = read.summary()
    first = st.columns(2, gap="small")
    first[0].metric("Transactions", f"{info['transactions']:,}")
    first[1].metric("Suppliers", f"{summary['suppliers']:,}")
    second = st.columns(2, gap="small")
    second[0].metric("Open findings", f"{summary['open_findings']:,}")
    estimates = read.opportunity_values()
    second[1].metric("Possible opportunity value",
                     " · ".join(money(row["amount"], row["currency"]) for row in estimates) or "—",
                     help="Recorded estimates by currency. Estimated values do not represent guaranteed savings.")
    st.html('<div class="sf-section-heading"><h2>Findings requiring attention</h2>'
            '<span title="Priority indicates suggested review order by rule family">Grouped by detection rule</span></div>')
    counts = defaultdict(int)
    for finding in info["finding_counts"]:
        counts[finding["finding_type"]] += finding["findings"]
    for index, (kind, (title, description, priority)) in enumerate(FAMILIES.items()):
        if index % 2 == 0:
            columns = st.columns(2, gap="small")
        with columns[index % 2].container(border=True, key=f"sf-card-{kind}"):
            st.html(f'<div class="sf-card"><div class="sf-card-top"><strong>{title}</strong>'
                    f'{pill(priority, f"{priority.title()} priority", priority=True)}</div>'
                    f'<span class="sf-card-value">{counts[kind]:,}</span>'
                    f'<span class="sf-muted">{description}</span></div>')
            st.button("View findings", icon=":material/arrow_outward:", key=f"view-{kind}",
                      on_click=navigate, args=("Findings", kind))

    chart, review = st.columns([3, 2], gap="small")
    with chart.container(border=True, key="sf-panel-chart"):
        st.subheader("Monthly spending")
        st.caption("Eligible spend from the loaded dataset, grouped by month and currency.")
        months = pd.DataFrame(read.monthly_spend())
        if months.empty:
            st.info("No dated spending is available.")
        else:
            months["amount"] = months["amount"].astype(float)
            currency = st.selectbox("Currency", sorted(months["currency"].unique()), key="chart-currency")
            data = months[months["currency"] == currency]
            base = alt.Chart(data).encode(
                x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %Y", labelAngle=0)),
                y=alt.Y("amount:Q", title=currency, axis=alt.Axis(format="~s")),
                tooltip=[alt.Tooltip("month:T", format="%B %Y"), alt.Tooltip("amount:Q", format=",.2f")],
            )
            plot = (base.mark_bar(color="#207657", size=42) if len(data) == 1 else
                    base.mark_area(color="#207657", opacity=.14) +
                    base.mark_line(color="#207657", point=True))
            st.altair_chart(plot.properties(height=265), width="stretch")
    with review.container(border=True, key="sf-panel-priority"):
        st.subheader("Priority investigations")
        st.caption("Open findings ordered by suggested family priority.")
        shown = 0
        for kind in FAMILIES:
            for row in read.finding_register(kind, None, None, "open", None, "", 1)[:3 - shown]:
                with st.container(border=True, key=f"sf-panel-priority-{shown}"):
                    priority = FAMILIES[kind][2]
                    st.html(f'<div class="sf-card-top"><strong>{text(row["title"])}</strong>'
                            f'{pill(priority, f"{priority.title()} priority", priority=True)}</div>'
                            f'<span class="sf-muted">{text(row["supplier"])}</span>')
                    st.button("Review evidence", key=f'priority-{row["finding_id"]}',
                              on_click=open_finding, args=(row["finding_id"],))
                shown += 1
            if shown == 3:
                break
        if not shown:
            st.info("There are no open investigations.")


def open_finding(finding_id):
    navigate("Findings")
    st.query_params["finding"] = finding_id


def reset_findings():
    for key in list(st.session_state):
        if key.startswith("filter-") or key == "page-findings":
            del st.session_state[key]
    navigate("Findings")


def finding_link(row, name):
    url = escape("?" + urlencode({"dataset": name, "finding": row["finding_id"]}))
    return f'<a href="{url}">{text(row["title"])}</a><small>{text(row["finding_id"][:10])}</small>'


def findings(read, name):
    heading("Findings", "Records surfaced by deterministic rules for human review.")
    current = st.query_params.get("finding")
    if current and current != st.session_state.get("handled_finding"):
        for key in list(st.session_state):
            if key.startswith("filter-") or key == "page-findings":
                del st.session_state[key]
        st.session_state["handled_finding"] = current
    elif not current:
        st.session_state.pop("handled_finding", None)
    requested = st.session_state.pop("requested_kind", None)
    if requested:
        st.session_state["filter-kind"] = requested
        st.session_state["page-findings"] = 1
    options = read.finding_options()
    with st.container(border=True, key="sf-panel-register"):
        search, kind_col, class_col, reset = st.columns([3, 2, 2, 1], vertical_alignment="bottom")
        with search:
            term = st.text_input("Search findings", placeholder="Search findings, suppliers or rules", key="filter-search")
        with kind_col:
            kind = choices("Finding type", FAMILIES, "filter-kind", lambda value: FAMILIES[value][0])
        with class_col:
            classification = choices("Classification", CLASSIFICATIONS, "filter-class")
        with reset:
            st.button("Reset filters", on_click=reset_findings)
        columns = st.columns([2, 2, 3, 1.4], vertical_alignment="bottom")
        with columns[0]:
            severity = choices("Severity", sorted({row["severity"] for row in options}), "filter-severity")
        with columns[1]:
            status = choices("Status", sorted({row["status"] for row in options}), "filter-status")
        with columns[2]:
            suppliers = sorted({row["supplier_name_raw"] for row in read.transaction_options() if row["supplier_name_raw"]})
            supplier = choices("Supplier", suppliers, "filter-supplier", str)
        with columns[3]:
            page = page_number("findings")
        records = page_rows(read.finding_register(kind, classification, severity, status, supplier, term, page))
        table(("Finding", "Type", "Classification", "Supplier", "Value", "Severity", "Status", "Date"), [
            (finding_link(r, name),
             text(FAMILIES[r["finding_type"]][0]), pill(r["finding_classification"]), text(r["supplier"]),
             text(money(r["estimated_value"], r["currency"])), text(r["severity"] or "Unassigned"),
             pill(r["status"]), text(r["first_date"])) for r in records
        ])
    if current and current not in {r["finding_id"] for r in records}:
        try:
            result = read.get_finding(current)
        except ValueError:
            result = {}
        if "finding" in result:
            records.insert(0, result["finding"])
    if records:
        options = {r["finding_id"]: f'{r["title"]} · {r["finding_id"][:10]}' for r in records}
        ids = list(options)
        finding_id = st.selectbox("Open finding", ids, index=ids.index(current) if current in ids else 0,
                                  format_func=options.get, key=f"open-{name}-{current}")
        finding_detail(read, finding_id)


def finding_detail(read, finding_id):
    with st.container(border=True, key="sf-panel-evidence"):
        page = st.number_input("Evidence page", 1, 201, step=1, key=f"evidence-{finding_id}")
        detail = read.get_finding(finding_id, PAGE_SIZE, (page - 1) * PAGE_SIZE)
        finding = detail["finding"]
        st.subheader(finding["title"])
        st.html(pill(finding["finding_classification"]))
        st.text(finding["description"])
        st.caption(f'{finding["rule_name"]} v{finding["rule_version"]} · {finding["file_name"]}')
        st.code(finding_id)
        with st.expander("Rule evidence"):
            st.json(finding["evidence"])
        if detail["transactions"]:
            rows = [{**row, "amount": money(row["amount"], row["currency"])} for row in detail["transactions"]]
            st.dataframe(rows, hide_index=True, column_order=[
                "evidence_role", "source_row_number", "supplier_name_raw", "amount",
                "transaction_date", "invoice_reference", "file_name", "transaction_id",
                "description", "category", "department", "payment_reference", "buyer_name_raw", "currency",
            ])
        else:
            st.info("No linked transaction records on this evidence page.")
        if detail["has_more"]:
            st.caption("More evidence is available on the next evidence page.")


def transactions(read):
    heading("Transactions", "Canonical transactions with the original supplier names and CSV references.")
    departments = sorted({r["department"] for r in read.transaction_options() if r["department"]})
    with st.container(border=True, key="sf-panel-transactions"):
        columns = st.columns([3, 2, 2])
        term = columns[0].text_input("Search transactions", placeholder="Search supplier, description or transaction ID")
        with columns[1]:
            department = choices("Department", departments, "department", str)
        with columns[2]:
            linked = choices("Findings", [True, False], "linked", lambda v: "With findings" if v else "Without findings")
        rows = page_rows(read.transactions(term, department, linked, page_number("transactions")))
        table(("Date", "Supplier", "Description", "Department", "Amount", "Findings", "Source"), [
            (text(r["transaction_date"]), f'<strong>{text(r["supplier_name_raw"])}</strong>'
             f'<small>{text(r["transaction_id"][:10])}</small>', text(r["description"] or r["category"]),
             text(r["department"]), text(money(r["amount"], r["currency"])), pill("medium", str(r["finding_count"]))
             if r["finding_count"] else "0", f'{text(r["file_name"])}<small>Record {text(r["source_row_number"])}</small>')
            for r in rows
        ])


def suppliers(read):
    heading("Suppliers", "Spend by supplier and currency. Accepted aliases contribute to the canonical supplier total.")
    term = st.text_input("Search suppliers", placeholder="Search supplier name")
    rows = page_rows(read.suppliers(term, page_number("suppliers")))
    aliases = read.aliases()
    by_supplier = defaultdict(list)
    groups = defaultdict(list)
    for alias in aliases:
        by_supplier[alias["canonical_supplier_name"] or alias["supplier_name_raw"]].append(alias)
        groups[alias["supplier_name_normalised"]].append(alias)

    def alias_chip(alias):
        return pill(alias["review_status"], f'{alias["supplier_name_raw"]} · {label(alias["review_status"])}')

    table(("Supplier", "Total spend", "Transactions", "Known / proposed aliases", "Open findings"), [
        (f'<strong>{text(r["supplier_identity"])}</strong>', text(money(r["amount"], r["currency"])),
         text(r["transactions"]), " ".join(map(alias_chip, by_supplier[r["supplier_identity"]])) or "—",
         text(r["open_findings"])) for r in rows
    ])
    st.subheader("Supplier identity detail")
    if not groups:
        st.caption("This dataset has no supplier alias groups.")
    for index, (group, members) in enumerate(groups.items()):
        if index % 2 == 0:
            columns = st.columns(2, gap="small")
        with columns[index % 2].container(border=True, key=f"sf-panel-alias-{index}"):
            st.caption("Alias review group")
            st.markdown(f"**{text(group)}**")
            st.html(" ".join(map(alias_chip, members)))
    st.subheader("Fragmented spend")
    fragmented = read.list_findings("fragmented_spend", limit=6)["findings"]
    if not fragmented:
        st.caption("This dataset has no fragmented spend findings.")
    for index, row in enumerate(fragmented):
        if index % 3 == 0:
            columns = st.columns(3)
        with columns[index % 3].container(border=True, key=f"sf-panel-fragment-{index}"):
            finding = read.get_finding(row["finding_id"])["finding"]
            evidence = finding["evidence"]
            st.text(evidence["supplier"])
            breakdown = evidence["net_by_department"]
            st.caption(finding["description"])
            st.metric("Net spend across departments",
                      money(sum(Decimal(amount) for amount in breakdown.values()), evidence["currency"]))
            for department, amount in breakdown.items():
                st.text(f"{department} · {money(Decimal(amount), evidence['currency'])}")
            st.button("View evidence", key=f'fragment-{row["finding_id"]}', on_click=open_finding,
                      args=(row["finding_id"],))


def quality(read):
    heading("Data Quality", "Conditions demonstrated directly by the dataset and recorded during validation.")
    stats = read.quality()
    columns = st.columns(2, gap="small")
    for index, (key, title) in enumerate([
        ("suppliers", "Missing supplier"), ("descriptions", "Missing description"),
        ("amounts", "Missing or invalid amount"), ("dates", "Missing or invalid date"),
    ]):
        columns[index % 2].metric(title, f'{stats["total"] - stats[key]:,}')
    completeness, affected = st.columns([1, 2], gap="small")
    with completeness.container(border=True, key="sf-panel-completeness"):
        st.subheader("Dataset quality")
        fields = {"dates": "Transaction date", "suppliers": "Supplier", "descriptions": "Description",
                  "amounts": "Amount", "departments": "Department"}
        total = stats["total"]
        score = sum(stats[k] for k in fields) / (len(fields) * total) if total else None
        st.metric("Field completeness", f"{score:.1%}" if score is not None else "—")
        if total:
            for key, title in fields.items():
                rate = stats[key] / total
                st.progress(rate, text=f"{title} · {rate:.1%}")
        st.caption("Completeness measures populated fields. It does not assess accuracy.")
    with affected.container(border=True, key="sf-panel-affected"):
        st.subheader("Affected records")
        rows = page_rows(read.affected(page_number("quality")))
        table(("Source row", "Source file", "Issue", "Field", "Details"), [
            (text(r["source_row"]), text(r["file_name"]), text(r["title"]), text(r["field"]),
             text(r["description"]) + (f'<small>{text(r["raw_value"])}</small>' if r["raw_value"] else ""))
            for r in rows
        ])


def credentials():
    return os.getenv("OPENAI_API_KEY"), os.getenv("SPENDFLOW_OPENAI_MODEL")


def investigator(read, name):
    heading("SpendFlow Investigator", "Ask about findings using approved read-only analysis tools.")
    api_key, model = credentials()
    enabled = bool(api_key and model)
    question_key = f"question-{name}"
    main, side = st.columns([2.15, 1], gap="small")
    with side.container(border=True, key="sf-panel-suggestions"):
        st.subheader("Suggested questions")
        for index, prompt in enumerate((
            "Summarise the unusual transaction findings.",
            "What possible duplicate payments warrant review?",
            "Which findings relate to fragmented spending?",
            "What data quality issues appear in this dataset?",
        )):
            st.button(prompt, key=f"suggest-{index}", width="stretch",
                      on_click=lambda value=prompt: st.session_state.update({question_key: value}))
    with side.container(border=True, key="sf-panel-tools"):
        st.subheader("Approved read-only tools")
        for tool in TOOLS:
            st.text(tool["function"]["name"])
    with main.container(border=True, key="sf-panel-investigator"):
        st.chat_message("assistant").write("Ask what a finding means or which evidence you should review.")
        if not enabled:
            st.info("Optional AI assistant unavailable. Set OPENAI_API_KEY and SPENDFLOW_OPENAI_MODEL to enable it.")
        else:
            st.caption("Submitting sends your question and the selected tool results to OpenAI.")
        with st.form("ask"):
            question = st.text_input("Question", placeholder="Ask about a finding or supplier…",
                                     max_chars=1500, key=question_key)
            submitted = st.form_submit_button("Investigate", disabled=not enabled)
        if submitted and question.strip():
            try:
                with st.spinner("Reviewing evidence…"):
                    st.session_state[f"answer-{name}"] = investigate(question, read, OpenAIProvider(api_key, model))
            except (OSError, ValueError, KeyError, IndexError, duckdb.Error):
                st.session_state.pop(f"answer-{name}", None)
                st.error("The assistant could not complete this request. Evidence is available on the Findings page.")
        if answer := st.session_state.get(f"answer-{name}"):
            st.chat_message("assistant").text(answer["answer"])
            with st.expander("Retrieved evidence and tool calls"):
                st.text("\n".join(answer["retrieved_ids"]))
                st.caption(", ".join(answer["tools_called"]) or "No tools called")


def main():
    st.set_page_config(page_title="SpendFlow", layout="wide", initial_sidebar_state="expanded")
    st.html(Path(__file__).with_name("dashboard.css"))
    name = st.query_params.get("dataset", "public")
    if name not in DATASETS:
        name = "public"
    page = st.session_state.get("page", "Findings" if st.query_params.get("finding") else "Overview")
    sidebar(name, page)
    context = "Public spending · July 2026" if name == "public" else "Demo dataset · synthetic records"
    st.html(f'<div class="sf-bar"><span class="sf-dataset">Dataset: {text(DATASETS[name])}</span>'
            f'<span>{context}</span></div>')
    if page == "How SpendFlow Works":
        heading(page, "Follow a finding from its detection rule to the original source record.")
        for title, body in [
            ("1. Load and validate", "SpendFlow archives the input bytes, maps each CSV record and stores typed transactions and validation evidence in DuckDB."),
            ("2. Apply deterministic rules", "Each finding records its rule, classification and linked evidence."),
            ("3. Review the evidence", "Open a finding and compare the linked records. Use the file and record number to check the original CSV."),
        ]:
            with st.container(border=True):
                st.subheader(title)
                st.write(body)
        return
    if page == "Settings":
        heading(page, "Review this workspace’s dataset and assistant configuration.")
        st.write(f"Active dataset: {DATASETS[name]}")
        st.write("AI assistant configured." if all(credentials()) else "AI assistant credentials are not configured.")
        st.caption("Select a dataset from the sidebar. Assistant credentials are read from the launch environment.")
        return
    database = Path("data/processed") / f"{name}.duckdb"
    if not database.is_file():
        st.info(f"Database missing. Use the README load command for the {name} dataset.")
        return
    read = DashboardData(database)
    try:
        info = read.overview()
    except duckdb.Error:
        st.error("This database has no readable SpendFlow snapshot. Load a fresh demo database.")
        return
    if not info["transactions"]:
        st.info("No transactions are loaded. Source-level findings may explain why.")
    if page == "Dataset":
        heading(page, "Inspect the active snapshot and its original input.")
        st.metric("Transactions", f'{info["transactions"]:,}')
        if info["sources"]:
            source = info["sources"][0]
            st.subheader(source["source_name"])
            st.text(source["file_name"])
            st.caption("SHA-256")
            st.code(source["file_hash"])
            st.caption("Source references use CSV record numbers, beginning with the header as record 1.")
        return
    if page == "Overview":
        overview(read, info)
    elif page == "Findings":
        findings(read, name)
    elif page == "AI Investigation":
        investigator(read, name)
    else:
        {"Transactions": transactions, "Suppliers": suppliers, "Data Quality": quality}[page](read)


main()
