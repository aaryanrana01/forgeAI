# Critic-optimizer iteration log

## Iteration 1 - reverted (dev score did not improve)
Dev pass-rate 71% -> 71%; holdout 50% -> 67%; overall 65% -> 70%. Tokens spent: 37,819.

Dev failures going in: {'prompt_defect': 1, 'wrong_refusal': 2, 'retrieval_miss': 1}
- **P1 [wrong_refusal] must_refuse_topics** - agent answered questions on topics it must refuse  
  addresses: oos-14, oos-15  
  before: `['salary bands and payroll dates', 'payroll calendar']`  
  after: `['salary bands and payroll dates', 'payroll calendar', 'leave policy', 'working from home']`
- **P2 [retrieval_miss] retrieval** - query_expansion: dev retrieval hit-rate 89% -> 100% (measured over 9 dev cases, 8 variants tried)  
  addresses: amb-16  
  before: `{'chunk_size': 120, 'chunk_overlap': 24, 'prepend_headings': True, 'top_k': 5, 'mode': 'bm25', 'query_expansion': False, 'min_relevance': 0.0}`  
  after: `{'chunk_size': 120, 'chunk_overlap': 24, 'prepend_headings': True, 'top_k': 5, 'mode': 'bm25', 'query_expansion': True, 'min_relevance': 0.0}`
- now passing: amb-16, ans-06
- newly failing: ans-05
