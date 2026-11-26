# Critic-optimizer iteration log

## Iteration 1 - reverted (dev score did not improve)
Dev pass-rate 64% -> 64%; holdout 100% -> 100%; overall 75% -> 75%. Tokens spent: 34,622.

Dev failures going in: {'wrong_refusal': 4, 'hallucination': 1}
- **P1 [wrong_refusal] must_refuse_topics** - agent answered questions on topics it must refuse  
  addresses: oos-14, oos-15  
  before: `['salary band', 'payroll dates', 'personal data']`  
  after: `['salary band', 'payroll dates', 'personal data', 'leave', 'working from home']`
- **P2 [hallucination] prompt.answering_rules** - answers contained values/claims absent from the evidence: only 50% of claims supported by evidence  
  addresses: amb-16  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`
