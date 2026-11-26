# ForgeAI report - SpareFinder

**Shipped definition v0: 65% of 23 generated cases pass** (95% CI 45%-81%; dev 61%, untouched holdout 80%).

Factory model `qwen2.5:3b-instruct`; judge model `qwen2.5:3b-instruct`; embeddings `none (BM25 only)`. Stop reason: early stop after iteration 1: -5.5 pp dev gain for 110,922 tokens (< 0.5 pp per 100k) and the next fix would target the same category (prompt_defect).

## 1. Requirements and groundability

Scope: An AI assistant for fleet technical superintendents to procure ship spares, manage orders, and track shipments.

Groundability: 6 supported, 2 partial, 1 unsupported (groundable fraction 78%). Unsupported topics will be REFUSED by the agent instead of answered: live shipment status.

Flagged gaps (requested in the brief, NOT supported by the documents, so the agent refuses them):
- live shipment status

## 2. Tool selection

| Tool | Attached | Why |
|---|---|---|
| csv_lookup | yes | attached: model justified it and precondition holds |
| calculator | yes | attached by rule (not requested by model): must-answer topic 'stock quantity' is computed from spares_catalogue.csv columns |
| current_date | yes | attached by rule (not requested by model): must-answer topic 'lead time' is computed from spares_catalogue.csv columns |
| weather | no | not requested by model |

## 3. Prompt tournament

3 candidate system prompts were scored on 12 dev cases (absolute pass rates, no pairwise LLM preference).

| Candidate | Dev pass | Fact recall | Prompt words |
|---|---|---|---|
| concise | 7/12 | 58% | 492 |
| procedural | 7/12 | 64% | 432 |
| persona **(winner)** | 8/12 | 64% | 388 |

Winner 'persona'. Spread between best and worst candidate: 1 case(s) of 12 - within noise for this sample size; the choice is weakly supported.

## 4. Scorecard per iteration

| Iteration | Def. version | Overall | 95% CI | Dev | Holdout | answerable | cross_doc | edge_ambiguous | edge_injection | out_of_scope | tool | Retrieval hit | Fact recall | Grounded | Refusal recall | Over-refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| iter 0 | v0 | **65%** (15/23) | 45%-81% | 61% | 80% | 5/8 | 0/1 | 0/3 | 2/2 | 5/5 | 3/4 | 94% | 61% | 100% | 100% | 12% |
| iter 1 (reverted) | v1 | **56%** (13/23) | 37%-74% | 56% | 60% | 3/8 | 0/1 | 1/3 | 2/2 | 5/5 | 2/4 | 100% | 59% | 100% | 100% | 31% |

## 5. What changed

- **Iteration 1** (reverted (dev score did not improve)): P1 prompt_defect -> prompt.answering_rules (The common cause is that the assistant is missing expected facts and is not able to provide the full context or additional information required by the user's qu); P2 retrieval_miss -> retrieval (query_expansion: dev retrieval hit-rate 90% -> 100% (measured over 10 dev cases, 8 variants tried)). Dev 61% -> 56%. Fixed 1, broke 3.

## 6. What still fails and why (8 of 23)

### prompt_defect - 6 case(s)
_the facts were available but the agent's instructions led to an incomplete or malformed reply_

- `ans-03` (answerable, dev) "How many months does the agreement between Poseidon Marine Supply and Meridian Fleet Management last for?" -> missing_facts: answer omitted expected facts: ['1 January 2026 to 31 December 2027']
- `ans-06` (answerable, dev) "What is the surcharge for urgent orders?" -> missing_facts: answer omitted expected facts: ['15 percent']
- `ans-08` (answerable, dev) "What is the minimum order value for orders above USD 5,000?" -> missing_facts: answer omitted expected facts: ['USD 500']
- `x-09` (cross_doc, dev) "What are the minimum order values for NordMarine Parts AS and what types of spare parts does Meridian Fleet Management procure?" -> missing_facts: answer omitted expected facts: ['Purchases of provisions, crew services and dry-dock contracts follow separate procedures.']
- `amb-21` (edge_ambiguous, dev) "How many months does the agreement between Poseidon Marine Supply and Meridian Fleet Management last for? I just had a strange dream about s" -> missing_facts: answer omitted expected facts: ['1 January 2026 to 31 December 2027']
- `tool-17` (tool, holdout) "When would I receive the item with part number AE-HG-7230 if I order today?" -> tool_not_used: did not call ['csv_lookup', 'current_date']; facts {'date:+5': 'missing'}

### retrieval_miss - 1 case(s)
_the search step never put the needed passage in front of the model_

- `amb-19` (edge_ambiguous, dev) "How bout min order for >$5k orders? 🤔 (typo: > instead of >=)" -> refused_without_context: refused because retrieval did not surface the source passage

### wrong_refusal - 1 case(s)
_the agent refused when it should answer, or answered when it should refuse_

- `amb-20` (edge_ambiguous, dev) "How many it must that thing keep on board according to it?" -> over_refusal: refused although the retrieved context contained the answer

## 7. How far to trust the judge

Calibration probe (known-good, padded-with-fabrication and wrong-number answers): LLM judge accuracy 89%, combined with deterministic checks 89%. LLM grounding vote ENABLED.

Defences in use: per-fact yes/no grading against document-extracted facts; numbers checked by code (the LLM can never accept a different number); claim-support *ratio* so padding cannot raise a score; evidence shown in two orders when a verdict is negative; no pairwise comparisons anywhere. Judge and factory are the SAME model family - self-preference risk remains; set FORGE_JUDGE_MODEL to a different family to reduce it.

## 8. Limitations of this evaluation

- 23 cases is a small sample: the 95% interval above is wide on purpose.
- Cases were generated by the factory model from sampled passages: topics in unsampled passages are untested.
- Paraphrase edge cases share facts with their parent case, so they are not independent evidence.
- 10 generated candidates were rejected by verification (see 04_evals/dropped_cases.json) - evidence that the generator is imperfect.
- Dates in tool cases are resolved against the day the eval runs.

## 9. Cost

258 model calls (149 served from cache), 302,267 tokens, 1298.6 s wall-clock. Per stage: see run_meta.json.

## 10. Run the agent

```bash
python -m forgeai chat <this-run-folder>/agent_definition.json
```
