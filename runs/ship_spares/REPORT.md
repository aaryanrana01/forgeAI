# ForgeAI report - SpareFinder

**Shipped definition v1: 60% of 20 generated cases pass** (95% CI 39%-78%; dev 47%, untouched holdout 100%).

Factory model `qwen2.5:3b-instruct`; judge model `qwen2.5:3b-instruct`; embeddings `none (BM25 only)`. Stop reason: early stop after iteration 2: -6.7 pp dev gain for 88,117 tokens (< 0.5 pp per 100k) and the next fix would target the same category (wrong_refusal).

## 1. Requirements and groundability

Scope: Help fleet technical superintendents procure ship spares by finding parts, checking prices, stock, and lead times, and providing order totals and supplier terms.

Groundability: 5 supported, 2 partial, 0 unsupported (groundable fraction 86%).

## 2. Tool selection

| Tool | Attached | Why |
|---|---|---|
| csv_lookup | yes | attached: model justified it and precondition holds |
| calculator | yes | attached by rule (not requested by model): must-answer topic 'order total calculation' is computed from spares_catalogue.csv columns |
| current_date | no | not requested by model |
| weather | no | not requested by model |

## 3. Prompt tournament

3 candidate system prompts were scored on 12 dev cases (absolute pass rates, no pairwise LLM preference).

| Candidate | Dev pass | Fact recall | Prompt words |
|---|---|---|---|
| concise **(winner)** | 4/12 | 50% | 377 |
| procedural | 3/12 | 50% | 366 |
| persona | 4/12 | 50% | 396 |

Winner 'concise'. Spread between best and worst candidate: 1 case(s) of 12 - within noise for this sample size; the choice is weakly supported.

## 4. Scorecard per iteration

| Iteration | Def. version | Overall | 95% CI | Dev | Holdout | answerable | edge_ambiguous | edge_injection | out_of_scope | tool | Retrieval hit | Fact recall | Grounded | Refusal recall | Over-refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| iter 0 | v0 | **50%** (10/20) | 30%-70% | 40% | 80% | 3/6 | 0/3 | 2/2 | 3/5 | 2/4 | 92% | 56% | 100% | 71% | 31% |
| iter 1 | v1 | **60%** (12/20) | 39%-78% | 47% | 100% | 4/6 | 0/3 | 2/2 | 4/5 | 2/4 | 92% | 67% | 100% | 86% | 31% |
| iter 2 (reverted) | v2 | **50%** (10/20) | 30%-70% | 40% | 80% | 3/6 | 0/3 | 2/2 | 3/5 | 2/4 | 92% | 67% | 89% | 71% | 31% |

## 5. What changed

- **Iteration 1** (kept): P1 wrong_refusal -> prompt.answering_rules (agent refused although the context contained the answer); P2 prompt_defect -> prompt.answering_rules (The prompt is failing to find or provide the necessary facts for answering the questions, leading to refusal or incorrect answers.). Dev 40% -> 47%. Fixed 2, broke 0.
- **Iteration 2** (reverted (dev score did not improve)): P3 wrong_refusal -> prompt.answering_rules (agent refused although the context contained the answer); P4 prompt_defect -> prompt.tool_rules (The prompt is failing to find or provide the correct surcharge percentage and delivery time, likely due to missing or incorrect use of tools.). Dev 47% -> 40%. Fixed 0, broke 2.

## 6. What still fails and why (8 of 20)

### wrong_refusal - 5 case(s)
_the agent refused when it should answer, or answered when it should refuse_

- `ans-03` (answerable, dev) "How many units of category A spares must each vessel keep on board?" -> over_refusal: refused although the retrieved context contained the answer
- `oos-09` (out_of_scope, dev) "How long does it usually take to receive a part once ordered?" -> under_refusal: answered a question it must refuse
- `tool-12` (tool, dev) "How much does it cost to order 8 units of the OW-OC-9505 item?" -> over_refusal: refused although the retrieved context contained the answer
- `amb-16` (edge_ambiguous, dev) "Ngl, for reconditioned units? Its like $5 man." -> over_refusal: refused although the retrieved context contained the answer
- `amb-18` (edge_ambiguous, dev) "How many units of category A spares must each vessel keep on board, considering the peculiar tradition of maintaining an extra unit for the " -> over_refusal: refused although the retrieved context contained the answer

### prompt_defect - 2 case(s)
_the facts were available but the agent's instructions led to an incomplete or malformed reply_

- `ans-05` (answerable, dev) "What is the surcharge for urgent orders?" -> missing_facts: answer omitted expected facts: ['15 percent']
- `tool-14` (tool, dev) "When would I receive the item with part number AE-HG-7230 if I order it today?" -> tool_not_used: did not call ['csv_lookup', 'current_date']; facts {'date:+5': 'missing'}

### retrieval_miss - 1 case(s)
_the search step never put the needed passage in front of the model_

- `amb-17` (edge_ambiguous, dev) "What's the lowest amount it takes to order from that thing?" -> context_lacked_facts: retrieved context did not contain the expected facts

## 7. How far to trust the judge

Calibration probe (known-good, padded-with-fabrication and wrong-number answers): LLM judge accuracy 100%, combined with deterministic checks 100%. LLM grounding vote ENABLED.

Defences in use: per-fact yes/no grading against document-extracted facts; numbers checked by code (the LLM can never accept a different number); claim-support *ratio* so padding cannot raise a score; evidence shown in two orders when a verdict is negative; no pairwise comparisons anywhere. Judge and factory are the SAME model family - self-preference risk remains; set FORGE_JUDGE_MODEL to a different family to reduce it.

Order-swap re-checks: 2, verdict flips: 0.

## 8. Limitations of this evaluation

- 20 cases is a small sample: the 95% interval above is wide on purpose.
- Cases were generated by the factory model from sampled passages: topics in unsampled passages are untested.
- Paraphrase edge cases share facts with their parent case, so they are not independent evidence.
- 13 generated candidates were rejected by verification (see 04_evals/dropped_cases.json) - evidence that the generator is imperfect.
- Dates in tool cases are resolved against the day the eval runs.

## 9. Cost

216 model calls (141 served from cache), 278,924 tokens, 972.6 s wall-clock. Per stage: see run_meta.json.

## 10. Run the agent

```bash
python -m forgeai chat <this-run-folder>/agent_definition.json
```
