# Critic-optimizer iteration log

## Iteration 1 - reverted (dev score did not improve)
Dev pass-rate 60% -> 60%; holdout 83% -> 100%; overall 67% -> 71%. Tokens spent: 41,348.

Dev failures going in: {'wrong_refusal': 4, 'prompt_defect': 2}
- **P1 [wrong_refusal] must_refuse_topics** - agent answered questions on topics it must refuse  
  addresses: oos-15, oos-16  
  before: `['salary band', 'payroll dates', 'personal data']`  
  after: `['salary band', 'payroll dates', 'personal data', 'leave', 'working from home']`
- **P2 [prompt_defect] prompt.answering_rules** - The common cause for the failures is that the assistant is missing expected facts in the answer and is unable to provide the necessary context to fully address the user's questions.  
  addresses: x-11, amb-17  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`
- now passing: amb-18
