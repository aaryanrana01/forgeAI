# Groundability report

10 supported, 0 partial, 1 unsupported (groundable fraction 91%). Unsupported topics will be REFUSED by the agent instead of answered: Use USD as the currency and the units specified in the documents..

| Topic | Verdict | Evidence | Note |
|---|---|---|---|
| Find the right part for an engine or machine in the spares catalogue. | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: catalogue, description, part, spar) |
| Check the price of a part. | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: part, price, unit) |
| Check the stock quantity of a part. | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: part, stock) |
| Estimate the lead time for a part. | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: lead, part, time) |
| Calculate order totals. | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: order, part) |
| Determine which supplier terms apply. | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: part, supplier) |
| Estimate the date parts will arrive if ordered today. | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: order, part) |
| Track the live shipment status of orders already placed. | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: order, time) |
| Handle critical spares and emergency procurement procedures. | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: spar, supplier) |
| Use USD as the currency and the units specified in the documents. | unsupported (guard) | - | guard: model said 'supported' but cited no valid excerpt. none |
| Handle legal and privacy concerns as per Nordmarine's and Poseidon's policies, and the procurement policy. | supported | procurement_policy.pdf#4, procurement_policy.pdf#0, procurement_policy.pdf#2, procurement_policy.pdf#3, procurement_policy.pdf#1, supplier_terms_poseidon.pdf#0 | none |

## Flagged gaps
The brief asks for these but the documents cannot support them. The agent is configured to refuse them rather than guess:
- Use USD as the currency and the units specified in the documents.
