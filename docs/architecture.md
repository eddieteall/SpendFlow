# SpendFlow Architecture

## Purpose

SpendFlow is a procurement data-quality and savings-opportunity assistant. It processes transaction data using deterministic Python and SQL, then allows a controlled AI agent to investigate the resulting findings through approved read-only tools.

The architecture is designed around a reusable canonical transaction model. UK public-spending CSV files will be the initial data source, but future datasets should be usable by adding a new source-specific mapping step rather than redesigning the complete system.

## Core Design Principles

1. Raw source files must be preserved unchanged.
2. Source-specific columns must be mapped into a canonical transaction schema.
3. Python and SQL must perform calculations, validation and detection logic.
4. The AI agent must not calculate findings independently.
5. The AI agent may only access approved, read-only Python tools.
6. Suspicious records must not be presented as confirmed errors.
7. Possible savings opportunities must not be presented as guaranteed savings.
8. Every finding should remain traceable to its original source file and transaction.

## High-Level Data Flow

1. **Acquire source data**  
   Download a UK public-spending CSV file and record where it came from.

2. **Preserve the raw file**  
   Store the downloaded file unchanged in the raw-data directory. Processing must never overwrite this file.

3. **Profile the source**  
   Inspect column names, data types, missing values, date formats and obvious quality problems.

4. **Map to the canonical model**  
   Convert source-specific columns into SpendFlow’s standard transaction fields.

5. **Validate and clean**  
   Use Python to standardise values, validate required fields and record data-quality issues.

6. **Load into DuckDB**  
   Store canonical transactions, source-file metadata, supplier aliases and findings in structured database tables.

7. **Run deterministic detection logic**  
   Use Python and SQL to identify duplicate-payment candidates, supplier-name inconsistencies, unusual transactions and other investigative signals.

8. **Store findings with evidence**  
   Save each finding with its category, explanation, supporting transaction references and confidence or severity information.

9. **Expose approved read-only tools**  
   Provide tested Python functions that allow the AI agent to query transactions, suppliers and stored findings without changing data.

10. **Investigate through the AI agent**  
    The agent selects approved tools, retrieves evidence and explains relevant findings to the user.

11. **Present results**  
    Display findings and supporting evidence in a simple Streamlit interface.

## Deterministic Processing and AI-Agent Boundary

### Deterministic Python and SQL Responsibilities

Python and SQL are responsible for:

- downloading and preserving source files;
- mapping source-specific columns into the canonical transaction model;
- validating required fields and data types;
- cleaning and normalising values;
- calculating metrics and summary statistics;
- detecting suspicious records using defined rules;
- storing findings and supporting evidence;
- returning reproducible query results.

Given the same input data and configuration, these components should produce the same output.

### AI-Agent Responsibilities

The AI agent may:

- interpret a user’s investigation question;
- select an approved read-only Python tool;
- retrieve transactions, suppliers and stored findings;
- summarise evidence in accessible language;
- suggest reasonable follow-up questions or investigative actions.

The AI agent must not:

- edit transactions, findings or source files;
- execute unrestricted SQL;
- invent missing evidence;
- independently calculate financial results;
- describe suspicious records as confirmed errors;
- describe estimated opportunities as guaranteed savings.

The agent’s role is to assist investigation, not to replace deterministic analysis or human judgement.

## Planned Technology Stack

- **Python**  
  Handles data ingestion, source-specific mapping, validation, cleaning, detection rules and approved agent tools.

- **pandas**  
  Reads and transforms CSV data before it is loaded into the database.

- **DuckDB**  
  Stores canonical transactions and findings and supports analytical SQL queries without requiring a separate database server.

- **SQL**  
  Produces reproducible summaries, comparisons and detection queries.

- **pytest**  
  Tests data transformations, validation rules, detection logic and approved tool functions.

- **Streamlit**  
  Provides a small interface for viewing findings and asking investigation questions.

- **AI model with controlled tool calling**  
  Interprets user questions and calls only approved, read-only Python functions. It does not directly access files or execute unrestricted SQL.

- **Git and GitHub**  
  Provide version control, issue tracking, branches and pull-request review.

- **GitHub Actions**  
  Runs automated checks such as tests when changes are pushed or reviewed.

The project will avoid unnecessary infrastructure such as cloud deployment, distributed processing, multiple agents or a separate database server during the MVP.

## Initial Repository Structure

```text
SpendFlow/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   └── findings.md
├── data/
│   ├── raw/
│   ├── processed/
│   └── synthetic/
├── src/
│   └── spendflow/
│       ├── ingestion/
│       ├── validation/
│       ├── mapping/
│       ├── analysis/
│       ├── tools/
│       └── app/
├── tests/
├── sql/
├── config/
├── .github/
│   └── workflows/
├── .gitignore
├── pyproject.toml
└── requirements.txt