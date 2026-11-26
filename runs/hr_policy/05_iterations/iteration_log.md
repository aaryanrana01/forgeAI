# Critic-optimizer iteration log

## Iteration 1 - reverted (dev score did not improve)
Dev pass-rate 67% -> 67%; holdout 67% -> 67%; overall 67% -> 67%. Tokens spent: 33,356.

Dev failures going in: {'prompt_defect': 2, 'wrong_refusal': 2, 'retrieval_miss': 1}
- **P1 [wrong_refusal] must_refuse_topics** - agent answered questions on topics it must refuse  
  addresses: oos-15, oos-16  
  before: `['salary bands and payroll dates', 'payroll calendar']`  
  after: `['salary bands and payroll dates', 'payroll calendar', 'leave policy', 'working from home']`
- **P2 [prompt_defect] prompt.answering_rules** - The prompt is missing facts from the provided documents, leading to incomplete or incorrect answers.  
  addresses: ans-10, x-11  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Use additional relevant facts from the documents when two documents are relevant, combine them.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the con ...`
