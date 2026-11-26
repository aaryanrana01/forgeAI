# ForgeAI report - HRPolicyAssistant

**Shipped definition v0: 52% of 21 generated cases pass** (95% CI 32%-72%; dev 60%, untouched holdout 33%).

⚠ Dev beats holdout by 27 points: the optimizer may have fitted the dev cases. Trust the holdout number more.

Factory model `qwen2.5:3b-instruct`; judge model `qwen2.5:3b-instruct`; embeddings `none (BM25 only)`. Stop reason: early stop after iteration 1: +0.0 pp dev gain for 29,454 tokens (< 0.5 pp per 100k) and the next fix would target the same category (prompt_defect).

## 1. Requirements and groundability

Scope: Answers HR policy questions for shore staff at BlueWake Shipping, including leave, travel, expense claims, working from home, and salary band inquiries.

Groundability: 5 supported, 4 partial, 1 unsupported (groundable fraction 70%). Unsupported topics will be REFUSED by the agent instead of answered: salary band.

Flagged gaps (requested in the brief, NOT supported by the documents, so the agent refuses them):
- salary band

## 2. Tool selection

| Tool | Attached | Why |
|---|---|---|
| csv_lookup | no | not requested by model |
| calculator | no | not requested by model |
| current_date | no | not requested by model |
| weather | no | not requested by model |

## 4. Scorecard per iteration

| Iteration | Def. version | Overall | 95% CI | Dev | Holdout | answerable | cross_doc | edge_ambiguous | edge_injection | out_of_scope | Retrieval hit | Fact recall | Grounded | Refusal recall | Over-refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| iter 0 | v0 | **52%** (11/21) | 32%-72% | 60% | 33% | 5/10 | 0/1 | 1/3 | 2/2 | 3/5 | 93% | 57% | 100% | 71% | 14% |
| iter 1 (reverted) | v1 | **52%** (11/21) | 32%-72% | 60% | 33% | 5/10 | 0/1 | 1/3 | 2/2 | 3/5 | 93% | 57% | 100% | 71% | 14% |

## 5. What changed

- **Iteration 1** (reverted (dev score did not improve)): P1 prompt_defect -> prompt.answering_rules (The prompt is missing rules to ensure that answers include all expected facts, leading to omitted answers and refusal of questions.); P2 wrong_refusal -> must_refuse_topics (agent answered questions on topics it must refuse). Dev 60% -> 60%. Fixed 0, broke 0.

## 6. What still fails and why (10 of 21)

### prompt_defect - 5 case(s)
_the facts were available but the agent's instructions led to an incomplete or malformed reply_

- `ans-05` (answerable, dev) "How many days of paid sick leave do employees receive?" -> missing_facts: answer omitted expected facts: ['12 days of paid sick leave', 'per leave year']
- `ans-07` (answerable, dev) "How many days per week can employees work from home?" -> missing_facts: answer omitted expected facts: ['2 days per week']
- `x-11` (cross_doc, dev) "What is the purpose of the HR Policy and what does it cover?" -> missing_facts: answer omitted expected facts: ['Purpose', 'Scope']
- `ans-06` (answerable, holdout) "What is the maximum hotel rate per night in Tier-1 cities?" -> missing_facts: answer omitted expected facts: ['Tier-1 cities']
- `amb-18` (edge_ambiguous, holdout) "How many days after that thing is it not reimbursed if not submitted? It's a policy name, but we're not asking about it." -> missing_facts: answer omitted expected facts: ['60 days']

### wrong_refusal - 4 case(s)
_the agent refused when it should answer, or answered when it should refuse_

- `oos-16` (out_of_scope, dev) "Can you explain the hybrid work and conduct policy for shore staff?" -> under_refusal: answered a question it must refuse
- `amb-19` (edge_ambiguous, dev) "Could you please inform me how many days of paid sick leave do employees receive, considering an interesting personal anecdote about my gran" -> over_refusal: refused although the retrieved context contained the answer
- `ans-03` (answerable, holdout) "How many days after the trip are claims not reimbursed if not submitted?" -> over_refusal: refused although the retrieved context contained the answer
- `oos-14` (out_of_scope, holdout) "How does the company handle conflicts of interest for shore staff?" -> under_refusal: answered a question it must refuse

### retrieval_miss - 1 case(s)
_the search step never put the needed passage in front of the model_

- `ans-10` (answerable, dev) "What is the minimum time before booking a trip for travel claims?" -> context_lacked_facts: retrieved context did not contain the expected facts

## 7. How far to trust the judge

Calibration probe (known-good, padded-with-fabrication and wrong-number answers): LLM judge accuracy 56%, combined with deterministic checks 89%. LLM grounding vote DISABLED (failed calibration) - only code checks decide grounding.

Defences in use: per-fact yes/no grading against document-extracted facts; numbers checked by code (the LLM can never accept a different number); claim-support *ratio* so padding cannot raise a score; evidence shown in two orders when a verdict is negative; no pairwise comparisons anywhere. Judge and factory are the SAME model family - self-preference risk remains; set FORGE_JUDGE_MODEL to a different family to reduce it.

## 8. Limitations of this evaluation

- 21 cases is a small sample: the 95% interval above is wide on purpose.
- Cases were generated by the factory model from sampled passages: topics in unsampled passages are untested.
- Paraphrase edge cases share facts with their parent case, so they are not independent evidence.
- 15 generated candidates were rejected by verification (see 04_evals/dropped_cases.json) - evidence that the generator is imperfect.
- Dates in tool cases are resolved against the day the eval runs.

## 9. Cost

103 model calls (38 served from cache), 103,836 tokens, 721.8 s wall-clock. Per stage: see run_meta.json.

## 10. Run the agent

```bash
python -m forgeai chat <this-run-folder>/agent_definition.json
```
