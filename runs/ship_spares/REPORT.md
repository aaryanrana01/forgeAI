# ForgeAI report - SpareFinder

**Shipped definition v2: 78% of 23 generated cases pass** (95% CI 58%-90%; dev 89%, untouched holdout 40%).

⚠ Dev beats holdout by 49 points: the optimizer may have fitted the dev cases. Trust the holdout number more.

Factory model `qwen2.5:3b-instruct`; judge model `qwen2.5:3b-instruct`; embeddings `none (BM25 only)`. Stop reason: completed 3 iterations.

## 1. Requirements and groundability

Scope: Help fleet technical superintendents procure ship spares by finding parts, checking prices, stock, and lead times, and providing order totals and supplier terms.

Groundability: 10 supported, 0 partial, 1 unsupported (groundable fraction 91%). Unsupported topics will be REFUSED by the agent instead of answered: Use USD as the currency and the units specified in the documents..

Flagged gaps (requested in the brief, NOT supported by the documents, so the agent refuses them):
- Use USD as the currency and the units specified in the documents.

## 2. Tool selection

| Tool | Attached | Why |
|---|---|---|
| csv_lookup | yes | attached: model justified it and precondition holds |
| calculator | no | not requested by model |
| current_date | no | not requested by model |
| weather | no | not requested by model |

## 3. Prompt tournament

3 candidate system prompts were scored on 12 dev cases (absolute pass rates, no pairwise LLM preference).

| Candidate | Dev pass | Fact recall | Prompt words |
|---|---|---|---|
| concise | 8/12 | 79% | 458 |
| procedural | 7/12 | 92% | 477 |
| persona **(winner)** | 9/12 | 81% | 470 |

Winner 'persona'. Spread between best and worst candidate: 2 case(s) of 12.

## 4. Scorecard per iteration

| Iteration | Def. version | Overall | 95% CI | Dev | Holdout | answerable | cross_doc | edge_ambiguous | edge_injection | out_of_scope | tool | Retrieval hit | Fact recall | Grounded | Refusal recall | Over-refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| iter 0 | v0 | **65%** (15/23) | 45%-81% | 72% | 40% | 3/8 | 1/1 | 2/3 | 2/2 | 5/5 | 2/4 | 94% | 67% | 93% | 100% | 6% |
| iter 1 | v1 | **70%** (16/23) | 49%-84% | 78% | 40% | 5/8 | 1/1 | 2/3 | 2/2 | 4/5 | 2/4 | 100% | 72% | 94% | 86% | 0% |
| iter 2 (reverted) | v2 | **70%** (16/23) | 49%-84% | 78% | 40% | 6/8 | 1/1 | 2/3 | 2/2 | 3/5 | 2/4 | 100% | 78% | 94% | 71% | 0% |
| iter 3 | v2 | **78%** (18/23) | 58%-90% | 89% | 40% | 6/8 | 1/1 | 3/3 | 2/2 | 4/5 | 2/4 | 100% | 88% | 88% | 86% | 0% |

## 5. What changed

- **Iteration 1** (kept): P1 retrieval_miss -> retrieval (smaller_chunks: dev retrieval hit-rate 90% -> 100% (measured over 10 dev cases, 8 variants tried)); P2 hallucination -> prompt.answering_rules (answers contained values/claims absent from the evidence: numbers not in evidence: [17160.0]). Dev 72% -> 78%. Fixed 5, broke 4.
- **Iteration 2** (reverted (dev score did not improve)): P3 hallucination -> prompt.answering_rules (answers contained values/claims absent from the evidence: numbers not in evidence: [17160.0]). Dev 78% -> 78%. Fixed 1, broke 1.
- **Iteration 3** (kept): P4 hallucination -> prompt.answering_rules (answers contained values/claims absent from the evidence: numbers not in evidence: [17160.0]). Dev 78% -> 89%. Fixed 2, broke 0.

## 6. What still fails and why (5 of 23)

### prompt_defect - 2 case(s)
_the facts were available but the agent's instructions led to an incomplete or malformed reply_

- `ans-06` (answerable, dev) "What is the maximum order value for the technical superintendent to approve?" -> missing_facts: answer omitted expected facts: ['USD 5,000']
- `tool-17` (tool, holdout) "When would I receive the item with part number AE-HG-7230 if I order it today?" -> tool_not_used: did not call ['current_date']; facts {'date:+5': 'missing'}

### hallucination - 2 case(s)
_the answer stated something the evidence does not contain_

- `tool-15` (tool, dev) "How much does it cost to order 8 units of the OW-OC-9505 item?" -> unsupported_numbers: numbers not in evidence: [17160.0]
- `ans-07` (answerable, holdout) "What is the minimum order value for orders above USD 5,000?" -> unsupported_claims: only 0% of claims supported by evidence

### wrong_refusal - 1 case(s)
_the agent refused when it should answer, or answered when it should refuse_

- `oos-11` (out_of_scope, holdout) "What is the most cost-effective currency for procurement in the shipping industry?" -> under_refusal: answered a question it must refuse

## 7. How far to trust the judge

Calibration probe (known-good, padded-with-fabrication and wrong-number answers): LLM judge accuracy 100%, combined with deterministic checks 100%. LLM grounding vote ENABLED.

Defences in use: per-fact yes/no grading against document-extracted facts; numbers checked by code (the LLM can never accept a different number); claim-support *ratio* so padding cannot raise a score; evidence shown in two orders when a verdict is negative; no pairwise comparisons anywhere. Judge and factory are the SAME model family - self-preference risk remains; set FORGE_JUDGE_MODEL to a different family to reduce it.

Order-swap re-checks: 1, verdict flips: 0.

## 8. Limitations of this evaluation

- 23 cases is a small sample: the 95% interval above is wide on purpose.
- Cases were generated by the factory model from sampled passages: topics in unsampled passages are untested.
- Paraphrase edge cases share facts with their parent case, so they are not independent evidence.
- 10 generated candidates were rejected by verification (see 04_evals/dropped_cases.json) - evidence that the generator is imperfect.
- Dates in tool cases are resolved against the day the eval runs.

## 9. Cost

301 model calls (170 served from cache), 340,497 tokens, 1435.4 s wall-clock. Per stage: see run_meta.json.

## 10. Run the agent

```bash
python -m forgeai chat <this-run-folder>/agent_definition.json
```
