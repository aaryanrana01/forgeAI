# ForgeAI report - HRPolicyAssistant

**Shipped definition v0: 67% of 21 generated cases pass** (95% CI 45%-83%; dev 67%, untouched holdout 67%).

Factory model `qwen2.5:3b-instruct`; judge model `qwen2.5:3b-instruct`; embeddings `none (BM25 only)`. Stop reason: early stop after iteration 1: +0.0 pp dev gain for 33,356 tokens (< 0.5 pp per 100k) and the next fix would target the same category (prompt_defect).

## 1. Requirements and groundability

Scope: Answers HR policy questions for shore staff at BlueWake Shipping regarding leave, travel and expense claims, and working from home. Also provides salary band and payroll calendar information.

Groundability: 3 supported, 1 partial, 1 unsupported (groundable fraction 70%). Unsupported topics will be REFUSED by the agent instead of answered: payroll calendar; salary bands and payroll dates.

Flagged gaps (requested in the brief, NOT supported by the documents, so the agent refuses them):
- payroll calendar
- salary bands and payroll dates

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
| concise | 7/12 | 67% | 269 |
| procedural **(winner)** | 8/12 | 71% | 299 |
| persona | 7/12 | 67% | 354 |

Winner 'procedural'. Spread between best and worst candidate: 1 case(s) of 12 - within noise for this sample size; the choice is weakly supported.

## 4. Scorecard per iteration

| Iteration | Def. version | Overall | 95% CI | Dev | Holdout | answerable | cross_doc | edge_ambiguous | edge_injection | out_of_scope | Retrieval hit | Fact recall | Grounded | Refusal recall | Over-refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| iter 0 | v0 | **67%** (14/21) | 45%-83% | 67% | 67% | 8/10 | 0/1 | 1/3 | 2/2 | 3/5 | 93% | 71% | 100% | 71% | 0% |
| iter 1 (reverted) | v1 | **67%** (14/21) | 45%-83% | 67% | 67% | 8/10 | 0/1 | 1/3 | 2/2 | 3/5 | 93% | 77% | 100% | 71% | 7% |

## 5. What changed

- **Iteration 1** (reverted (dev score did not improve)): P1 wrong_refusal -> must_refuse_topics (agent answered questions on topics it must refuse); P2 prompt_defect -> prompt.answering_rules (The prompt is missing facts from the provided documents, leading to incomplete or incorrect answers.). Dev 67% -> 67%. Fixed 0, broke 0.

## 6. What still fails and why (7 of 21)

### prompt_defect - 4 case(s)
_the facts were available but the agent's instructions led to an incomplete or malformed reply_

- `ans-10` (answerable, dev) "How many days of annual leave can a new joiner start using?" -> missing_facts: answer omitted expected facts: ['3 months']
- `x-11` (cross_doc, dev) "What is the standard economy class travel option for employees, and how are compensatory off days calculated for public holidays?" -> missing_facts: answer omitted expected facts: ['All bookings are made through the company travel desk.', 'Each office observes 12 public holidays per calendar year.']
- `ans-03` (answerable, holdout) "How many days after the trip can a claim be submitted?" -> missing_facts: answer omitted expected facts: ['30 days']
- `amb-18` (edge_ambiguous, holdout) "How long can it be after that trip before it's that thing?" -> missing_facts: answer omitted expected facts: ['30 days']

### wrong_refusal - 2 case(s)
_the agent refused when it should answer, or answered when it should refuse_

- `oos-15` (out_of_scope, dev) "How do I request a working from home approval for next week?" -> under_refusal: answered a question it must refuse
- `oos-16` (out_of_scope, dev) "Can you explain the leave policy for shore staff at BlueWake Shipping?" -> under_refusal: answered a question it must refuse

### retrieval_miss - 1 case(s)
_the search step never put the needed passage in front of the model_

- `amb-17` (edge_ambiguous, dev) "Ngl, what's the v of the leave pol? typo: v instead of ver" -> context_lacked_facts: retrieved context did not contain the expected facts

## 7. How far to trust the judge

Calibration probe (known-good, padded-with-fabrication and wrong-number answers): LLM judge accuracy 78%, combined with deterministic checks 89%. LLM grounding vote ENABLED.

Defences in use: per-fact yes/no grading against document-extracted facts; numbers checked by code (the LLM can never accept a different number); claim-support *ratio* so padding cannot raise a score; evidence shown in two orders when a verdict is negative; no pairwise comparisons anywhere. Judge and factory are the SAME model family - self-preference risk remains; set FORGE_JUDGE_MODEL to a different family to reduce it.

## 8. Limitations of this evaluation

- 21 cases is a small sample: the 95% interval above is wide on purpose.
- Cases were generated by the factory model from sampled passages: topics in unsampled passages are untested.
- Paraphrase edge cases share facts with their parent case, so they are not independent evidence.
- 16 generated candidates were rejected by verification (see 04_evals/dropped_cases.json) - evidence that the generator is imperfect.
- Dates in tool cases are resolved against the day the eval runs.

## 9. Cost

145 model calls (58 served from cache), 139,252 tokens, 569.1 s wall-clock. Per stage: see run_meta.json.

## 10. Run the agent

```bash
python -m forgeai chat <this-run-folder>/agent_definition.json
```
