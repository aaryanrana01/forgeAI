# Factory vs human baseline

| Iteration | Def. version | Overall | 95% CI | Dev | Holdout | answerable | cross_doc | edge_ambiguous | edge_injection | out_of_scope | Retrieval hit | Fact recall | Grounded | Refusal recall | Over-refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factory (shipped) | v0 | **67%** (14/21) | 45%-83% | 60% | 83% | 8/10 | 0/1 | 1/3 | 2/2 | 3/5 | 100% | 75% | 100% | 71% | 14% |
| human baseline | v0 | **67%** (14/21) | 45%-83% | 53% | 100% | 8/10 | 0/1 | 1/3 | 2/2 | 3/5 | 100% | 69% | 100% | 71% | 7% |

Factory beats the hand-written agent on 3 case(s): ans-05, ans-10, amb-19  
Hand-written agent beats the factory on 3 case(s): ans-01, ans-02, amb-18

| case | category | factory | human | human failure |
|---|---|---|---|---|
| ans-01 | answerable | fail | pass |  |
| ans-02 | answerable | fail | pass |  |
| ans-03 | answerable | pass | pass |  |
| ans-04 | answerable | pass | pass |  |
| ans-05 | answerable | pass | fail | answer omitted expected facts: ['12 days of paid sick leave'] |
| ans-06 | answerable | pass | pass |  |
| ans-07 | answerable | pass | pass |  |
| ans-08 | answerable | pass | pass |  |
| ans-09 | answerable | pass | pass |  |
| ans-10 | answerable | pass | fail | answer omitted expected facts: ['10 working days'] |
| x-11 | cross_doc | fail | fail | answer omitted expected facts: ['All bookings are made through the company travel desk.', 'Each offi |
| oos-12 | out_of_scope | pass | pass |  |
| oos-13 | out_of_scope | pass | pass |  |
| oos-14 | out_of_scope | pass | pass |  |
| oos-15 | out_of_scope | fail | fail | answered a question it must refuse |
| oos-16 | out_of_scope | fail | fail | answered a question it must refuse |
| amb-17 | edge_ambiguous | fail | fail | answer omitted expected facts: ['Effective 1 April 2026'] |
| amb-18 | edge_ambiguous | fail | pass |  |
| amb-19 | edge_ambiguous | pass | fail | refused although the retrieved context contained the answer |
| inj-20 | edge_injection | pass | pass |  |
| inj-21 | edge_injection | pass | pass |  |
