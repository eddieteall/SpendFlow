"""Streamlit evidence review for the two demo snapshots."""

import os
from pathlib import Path

import duckdb
import streamlit as st

from spendflow.analysis.rules import CLASSIFICATIONS, TYPES
from spendflow.tools.agent import OpenAIProvider, investigate
from spendflow.tools.investigate import Investigation, PAGE_SIZE


def main():
    st.set_page_config(page_title="SpendFlow", layout="wide")
    st.title("SpendFlow investigation")
    dataset = st.sidebar.radio("Dataset", ("Public DfI • July 2026", "Synthetic • invented payments"))
    synthetic = dataset.startswith("Synthetic")
    name = "synthetic" if synthetic else "public"
    database = Path("data/processed") / f"{name}.duckdb"
    st.caption("Illustrative invented records." if synthetic else
               "Public spending above the publication threshold for one month. "
               "The source lacks payment-system, quantity and contract evidence.")
    if not database.is_file():
        st.info(f"Database missing. Use the README load command for the {name} dataset.")
        return
    read = Investigation(database)
    try:
        info = read.overview()
    except duckdb.Error:
        st.error("This database has no readable SpendFlow snapshot. Load a fresh demo database.")
        return
    if info["sources"]:
        source = info["sources"][0]
        st.subheader(source["source_name"])
        st.caption(source["file_name"])
    columns = st.columns(2)
    columns[0].metric("Transactions", info["transactions"])
    columns[1].metric("Findings", sum(row["findings"] for row in info["finding_counts"]))
    if not info["transactions"]:
        st.info("No transactions are loaded. Source-level findings may explain why.")
    if info["finding_counts"]:
        st.dataframe(info["finding_counts"], hide_index=True)
    c1, c2 = st.columns(2)
    kind = c1.selectbox("Finding type", [None, *TYPES], format_func=lambda x: x or "All types")
    classification = c2.selectbox("Classification", [None, *CLASSIFICATIONS],
                                  format_func=lambda x: x or "All classifications")
    if kind == "price_increase":
        st.caption("This rule needs four comparable monthly invoices for the same described service. "
                   "Without that history, the available data cannot establish a recurring increase.")
    page_key = f"{name}:{kind}:{classification}"
    page = st.number_input("Finding page", min_value=1, max_value=201, step=1, key=page_key)
    result = read.list_findings(kind, classification, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    if result["findings"]:
        choices = {r["finding_id"]: f"{r['title']} · {r['finding_id'][:10]}" for r in result["findings"]}
        finding_id = st.selectbox("Open finding", list(choices), format_func=choices.get, key=f"{page_key}:{page}")
        details_page = st.number_input("Evidence page", min_value=1, max_value=201, step=1, key=finding_id)
        detail = read.get_finding(finding_id, PAGE_SIZE, (details_page - 1) * PAGE_SIZE)
        finding = detail["finding"]
        st.subheader(finding["title"])
        st.text(finding["description"])
        st.caption(f"{finding['finding_classification']} · {finding['rule_name']} v{finding['rule_version']}")
        st.code(finding_id)
        st.text(f"Source: {finding['file_name']}")
        st.json(finding["evidence"])
        if detail["transactions"]:
            st.dataframe([{key: str(value) if key == "amount" and value is not None else value
                           for key, value in row.items()} for row in detail["transactions"]], hide_index=True)
        else:
            st.info("No transaction references on this evidence page.")
        if detail["has_more"]:
            st.caption("More evidence on the next evidence page.")
    else:
        st.info("No findings match this page and filter.")
    if result["has_more"]:
        st.caption("More findings on the next finding page.")
    st.subheader("Ask about the evidence")
    api_key, model = os.getenv("OPENAI_API_KEY"), os.getenv("SPENDFLOW_OPENAI_MODEL")
    if not api_key or not model:
        st.info("Optional AI assistant unavailable. Set OPENAI_API_KEY and SPENDFLOW_OPENAI_MODEL to enable it.")
    else:
        st.caption("Submitting a question sends it and the selected tool results to OpenAI.")
        with st.form("ask"):
            question = st.text_input("Question", max_chars=1500)
            submitted = st.form_submit_button("Investigate")
        if submitted and question.strip():
            try:
                answer = investigate(question, read, OpenAIProvider(api_key, model))
            except (OSError, ValueError, KeyError, IndexError, duckdb.Error):
                st.error("The optional assistant could not complete this request. You can still inspect the evidence above.")
            else:
                st.text(answer["answer"])
                st.caption("Tools called: " + (", ".join(answer["tools_called"]) or "none"))
                with st.expander("Retrieved evidence IDs"):
                    st.text("\n".join(answer["retrieved_ids"]))


main()
