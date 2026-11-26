# Groundability report

6 supported, 2 partial, 1 unsupported (groundable fraction 78%). Unsupported topics will be REFUSED by the agent instead of answered: live shipment status.

| Topic | Verdict | Evidence | Note |
|---|---|---|---|
| part number | partial (guard) | supplier_terms_poseidon.pdf#2 | guard: model said 'supported' without citing; excerpt supplier_terms_poseidon.pdf#2 contains the topic, so kept as partial. none |
| price | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: part, price) |
| stock quantity | supported | spares_catalogue.csv:columns | computed from spares_catalogue.csv columns with the calculator tool |
| lead time | supported | spares_catalogue.csv:columns | computed from spares_catalogue.csv columns with the current_date tool |
| order total | supported | spares_catalogue.csv:columns | computed from spares_catalogue.csv columns with the calculator tool |
| supplier terms | partial (guard) | supplier_terms_nordmarine.pdf#0 | guard: model said 'supported' without citing; excerpt supplier_terms_nordmarine.pdf#0 contains the topic, so kept as partial. none |
| approval rules | supported | procurement_policy.pdf#1, procurement_policy.pdf#0 | none |
| estimated delivery date | supported | spares_catalogue.csv:columns | computed from spares_catalogue.csv columns with the current_date tool |
| live shipment status | unsupported | - | live shipment status |

## Flagged gaps
The brief asks for these but the documents cannot support them. The agent is configured to refuse them rather than guess:
- live shipment status
