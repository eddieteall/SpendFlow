# SpendFlow Findings

## Purpose

A SpendFlow finding is an issue, anomaly or opportunity produced by deterministic Python or SQL analysis.

Transactions and findings are stored separately:

- a transaction represents a record derived from a source dataset;
- a finding represents an interpretation of one or more transactions;
- one transaction may support several findings;
- one finding may involve several transactions.

Findings help users decide what to investigate. They do not automatically prove that a payment is incorrect or that a financial saving will be achieved.

## Finding Classifications

Every finding must use one of the following classifications.

### Confirmed Finding

A confirmed finding is a fact that can be demonstrated directly from the available evidence.

Examples include:

- a required supplier name is missing;
- a transaction amount cannot be parsed;
- a source row appears more than once with exactly the same recorded values;
- a source file is missing an expected column.

A confirmed finding confirms the observed data condition. It does not necessarily confirm a business error.

For example, SpendFlow may confirm that two source rows are identical, but it cannot automatically confirm that the organisation paid an invoice twice. The rows may represent legitimate repeated payments or duplicated publication records.

### Suspicious Record

A suspicious record is a transaction or group of transactions that matches a defined detection rule but requires further investigation.

Examples include:

- two payments with similar suppliers, dates and amounts;
- a supplier name that closely resembles another supplier name;
- a transaction that is unusually large compared with similar transactions;
- an apparent recurring payment that increased substantially.

Suspicion must be based on recorded evidence and a documented rule. It must not be described as proof of fraud, overpayment or error.

### Possible Savings Opportunity

A possible savings opportunity is a finding where investigation could potentially reduce future costs or recover money.

Examples include:

- consolidating fragmented spending with one supplier;
- reviewing an apparent duplicate payment;
- challenging an unexplained recurring-price increase;
- negotiating improved terms where repeated purchases occur separately.

Any financial value attached to the finding is an estimate. It must not be described as guaranteed, recoverable or already achieved.

## Finding Types

### Potential Duplicate Payment

This finding identifies transactions that may represent the same underlying payment.

Possible matching evidence includes:

- the same or similar supplier name;
- the same amount;
- the same or nearby transaction dates;
- the same invoice or payment reference, when available;
- similar descriptions;
- records appearing in the same or related source files.

Public-spending data usually cannot prove that a duplicate payment occurred because invoice identifiers and payment-processing details may be absent.

The default classification should therefore be `suspicious`.

### Supplier Identity

This finding identifies supplier names that may refer to the same organisation.

Examples include:

- `ACME LTD`;
- `Acme Limited`;
- `Acme Ltd.`;
- a supplier name containing a spelling or formatting variation.

Normalisation may remove differences in capitalisation, punctuation and legal suffixes. Fuzzy matching may propose additional possible relationships.

A proposed supplier match remains suspicious until it is accepted through a documented rule or human review.

### Recurring-Price Increase

This finding identifies a sequence of apparently recurring payments where the amount increases.

Evidence may include:

- a repeated supplier;
- similar descriptions;
- a regular payment interval;
- an increase relative to earlier transactions.

A price increase is not automatically incorrect. It may result from inflation, increased quantities, contract changes or different services.

This feature requires sufficient transaction history and reliable recurring-payment identification.

### Unusual Transaction

This finding identifies a transaction that differs substantially from an appropriate comparison group.

Possible comparisons include:

- the supplier’s normal transaction values;
- transactions in the same category;
- transactions from the same buyer or department;
- historical values over a defined period.

An unusual transaction is not automatically erroneous. The finding should explain the comparison used and why the transaction was flagged.

### Fragmented Supplier Spending

This finding identifies spending that may be divided across:

- several aliases for the same supplier;
- multiple departments;
- many small transactions;
- similar suppliers or related purchasing categories.

Fragmented spending may indicate an opportunity for consolidation or negotiation.

It must not be assumed that consolidation is possible. Existing contracts, departmental requirements and supplier relationships may justify the fragmentation.

### Missing or Unreliable Data

This finding records data-quality problems such as:

- missing supplier names;
- missing transaction dates;
- invalid or unparseable amounts;
- absent expected columns;
- inconsistent date formats;
- unsupported currencies;
- incomplete descriptions;
- duplicate source rows;
- unexpected changes in a source file.

Where possible, incomplete records should be retained and clearly marked rather than silently removed.

## Evidence and Traceability Requirements

Every finding must include:

- a unique `finding_id`;
- a documented `finding_type`;
- a valid `finding_classification`;
- the deterministic rule that produced it;
- links to the supporting transaction records;
- a human-readable explanation;
- the time at which it was created.

Where applicable, a finding may also include:

- comparison transactions;
- confidence information;
- severity;
- an estimated financial value;
- review notes;
- a rule version.

A finding must remain traceable through:

```text
finding
    → canonical transaction
    → source file
    → original source row