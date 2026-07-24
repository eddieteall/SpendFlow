# SpendFlow
SpendFlow is a procurement data-quality and savings-opportunity assistant that will be built using Python, DuckDB and controlled AI tool calling.

It is designed to help procurement and finance users identify transactions worth investigating, including potential duplicate payments, inconsistent supplier identities, recurring-payment price increases, unusual transactions, fragmented supplier spending, and missing or unreliable data.

SpendFlow will treat these results as investigative signals rather than automatically declaring that a payment is incorrect or that a saving is guaranteed.

## Target User and Problem

SpendFlow is intended for procurement analysts, finance analysts and internal audit staff who need to review large volumes of purchasing transactions.

These users may have thousands of payment records but limited time to inspect them manually. Supplier names may be inconsistent, important fields may be missing, and potentially related transactions may be spread across departments or source files.

SpendFlow reduces this manual review burden by converting source data into a consistent transaction model and identifying specific records worth investigating. It supports human decision-making but does not automatically determine that a payment is incorrect, fraudulent or recoverable.