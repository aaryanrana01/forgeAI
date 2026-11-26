# Critic-optimizer iteration log

## Iteration 1 - reverted (dev score did not improve)
Dev pass-rate 73% -> 73%; holdout 67% -> 67%; overall 71% -> 71%. Tokens spent: 40,979.

Dev failures going in: {'prompt_defect': 1, 'wrong_refusal': 2, 'retrieval_miss': 1}
- **P1 [wrong_refusal] must_refuse_topics** - agent answered questions on topics it must refuse  
  addresses: oos-16  
  before: `['salary bands and payroll dates', 'payroll calendar', 'tell employees their salary band']`  
  after: `['salary bands and payroll dates', 'payroll calendar', 'tell employees their salary band', 'leave policy, travel and expense policy, working from home, hybrid work and conduct policy']`
- **P2 [retrieval_miss] retrieval** - query_expansion: dev retrieval hit-rate 90% -> 100% (measured over 10 dev cases, 8 variants tried)  
  addresses: amb-17  
  before: `{'chunk_size': 120, 'chunk_overlap': 24, 'prepend_headings': True, 'top_k': 5, 'mode': 'bm25', 'query_expansion': False, 'min_relevance': 0.0}`  
  after: `{'chunk_size': 120, 'chunk_overlap': 24, 'prepend_headings': True, 'top_k': 5, 'mode': 'bm25', 'query_expansion': True, 'min_relevance': 0.0}`
- now passing: amb-17
- newly failing: ans-05
