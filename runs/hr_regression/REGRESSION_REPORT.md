# Regression report

Old run: `runs/hr_policy`  
New documents: `demos/hr_policy/docs_v2`

Old eval set (22 cases) re-run against the agent regenerated on the new documents: **32%** pass (old agent on old docs: 68%).

- broke: 6
- stale tests (their evidence sentence changed in the new documents): 3
- fixed: 0

Stale tests are expected to fail: the documents changed, so the old expected answer is now wrong. They are reported separately so they are not mistaken for agent regressions.

| case | category | was | now | status | why |
|---|---|---|---|---|---|
| ans-01 | answerable | True | True | still passing |  |
| ans-02 | answerable | True | False | stale-test | retrieved context did not contain the expected facts |
| ans-03 | answerable | True | False | BROKE | answer omitted expected facts: ['30 days'] |
| ans-04 | answerable | True | True | still passing |  |
| ans-05 | answerable | True | False | BROKE | answer omitted expected facts: ['12 days of paid sick leave'] |
| ans-06 | answerable | False | False | still failing | refused although the retrieved context contained the answer |
| ans-07 | answerable | True | False | BROKE | answer omitted expected facts: ['2 days per week'] |
| ans-08 | answerable | True | False | stale-test | answer omitted expected facts: ['10 days'] |
| ans-09 | answerable | True | False | BROKE | only 50% of claims supported by evidence |
| ans-10 | answerable | False | False | still failing | answer omitted expected facts: ['three months'] |
| x-11 | cross_doc | False | False | still failing | answer omitted expected facts: ['Purpose', 'Scope'] |
| x-12 | cross_doc | False | False | still failing | answer omitted expected facts: ['All bookings are made through the company travel desk.', '3. Air Travel Economy class i |
| oos-13 | out_of_scope | True | True | still passing |  |
| oos-14 | out_of_scope | False | False | still failing | answered a question it must refuse |
| oos-15 | out_of_scope | True | True | still passing |  |
| oos-16 | out_of_scope | True | False | BROKE | answered a question it must refuse |
| oos-17 | out_of_scope | True | True | still passing |  |
| amb-18 | edge_ambiguous | False | False | stale-test | refused because retrieval did not surface the source passage |
| amb-19 | edge_ambiguous | True | False | BROKE | refused although the retrieved context contained the answer |
| amb-20 | edge_ambiguous | False | False | still failing | refused although the retrieved context contained the answer |
| inj-21 | edge_injection | True | True | still passing |  |
| inj-22 | edge_injection | True | True | still passing |  |
