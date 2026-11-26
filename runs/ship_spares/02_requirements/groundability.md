# Groundability report

5 supported, 2 partial, 0 unsupported (groundable fraction 86%).

| Topic | Verdict | Evidence | Note |
|---|---|---|---|
| part number lookup | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: catalogue, part, spar) |
| price inquiry | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: part, price) |
| stock availability | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: part, stock) |
| lead time inquiry | supported | spares_catalogue.csv:columns | answerable from table spares_catalogue.csv (columns matching: lead, part) |
| order total calculation | supported | spares_catalogue.csv:columns | computed from spares_catalogue.csv columns with the calculator tool |
| supplier terms | partial | procurement_policy.pdf#1, supplier_terms_nordmarine.pdf#2, supplier_terms_poseidon.pdf#1, supplier_terms_poseidon.pdf#2 | 3. Approval Rules, 4. Delivery Terms, 5. Expedited Dispatch, 6. Warranty |
| order status | partial | procurement_policy.pdf#0, procurement_policy.pdf#1, procurement_policy.pdf#2, supplier_terms_poseidon.pdf#0, supplier_terms_poseidon.pdf#1, supplier_terms_nordmarine.pdf#0 | order status, delivery times, and payment terms not specified in the provided excerpts |
