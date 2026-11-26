# Critic-optimizer iteration log

## Iteration 1 - reverted (dev score did not improve)
Dev pass-rate 62% -> 56%; holdout 83% -> 83%; overall 68% -> 64%. Tokens spent: 34,901.

Dev failures going in: {'prompt_defect': 3, 'wrong_refusal': 2, 'retrieval_miss': 1}
- **P1 [prompt_defect] prompt.answering_rules** - The common cause for the failures is that the assistant is omitting expected facts without providing a comprehensive answer, leading to refusal due to lack of information.  
  addresses: ans-10, x-11, x-12  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the provided documents and TOOL RESULTS.', 'Cite the IDs of the passages used.', 'If the context does not contain the answer, refuse instead of gu ...`  
  after: `['Use only facts found in the CONTEXT, TOOL RESULTS, and any additional expected facts. Never use outside knowledge.', 'Answer only from the provided documents and TOOL RESULTS.', 'Cite the IDs of the passages used.', 'If the context does not contain the answe ...`
- **P2 [wrong_refusal] prompt.refusal_rules** - The current refusal rules do not cover questions about reporting conflicts of interest, leading to a refusal instead of a refusal to answer.  
  addresses: oos-14  
  before: `['Salary band inquiries are not covered by the provided documents.', 'Grievances and speak-up are not covered by the provided documents.', 'Conflicts of interest, speak-up, and grievances are not covered by the provided documents.']`  
  after: `['Salary band inquiries are not covered by the provided documents.', 'Grievances and speak-up are not covered by the provided documents.', 'Conflicts of interest, speak-up, and grievances are not covered by the provided documents.', 'Refuses to answer question ...`
- newly failing: ans-09
