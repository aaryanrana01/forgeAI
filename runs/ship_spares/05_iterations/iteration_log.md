# Critic-optimizer iteration log

## Iteration 1 - kept
Dev pass-rate 40% -> 47%; holdout 80% -> 100%; overall 50% -> 60%. Tokens spent: 41,279.

Dev failures going in: {'wrong_refusal': 6, 'prompt_defect': 2, 'retrieval_miss': 1}
- **P1 [wrong_refusal] prompt.answering_rules** - agent refused although the context contained the answer  
  addresses: ans-03, tool-12, amb-16, amb-18  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`
- **P2 [prompt_defect] prompt.answering_rules** - The prompt is failing to find or provide the necessary facts for answering the questions, leading to refusal or incorrect answers.  
  addresses: ans-05, tool-14  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`
- now passing: ans-06, oos-11

## Iteration 2 - reverted (dev score did not improve)
Dev pass-rate 47% -> 40%; holdout 100% -> 80%; overall 60% -> 50%. Tokens spent: 88,117.

Dev failures going in: {'wrong_refusal': 5, 'prompt_defect': 2, 'retrieval_miss': 1}
- **P3 [wrong_refusal] prompt.answering_rules** - agent refused although the context contained the answer  
  addresses: ans-03, tool-12, amb-16, amb-18  
  before: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`  
  after: `['Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.', 'Answer only from the CONTEXT / TOOL RESULTS.', 'Cite the ids of the passages used.', 'If the context does not contain the answer, refuse instead of guessing.', 'Co ...`
- **P4 [prompt_defect] prompt.tool_rules** - The prompt is failing to find or provide the correct surcharge percentage and delivery time, likely due to missing or incorrect use of tools.  
  addresses: ans-05, tool-14  
  before: `['Use csv_lookup when needed: Brief needs exact values from a structured table (catalogue, price list, inventory, roster).', 'Use calculator when needed: Brief needs arithmetic: totals, costs, quantities, percentages, conversions.']`  
  after: `['Use csv_lookup when needed: Brief needs exact values from a structured table (catalogue, price list, inventory, roster).', 'Use calculator when needed: Brief needs arithmetic: totals, costs, quantities, percentages, conversions.', 'Use csv_lookup and current ...`
- newly failing: ans-06, oos-11
