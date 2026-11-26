"""Requirement 6a - Critic: classify every failure into exactly one category.

The classification is deterministic (driven by the judge's checks), so the
optimizer's decisions can be traced back to evidence rather than to a model's
opinion. Order matters: upstream causes win (if retrieval never delivered the
facts, the prompt is not the first thing to fix)."""

from __future__ import annotations

from ..schemas import CaseResult
from .judge import FACT_RECALL_PASS, GROUNDED_PASS


def classify(r: CaseResult) -> CaseResult:
    if r.passed:
        r.failure_category, r.failure_subtype, r.failure_reason = None, "", ""
        return r
    c = r.checks
    if r.should_refuse and not r.refused:
        r.failure_category, r.failure_subtype = "wrong_refusal", "under_refusal"
        r.failure_reason = "answered a question it must refuse"
    elif not r.should_refuse and r.refused:
        if not c.get("retrieval_hit", True):
            r.failure_category, r.failure_subtype = "retrieval_miss", "refused_without_context"
            r.failure_reason = "refused because retrieval did not surface the source passage"
        else:
            r.failure_category, r.failure_subtype = "wrong_refusal", "over_refusal"
            r.failure_reason = "refused although the retrieved context contained the answer"
    elif "fact_recall" not in c:
        r.failure_category, r.failure_subtype = "prompt_defect", "no_valid_output"
        r.failure_reason = "; ".join(c.get("contract_errors", [])) or "agent produced no usable answer"
    elif not c.get("retrieval_hit", True):
        r.failure_category, r.failure_subtype = "retrieval_miss", "context_lacked_facts"
        extra = " (and the answer contains unsupported claims)" if not c.get("grounded", True) else ""
        r.failure_reason = f"retrieved context did not contain the expected facts{extra}"
    elif c.get("unsupported_numbers") or c.get("claim_support", 1.0) < GROUNDED_PASS:
        r.failure_category, r.failure_subtype = "hallucination", (
            "unsupported_numbers" if c.get("unsupported_numbers") else "unsupported_claims")
        r.failure_reason = (f"numbers not in evidence: {c.get('unsupported_numbers')}" if c.get("unsupported_numbers")
                            else f"only {c.get('claim_support', 0):.0%} of claims supported by evidence")
    elif c.get("expected_tools_missing"):
        r.failure_category, r.failure_subtype = "prompt_defect", "tool_not_used"
        r.failure_reason = f"did not call {c['expected_tools_missing']}; facts {c.get('facts')}"
    elif c.get("fact_recall", 1.0) < FACT_RECALL_PASS:
        r.failure_category, r.failure_subtype = "prompt_defect", "missing_facts"
        missing = [f for f, how in c.get("facts", {}).items() if how == "missing"]
        r.failure_reason = f"answer omitted expected facts: {missing}"
    else:
        r.failure_category, r.failure_subtype = "prompt_defect", "contract_violation"
        r.failure_reason = "; ".join(c.get("contract_errors", [])) or "output contract violated"
    return r
