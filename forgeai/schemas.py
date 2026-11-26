"""Data contracts between the factory stages. Everything the factory produces is
one of these models serialised to JSON, so every artifact is inspectable and
reloadable."""

from __future__ import annotations

import typing
from typing import Any, Literal

from pydantic import BaseModel as _PydanticBase
from pydantic import Field, model_validator


class BaseModel(_PydanticBase):
    """Lenient base: small models often return "x" where ["x"] is expected, ["a", "b"] where a list of
    objects is expected, or {"text": "..."} where a string is expected. Coerce those shapes instead of
    failing the whole stage; anything else still fails validation and triggers a repair retry."""

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for name, field in cls.model_fields.items():
            if name not in data or data[name] is None:
                if name in data and data[name] is None and field.default is not None and not field.is_required():
                    data.pop(name)
                continue
            v, ann = data[name], field.annotation
            origin, args = typing.get_origin(ann), typing.get_args(ann)
            if ann is str and isinstance(v, (list, dict)):
                data[name] = "; ".join(map(str, v.values() if isinstance(v, dict) else v))
            elif ann is bool and isinstance(v, str):
                data[name] = v.strip().lower() in ("true", "yes", "1")
            elif origin is list and args:
                item = args[0]
                if isinstance(v, (str, dict)):
                    v = [v]
                if item is str:
                    v = [x if isinstance(x, str) else "; ".join(map(str, x.values())) if isinstance(x, dict) else str(x)
                         for x in v]
                elif isinstance(item, type) and issubclass(item, _PydanticBase):
                    first = next(iter(item.model_fields))
                    v = [{first: x} if isinstance(x, str) else x for x in v]
                data[name] = v
        return data

# ----------------------------------------------------------------- intake


class ClarifyingQuestion(BaseModel):
    question: str
    why_it_matters: str = ""
    default_assumption: str = Field("", description="answer to assume if the requester does not reply")


class QuestionList(BaseModel):
    questions: list[ClarifyingQuestion]


class QAPair(BaseModel):
    question: str
    answer: str
    source: Literal["requester", "requester_notes", "default_assumption"]


class Topic(BaseModel):
    topic: str
    description: str = ""


class RefuseTopic(BaseModel):
    topic: str
    reason: str = ""


class Requirements(BaseModel):
    agent_name: str
    scope: str
    audience: str
    tone: str
    language: str = "English"
    must_answer_topics: list[Topic]
    must_refuse_topics: list[RefuseTopic]
    escalation_contact: str = Field("", description="where to send users when the agent cannot help")
    success_criteria: list[str] = []
    constraints: list[str] = []
    assumptions: list[str] = []


# ----------------------------------------------------------- groundability


class TopicGrounding(BaseModel):
    topic: str
    verdict: Literal["supported", "partial", "unsupported"]
    evidence_chunk_ids: list[str] = []
    note: str = ""
    lexical_overlap: float = 0.0
    adjusted_by_guard: bool = False


class GroundabilityReport(BaseModel):
    topics: list[TopicGrounding]
    flagged_gaps: list[str]
    groundable_fraction: float
    blocking: bool
    summary: str


# ------------------------------------------------------------ definition


class RetrievalConfig(BaseModel):
    chunk_size: int = 180            # words
    chunk_overlap: int = 40          # words
    prepend_headings: bool = True    # "(doc > section)" prefix on each chunk
    top_k: int = 5
    mode: Literal["bm25", "hybrid"] = "bm25"
    query_expansion: bool = False    # LLM adds synonyms/keywords before searching
    min_relevance: float = 0.0       # 0..1 query-term coverage below which context is dropped
    rationale: str = ""


class ToolBinding(BaseModel):
    name: str
    config: dict = {}
    justification: str = ""
    evidence_quote: str = ""


class PromptSections(BaseModel):
    """The system prompt is stored as sections so the optimizer can patch one
    rule instead of regenerating the whole prompt."""
    role: str
    scope: str
    answering_rules: list[str]
    refusal_rules: list[str]
    tone_rules: list[str] = []
    tool_rules: list[str] = []
    format_rules: list[str] = []


class OutputContract(BaseModel):
    format: Literal["json"] = "json"
    fields: dict[str, str] = {
        "answer": "string - the reply shown to the user",
        "citations": "list of context ids, e.g. ['leave_policy.pdf#3'] or ['tool:csv_lookup#1']",
        "refused": "boolean - true when the agent declines (out of scope / not in documents)",
        "refusal_reason": "string - short reason when refused, else empty",
    }
    rules: list[str] = [
        "citations must only contain ids that appear in the provided CONTEXT or TOOL RESULTS",
        "when refused is false, citations must contain at least one id",
        "when refused is true, answer must contain the refusal message",
    ]
    max_answer_words: int = 180


class AgentDefinition(BaseModel):
    name: str
    version: int = 0
    description: str
    prompt: PromptSections
    system_prompt: str = ""            # rendered from `prompt`, what the model actually sees
    refusal_message: str
    must_refuse_topics: list[str] = []
    retrieval: RetrievalConfig = RetrievalConfig()
    tools: list[ToolBinding] = []
    output_contract: OutputContract = OutputContract()
    temperature: float = 0.0
    knowledge_dir: str = "knowledge"   # relative to the definition file
    generated_by: dict = {}


# ------------------------------------------------------------------ evals


class EvalCase(BaseModel):
    id: str
    category: Literal["answerable", "cross_doc", "out_of_scope", "edge_ambiguous",
                      "edge_injection", "tool"]
    question: str
    should_refuse: bool
    expected_sources: list[str] = []        # doc ids
    key_facts: list[str] = []               # short facts that must be in the answer
    evidence: list[str] = []                # verbatim quotes from the source documents
    reference_answer: str = ""
    expected_tools: list[str] = []
    split: Literal["dev", "holdout"] = "dev"
    generation: dict = {}                   # which prompt/seed produced it


class EvalSet(BaseModel):
    cases: list[EvalCase]
    meta: dict = {}


# ---------------------------------------------------------------- results


FailureCategory = Literal["retrieval_miss", "prompt_defect", "hallucination", "wrong_refusal"]


class CaseResult(BaseModel):
    case_id: str
    category: str
    split: str
    question: str
    should_refuse: bool
    answer: str
    refused: bool
    citations: list[str]
    retrieved_ids: list[str]
    tool_calls: list[dict] = []
    checks: dict = {}
    passed: bool
    failure_category: FailureCategory | None = None
    failure_subtype: str = ""
    failure_reason: str = ""
    latency_s: float = 0.0


class Scorecard(BaseModel):
    label: str
    definition_version: int
    n_cases: int
    passed: int
    pass_rate: float
    ci95: tuple[float, float]
    dev_pass_rate: float
    holdout_pass_rate: float
    by_category: dict[str, dict]
    metrics: dict[str, float]
    failures_by_type: dict[str, int]
