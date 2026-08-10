# SpendFlow
SpendFlow is a procurement data-quality and savings-opportunity assistant that will be built using Python, DuckDB and controlled AI tool calling.

It is designed to help procurement and finance users identify transactions worth investigating, including potential duplicate payments, inconsistent supplier identities, recurring-payment price increases, unusual transactions, fragmented supplier spending, and missing or unreliable data.

SpendFlow will treat these results as investigative signals rather than automatically declaring that a payment is incorrect or that a saving is guaranteed.

## Target User and Problem

SpendFlow is intended for procurement analysts, finance analysts and internal audit staff who need to review large volumes of purchasing transactions.

These users may have thousands of payment records but limited time to inspect them manually. Supplier names may be inconsistent, important fields may be missing, and potentially related transactions may be spread across departments or source files.

SpendFlow reduces this manual review burden by converting source data into a consistent transaction model and identifying specific records worth investigating. It supports human decision-making but does not automatically determine that a payment is incorrect, fraudulent or recoverable.

## Decisions and Actions Supported

SpendFlow should help a procurement or finance user take actions such as:

1. **Review a potential duplicate payment**  
   Examine the linked transactions, then check the relevant invoices, purchase orders or payment-system records before deciding whether the payments are legitimate.

2. **Investigate inconsistent supplier identities**  
   Review supplier-name variations that may refer to the same organisation, accept or reject proposed aliases, and calculate combined supplier spending more accurately.

3. **Assess a possible savings opportunity**  
   Investigate recurring price increases or fragmented purchasing, then decide whether to contact the supplier, consolidate future purchases or begin a contract review.

SpendFlow supplies prioritised evidence for these actions. The final decision remains with the procurement or finance user.

## Minimum Viable Product

The SpendFlow MVP will:

1. import one UK public-spending CSV dataset;
2. preserve the original downloaded file unchanged;
3. map the source columns into the canonical transaction model;
4. validate records and identify missing or invalid values;
5. load canonical transactions into DuckDB;
6. use deterministic Python and SQL rules to identify:
   - potential duplicate-payment candidates;
   - inconsistent supplier names;
   - unusual transactions;
   - missing or unreliable data;
7. store each finding with supporting transaction evidence;
8. expose a small set of tested, read-only Python tools;
9. allow one AI agent to retrieve and explain stored findings;
10. present the results through a simple Streamlit interface.

The MVP is successful when a user can load the chosen dataset, inspect prioritised findings, trace each finding back to its source records, and ask the agent controlled investigation questions.

## Outside the MVP

The following features are intentionally excluded from the initial version:

- support for multiple unrelated public datasets;
- direct integration with company finance or procurement systems;
- automatic recovery of duplicate payments;
- automatic supplier merging without review;
- contract, purchase-order or invoice management;
- guaranteed savings calculations;
- advanced machine-learning anomaly detection;
- unrestricted natural-language SQL generation;
- write access for the AI agent;
- multiple cooperating AI agents;
- user accounts, permissions and authentication;
- cloud deployment and production-scale infrastructure;
- real-time data processing;
- mobile applications;
- comprehensive procurement dashboards.

These features may be considered after the core pipeline, findings model and controlled investigation workflow have been implemented and tested.

## Use and Limitations of Public-Spending Data

SpendFlow will initially use a UK public-spending CSV dataset as an accessible source of real transaction data.

The dataset will be used to demonstrate:

- downloading and preserving source files;
- profiling unfamiliar CSV data;
- mapping source-specific columns into the canonical transaction model;
- validating missing, invalid or inconsistent values;
- grouping and analysing supplier spending;
- generating records for further investigation.

Public-spending data has important limitations:

- column names and formats vary between publishers;
- supplier names may be incomplete or inconsistent;
- transaction descriptions may be vague or missing;
- invoice numbers and payment references are often unavailable;
- purchase orders, contracts and quantities are usually unavailable;
- published dates may not represent the exact invoice or payment date;
- repeated rows may be publication duplicates rather than duplicate payments;
- amounts may include adjustments, credits, tax or aggregated payments;
- datasets may contain reporting errors or delayed corrections;
- public records normally do not show whether an opportunity produced an actual saving.

SpendFlow can therefore identify patterns and suspicious records, but public data alone will rarely confirm the underlying business cause.

Stronger testing of duplicate payments, recurring-payment price increases, supplier identity matching and realised savings will use clearly labelled synthetic data with known expected outcomes.
