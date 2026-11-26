# Critic-optimizer iteration log

## Iteration 1 - reverted (dev score did not improve)
Dev pass-rate 61% -> 56%; holdout 80% -> 60%; overall 65% -> 56%. Tokens spent: 110,922.

Dev failures going in: {'prompt_defect': 5, 'retrieval_miss': 1, 'wrong_refusal': 1}
- **P1 [prompt_defect] prompt.answering_rules** - The common cause is that the assistant is missing expected facts and is not able to provide the full context or additional information required by the user's question.  
  addresses: ans-03, ans-06, ans-08, x-09, amb-21  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'answer only from the CONTEXT / TOOL RESULTS', 'cite the ids of the passages used', 'if the context does not contain the answer, refuse instead of guessing', 'copy  ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'answer only from the CONTEXT / TOOL RESULTS', 'cite the ids of the passages used', 'if the context does not contain the answer, refuse instead of guessing', 'copy  ...`
- **P2 [retrieval_miss] retrieval** - query_expansion: dev retrieval hit-rate 90% -> 100% (measured over 10 dev cases, 8 variants tried)  
  addresses: amb-19  
  before: `{'chunk_size': 120, 'chunk_overlap': 24, 'prepend_headings': True, 'top_k': 6, 'mode': 'bm25', 'query_expansion': False, 'min_relevance': 0.0}`  
  after: `{'chunk_size': 120, 'chunk_overlap': 24, 'prepend_headings': True, 'top_k': 6, 'mode': 'bm25', 'query_expansion': True, 'min_relevance': 0.0}`
- now passing: amb-21
- newly failing: ans-04, ans-07, tool-15
