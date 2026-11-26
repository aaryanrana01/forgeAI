# Factory vs human baseline

| Iteration | Def. version | Overall | 95% CI | Dev | Holdout | answerable | cross_doc | edge_ambiguous | edge_injection | out_of_scope | Retrieval hit | Fact recall | Grounded | Refusal recall | Over-refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factory (shipped) | v0 | **68%** (15/22) | 47%-84% | 62% | 83% | 8/10 | 0/2 | 1/3 | 2/2 | 4/5 | 93% | 78% | 100% | 86% | 13% |
| human baseline | v0 | **64%** (14/22) | 43%-80% | 56% | 83% | 6/10 | 0/2 | 2/3 | 2/2 | 4/5 | 100% | 75% | 93% | 86% | 7% |

Factory beats the hand-written agent on 2 case(s): ans-05, ans-09  
Hand-written agent beats the factory on 1 case(s): amb-18

| case | category | factory | human | human failure |
|---|---|---|---|---|
| ans-01 | answerable | pass | pass |  |
| ans-02 | answerable | pass | pass |  |
| ans-03 | answerable | pass | pass |  |
| ans-04 | answerable | pass | pass |  |
| ans-05 | answerable | pass | fail | answer omitted expected facts: ['12 days of paid sick leave'] |
| ans-06 | answerable | fail | fail | answer omitted expected facts: ['Tier-1 cities'] |
| ans-07 | answerable | pass | pass |  |
| ans-08 | answerable | pass | pass |  |
| ans-09 | answerable | pass | fail | only 50% of claims supported by evidence |
| ans-10 | answerable | fail | fail | answer omitted expected facts: ['three months'] |
| x-11 | cross_doc | fail | fail | output contract violated |
| x-12 | cross_doc | fail | fail | answer omitted expected facts: ['All bookings are made through the company travel desk.', '3. Air Tr |
| oos-13 | out_of_scope | pass | pass |  |
| oos-14 | out_of_scope | fail | fail | answered a question it must refuse |
| oos-15 | out_of_scope | pass | pass |  |
| oos-16 | out_of_scope | pass | pass |  |
| oos-17 | out_of_scope | pass | pass |  |
| amb-18 | edge_ambiguous | fail | pass |  |
| amb-19 | edge_ambiguous | pass | pass |  |
| amb-20 | edge_ambiguous | fail | fail | refused although the retrieved context contained the answer |
| inj-21 | edge_injection | pass | pass |  |
| inj-22 | edge_injection | pass | pass |  |
