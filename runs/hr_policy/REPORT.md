# ForgeAI report - HRPolicyAssistant

**Shipped definition v0: 68% of 22 generated cases pass** (95% CI 47%-84%; dev 62%, untouched holdout 83%).

Factory model `qwen2.5:3b-instruct`; judge model `qwen2.5:3b-instruct`; embeddings `none (BM25 only)`. Stop reason: early stop after iteration 1: -6.3 pp dev gain for 34,901 tokens (< 0.5 pp per 100k) and the next fix would target the same category (prompt_defect).

## 1. Requirements and groundability

Scope: Answers HR policy questions for shore staff at BlueWake Shipping, including leave, travel, expense claims, working from home, and salary band inquiries.

Groundability: 5 supported, 3 partial, 2 unsupported (groundable fraction 65%). Unsupported topics will be REFUSED by the agent instead of answered: salary band; grievances and speak-up.

Flagged gaps (requested in the brief, NOT supported by the documents, so the agent refuses them):
- salary band
- grievances and speak-up

## 2. Tool selection

| Tool | Attached | Why |
|---|---|---|
| csv_lookup | no | not requested by model |
| calculator | no | not requested by model |
| current_date | no | not requested by model |
| weather | no | not requested by model |

## 3. Prompt tournament

3 candidate system prompts were scored on 12 dev cases (absolute pass rates, no pairwise LLM preference).

| Candidate | Dev pass | Fact recall | Prompt words |
|---|---|---|---|
| concise | 7/12 | 73% | 323 |
| procedural **(winner)** | 7/12 | 73% | 315 |
| persona | 6/12 | 53% | 348 |

Winner 'procedural'. Spread between best and worst candidate: 1 case(s) of 12 - within noise for this sample size; the choice is weakly supported.

## 4. Scorecard per iteration

| Iteration | Def. version | Overall | 95% CI | Dev | Holdout | answerable | cross_doc | edge_ambiguous | edge_injection | out_of_scope | Retrieval hit | Fact recall | Grounded | Refusal recall | Over-refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| iter 0 | v0 | **68%** (15/22) | 47%-84% | 62% | 83% | 8/10 | 0/2 | 1/3 | 2/2 | 4/5 | 93% | 78% | 100% | 86% | 13% |
| iter 1 (reverted) | v1 | **64%** (14/22) | 43%-80% | 56% | 83% | 7/10 | 0/2 | 1/3 | 2/2 | 4/5 | 93% | 65% | 100% | 86% | 7% |

## 5. What changed

- **Iteration 1** (reverted (dev score did not improve)): P1 prompt_defect -> prompt.answering_rules (The common cause for the failures is that the assistant is omitting expected facts without providing a comprehensive answer, leading to refusal due to lack of i); P2 wrong_refusal -> prompt.refusal_rules (The current refusal rules do not cover questions about reporting conflicts of interest, leading to a refusal instead of a refusal to answer.). Dev 62% -> 56%. Fixed 0, broke 1.

## 6. What still fails and why (7 of 22)

### prompt_defect - 4 case(s)
_the facts were available but the agent's instructions led to an incomplete or malformed reply_

- `ans-10` (answerable, dev) "How many days of annual leave do new joiners start using after their probation period?" -> missing_facts: answer omitted expected facts: ['three months']
- `x-11` (cross_doc, dev) "What is the purpose of the HR Policy and what does it cover?" -> missing_facts: answer omitted expected facts: ['Purpose', 'Scope']
- `x-12` (cross_doc, dev) "What is the standard economy class travel option for employees, and how many public holidays are observed by the office?" -> missing_facts: answer omitted expected facts: ['All bookings are made through the company travel desk.', '3. Air Travel Economy class is the standard for all employees.']
- `ans-06` (answerable, holdout) "What is the maximum hotel rate for Tier-1 cities?" -> missing_facts: answer omitted expected facts: ['Tier-1 cities']

### wrong_refusal - 2 case(s)
_the agent refused when it should answer, or answered when it should refuse_

- `oos-14` (out_of_scope, dev) "How do I report a conflict of interest to HR?" -> under_refusal: answered a question it must refuse
- `amb-20` (edge_ambiguous, dev) "Could you please inform me how many days of paid sick leave do employees receive, considering an interesting personal anecdote about my gran" -> over_refusal: refused although the retrieved context contained the answer

### retrieval_miss - 1 case(s)
_the search step never put the needed passage in front of the model_

- `amb-18` (edge_ambiguous, dev) "Ngl, what's the v of the leave pol? typo: v instead of ver" -> refused_without_context: refused because retrieval did not surface the source passage

## 7. How far to trust the judge

Calibration probe (known-good, padded-with-fabrication and wrong-number answers): LLM judge accuracy 78%, combined with deterministic checks 100%. LLM grounding vote ENABLED.

Defences in use: per-fact yes/no grading against document-extracted facts; numbers checked by code (the LLM can never accept a different number); claim-support *ratio* so padding cannot raise a score; evidence shown in two orders when a verdict is negative; no pairwise comparisons anywhere. Judge and factory are the SAME model family - self-preference risk remains; set FORGE_JUDGE_MODEL to a different family to reduce it.

## 8. Limitations of this evaluation

- 22 cases is a small sample: the 95% interval above is wide on purpose.
- Cases were generated by the factory model from sampled passages: topics in unsampled passages are untested.
- Paraphrase edge cases share facts with their parent case, so they are not independent evidence.
- 15 generated candidates were rejected by verification (see 04_evals/dropped_cases.json) - evidence that the generator is imperfect.
- Dates in tool cases are resolved against the day the eval runs.

## 9. Cost

174 model calls (47 served from cache), 164,085 tokens, 651.2 s wall-clock. Per stage: see run_meta.json.

## 10. Run the agent

```bash
python -m forgeai chat <this-run-folder>/agent_definition.json
```
