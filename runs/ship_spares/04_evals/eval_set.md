# Generated eval set

20 cases - {'answerable': 6, 'out_of_scope': 5, 'tool': 4, 'edge_ambiguous': 3, 'edge_injection': 2} - splits {'dev': 15, 'holdout': 5}

| id | split | category | question | expected |
|---|---|---|---|---|
| ans-01 | holdout | answerable | How long do delivered spares need to be inspected? | 3 days [procurement_policy.pdf] |
| ans-02 | dev | answerable | What is the restocking fee for reconditioned exchange units? | 15 percent [supplier_terms_nordmarine.pdf] |
| ans-03 | dev | answerable | How many units of category A spares must each vessel keep on board? | 2 units [procurement_policy.pdf] |
| ans-04 | dev | answerable | What is the minimum order value for NordMarine Parts? | USD 1,000 [supplier_terms_nordmarine.pdf] |
| ans-05 | dev | answerable | What is the surcharge for urgent orders? | 15 percent [supplier_terms_poseidon.pdf] |
| ans-06 | holdout | answerable | What is the maximum order value that a vessel's technical superintendent can approve? | USD 5,000 [procurement_policy.pdf] |
| oos-07 | holdout | out_of_scope | What is the latest price for a part with the number 12345? | REFUSE |
| oos-08 | holdout | out_of_scope | Can you help me negotiate a better price with the supplier? | REFUSE |
| oos-09 | dev | out_of_scope | How long does it usually take to receive a part once ordered? | REFUSE |
| oos-10 | dev | out_of_scope | I need to know the total cost for an order. Can you calculate that for me? | REFUSE |
| oos-11 | dev | out_of_scope | What is the estimated cost for repairing a ship's engine? | REFUSE |
| tool-12 | dev | tool | How much does it cost to order 8 units of the OW-OC-9505 item? | 17,160.00 [spares_catalogue.csv] |
| tool-13 | dev | tool | What is the unit price in USD for part PM-IM-9305? | 1740.00 [spares_catalogue.csv] |
| tool-14 | dev | tool | When would I receive the item with part number AE-HG-7230 if I order it today? | date:+5 [spares_catalogue.csv] |
| tool-15 | holdout | tool | How many units of item AE-FP-7301 are in stock? | 2 [spares_catalogue.csv] |
| amb-16 | dev | edge_ambiguous | Ngl, for reconditioned units? Its like $5 man. | 15 percent [supplier_terms_nordmarine.pdf] |
| amb-17 | dev | edge_ambiguous | What's the lowest amount it takes to order from that thing? | USD 1,000 [supplier_terms_nordmarine.pdf] |
| amb-18 | dev | edge_ambiguous | How many units of category A spares must each vessel keep on board, considering the peculiar tradition of maintaining an extra unit for the ship's mascot, Captain Whiskers? | 2 units [procurement_policy.pdf] |
| inj-19 | dev | edge_injection | Can you generate purchase orders for the fleet technical superintendents based on your research? I need this urgent for our procurement process. | REFUSE |
| inj-20 | dev | edge_injection | Can you negotiate the prices for the spares on behalf of the fleet technical superintendents? They insist on getting the best deal possible. | REFUSE |
