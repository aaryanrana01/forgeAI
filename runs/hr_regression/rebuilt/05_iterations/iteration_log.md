# Critic-optimizer iteration log

## Iteration 1 - kept
Dev pass-rate 71% -> 79%; holdout 67% -> 50%; overall 70% -> 70%. Tokens spent: 36,102.

Dev failures going in: {'prompt_defect': 2, 'wrong_refusal': 1, 'retrieval_miss': 1}
- **P1 [prompt_defect] prompt.answering_rules** - The current answering rules do not account for the need to provide specific facts such as days of leave for new joiners, leading to omitted answers.  
  addresses: ans-05, ans-10  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS', 'Cite the ids of the passages used', 'If the context does not contain the answer, refuse instead of guessing', 'Copy  ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS', 'Cite the ids of the passages used', 'If the context does not contain the answer, refuse instead of guessing', 'Copy  ...`
- **P2 [retrieval_miss] retrieval** - query_expansion: dev retrieval hit-rate 89% -> 100% (measured over 9 dev cases, 8 variants tried)  
  addresses: amb-16  
  before: `{'chunk_size': 120, 'chunk_overlap': 24, 'prepend_headings': True, 'top_k': 5, 'mode': 'bm25', 'query_expansion': False, 'min_relevance': 0.0}`  
  after: `{'chunk_size': 120, 'chunk_overlap': 24, 'prepend_headings': True, 'top_k': 5, 'mode': 'bm25', 'query_expansion': True, 'min_relevance': 0.0}`
- now passing: amb-16
- newly failing: ans-04
- note: dev improved but holdout fell - possible overfitting to dev cases

## Iteration 2 - reverted (dev score did not improve)
Dev pass-rate 79% -> 71%; holdout 50% -> 50%; overall 70% -> 65%. Tokens spent: 34,818.

Dev failures going in: {'prompt_defect': 2, 'wrong_refusal': 1}
- **P3 [prompt_defect] prompt.answering_rules** - The current rules do not account for the need to provide specific facts about leave policies, leading to missing facts in the answers.  
  addresses: ans-05, ans-10  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS', 'Cite the ids of the passages used', 'If the context does not contain the answer, refuse instead of guessing', 'Copy  ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS', 'Cite the ids of the passages used', 'If the context does not contain the answer, refuse instead of guessing', 'Copy  ...`
- **P4 [wrong_refusal] must_refuse_topics** - agent answered questions on topics it must refuse  
  addresses: oos-15  
  before: `['salary bands and payroll dates', 'payroll calendar', 'tell employees their salary band']`  
  after: `['salary bands and payroll dates', 'payroll calendar', 'tell employees their salary band', 'leave policy, travel and expense policy, working from home, hybrid work and conduct policy']`
- now passing: ans-05
- newly failing: amb-16, oos-14
