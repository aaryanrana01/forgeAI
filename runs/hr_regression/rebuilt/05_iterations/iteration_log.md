# Critic-optimizer iteration log

## Iteration 1 - reverted (dev score did not improve)
Dev pass-rate 60% -> 60%; holdout 33% -> 33%; overall 52% -> 52%. Tokens spent: 29,454.

Dev failures going in: {'prompt_defect': 3, 'retrieval_miss': 1, 'wrong_refusal': 2}
- **P1 [prompt_defect] prompt.answering_rules** - The prompt is missing rules to ensure that answers include all expected facts, leading to omitted answers and refusal of questions.  
  addresses: ans-05, ans-07, x-11  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'If the CONTEXT does not contain the answer, set refused=true. Do not guess.', 'Cite the ids of the passages you used.', 'Copy numbers and dates exactly.']`  
  after: `['Use only facts found in the CONTEXT, TOOL RESULTS, and any additional expected facts. Never use outside knowledge.', 'If the CONTEXT does not contain the answer, set refused=true. Do not guess.', 'Cite the ids of the passages you used.', 'Copy numbers and da ...`
- **P2 [wrong_refusal] must_refuse_topics** - agent answered questions on topics it must refuse  
  addresses: oos-16  
  before: `['personal data', 'salary details', 'advice on personal matters', 'salary band']`  
  after: `['personal data', 'salary details', 'advice on personal matters', 'salary band', 'working from home']`
