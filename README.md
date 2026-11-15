# SpendFlow

SpendFlow loads procurement CSVs into DuckDB and flags records worth investigating. Each finding shows the rule that triggered it and links to the transactions and original CSV records. The Streamlit demo works without credentials.

## Run the demo

From the repository root with Python 3.13, run these commands in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m spendflow.load --dataset public --db data/processed/public.duckdb
.\.venv\Scripts\python.exe -m spendflow.load --dataset synthetic --db data/processed/synthetic.duckdb --alias-reviews data/synthetic-alias-reviews.json
.\.venv\Scripts\python.exe -m streamlit run src/spendflow/app/dashboard.py --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
```

On Linux or macOS, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`. Open [the local demo](http://127.0.0.1:8501). Load either dataset on its own or switch between them using the sidebar.

| Demo | Transactions | Findings |
| --- | ---: | ---: |
| Public: OpenDataNI, DfI July 2026 | 292 | 36 unusual transaction signals |
| Synthetic: invented records and reviewed alias examples | 23 | 11 findings across all six classes |

Run the load commands twice to verify the same IDs and counts. The public CSV at record 2 has date `2026-07-01` and amount `336631.50 GBP`. Its Git blob and archived input share SHA-256 `5d77ab3552991b2558b3988a3e953013bcca57aa09ac437becf4016fb44c18ab`.

## How the data gets there

```text
CSV → unchanged archive + source metadata → canonical mapping and validation
    → DuckDB transactions, findings and evidence → read-only tools → Streamlit
```

The pipeline reuses the original source registration and DfI mapper. The CSV reader preserves Windows-1252 text, quoted records, leading zero references, empty cells and the distinction between a blank and an absent field on a short record. Pandas standardises buyer and supplier names in the pipeline; raw values remain available. A source row number counts CSV records, with the header as 1. Blank lines are skipped; a quoted multiline cell does not take extra record numbers. Git is configured to preserve the bundled public CSV's exact bytes on checkout.

Each database contains a single input and configuration snapshot. The source ID derives from its mapping and complete file hash; transaction IDs still derive from source ID, source record number and raw record hash. New source IDs are reproducible across clean checkouts. A rerun with the same snapshot preserves the stored timestamps, IDs and links. A different input or alias configuration needs a new database path. Use `--input path/to/file.csv` with the matching dataset schema to specify an alternate input. The loader stores related records in one transaction. Missing headers or unreadable CSV syntax record source-level evidence and give a nonzero exit code. Individual invalid values are retained as evidence, with a null typed value where parsing fails.

The original file is archived beside the database under `sources/`. Use the UI's file name and record number to trace a finding. See the [data contract](docs/data-contract.md), [data model](docs/data-model.md), and [architecture](docs/architecture.md).

## Rules and limits

See [rule thresholds and evidence](docs/findings.md#implemented-rules-v1). A confirmed finding establishes an observed data condition. A suspicious finding is a candidate for review. A possible savings finding suggests a question to investigate; it carries no estimated saving.

The public file covers one month and spending above a publication threshold. Invoice numbers repeat, but that alone does not indicate duplicate payments. The public data lacks payment references, service descriptions, quantities and contract terms. There is insufficient evidence for the recurring-payment rule in this file. The synthetic file illustrates known test cases and says nothing about the public organisation's spending.

## Optional AI investigation

Set `OPENAI_API_KEY` and `SPENDFLOW_OPENAI_MODEL` in your environment before starting Streamlit to enable the optional assistant. Choose a model in your account that supports [Chat Completions function calling](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create). Submit questions only for data you are authorised to share with the provider.

| Allowed tool | Inputs | Returns |
| --- | --- | --- |
| `list_findings` | Optional finding type, classification, limit and offset | Matching finding IDs and titles |
| `get_finding` | Finding ID, optional limit and offset | Rule, explanation, source and linked transactions |
| `compare_records` | Finding ID | Stored statistics and record amounts grouped by role and currency |
| `supplier_spend` | Exact raw or accepted canonical name and currency | Net spend and count in that currency |

Only tool results supply database information to the model. The tool layer validates arguments, uses fixed parameterised queries and opens DuckDB in read-only mode with external access disabled. The agent cannot choose a database path or run SQL, shell commands or file operations. Finance calculations come from deterministic code; verify the assistant's wording against the evidence shown. The test suite uses a fake provider for tool dispatch and checks the database hash is unchanged.

## Three-minute interview demo

1. **0:00–0:45 — Load the public file.** Run the public load command. Point out the 292 records and SHA-256. Explain that the pipeline preserves the original bytes and separates the raw values from typed dates and decimal money.
2. **0:45–1:45 — Trace the first public finding.** In Streamlit, select Public DfI and open `01e4ad5f3b…`. The candidate is record 83: `TRANSLINK*GRANTEE`, GBP 7,500,000.00 on 10 July 2026. Open the original CSV at record 83 and match reference `ERS-DFI-EF00573782-ERS-1184`. The median of seven other payments in that buyer/category/currency group is GBP 1,015,576.50. The payment clears the three-times threshold; the result is a review signal.
3. **1:45–3:00 — Explain the history requirement.** Switch to Synthetic and select `price_increase`. Records 2–4 establish a GBP 100.00 baseline, and record 5 is GBP 130.00. Point to the matching service description, dates and different references. The amount paid rose GBP 30.00 (30%). To infer a unit price change, ask for quantity and contract evidence. The public one-month file cannot support this test.

The audit baseline already contained the raw public CSV, source registry and hashing, DfI mapping and ID algorithm, documentation, and ten tests. The feature branch extends that work with pandas standardisation, DuckDB snapshots, the six rule classes, labelled fixtures, evidence tools, Streamlit, the optional provider and integration tests.
