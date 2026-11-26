# Critic-optimizer iteration log

## Iteration 1 - kept
Dev pass-rate 72% -> 78%; holdout 40% -> 40%; overall 65% -> 70%. Tokens spent: 78,810.

Dev failures going in: {'prompt_defect': 3, 'hallucination': 1, 'retrieval_miss': 1}
- **P1 [retrieval_miss] retrieval** - smaller_chunks: dev retrieval hit-rate 90% -> 100% (measured over 10 dev cases, 8 variants tried)  
  addresses: amb-20  
  before: `{'chunk_size': 120, 'chunk_overlap': 24, 'prepend_headings': True, 'top_k': 6, 'mode': 'bm25', 'query_expansion': False, 'min_relevance': 0.0}`  
  after: `{'chunk_size': 80, 'chunk_overlap': 15, 'prepend_headings': True, 'top_k': 6, 'mode': 'bm25', 'query_expansion': False, 'min_relevance': 0.0}`
- **P2 [hallucination] prompt.answering_rules** - answers contained values/claims absent from the evidence: numbers not in evidence: [17160.0]  
  addresses: tool-15  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'If the CONTEXT does not contain the answer, set refused=true. Do not guess.', 'Find the correct part number and description for a specific engine or machine from t ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'If the CONTEXT does not contain the answer, set refused=true. Do not guess.', 'Find the correct part number and description for a specific engine or machine from t ...`
- now passing: amb-20, ans-01, ans-03, ans-05, ans-08
- newly failing: amb-21, ans-02, ans-06, oos-11

## Iteration 2 - reverted (dev score did not improve)
Dev pass-rate 78% -> 78%; holdout 40% -> 40%; overall 70% -> 70%. Tokens spent: 41,237.

Dev failures going in: {'prompt_defect': 3, 'hallucination': 1}
- **P3 [hallucination] prompt.answering_rules** - answers contained values/claims absent from the evidence: numbers not in evidence: [17160.0]  
  addresses: tool-15  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'If the CONTEXT does not contain the answer, set refused=true. Do not guess.', 'Find the correct part number and description for a specific engine or machine from t ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'If the CONTEXT does not contain the answer, set refused=true. Do not guess.', 'Find the correct part number and description for a specific engine or machine from t ...`
- now passing: ans-02
- newly failing: oos-14

## Iteration 3 - kept
Dev pass-rate 78% -> 89%; holdout 40% -> 40%; overall 70% -> 78%. Tokens spent: 44,758.

Dev failures going in: {'prompt_defect': 3, 'hallucination': 1}
- **P4 [hallucination] prompt.answering_rules** - answers contained values/claims absent from the evidence: numbers not in evidence: [17160.0]  
  addresses: tool-15  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'If the CONTEXT does not contain the answer, set refused=true. Do not guess.', 'Find the correct part number and description for a specific engine or machine from t ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'If the CONTEXT does not contain the answer, set refused=true. Do not guess.', 'Find the correct part number and description for a specific engine or machine from t ...`
- now passing: amb-21, ans-02
