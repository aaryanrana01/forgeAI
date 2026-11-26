"""End-to-end plumbing tests with the scripted fake model: every stage runs,
every artifact the assignment asks for is written, and the guards fire."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGE_BACKEND", "fake")
    monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "cache"))


def _settings():
    from forgeai.config import Settings
    return Settings()


ARTIFACTS = ["01_intake/questions.json", "02_requirements/requirements.json", "02_requirements/groundability.json",
             "03_agent/tool_selection.json", "03_agent/tournament.json", "03_agent/definitions/v0.json",
             "04_evals/eval_set.json", "04_evals/dropped_cases.json", "04_evals/judge_calibration.json",
             "05_iterations/iteration_log.json", "05_iterations/scorecards.json", "agent_definition.json",
             "REPORT.md", "run_meta.json", "llm_calls.jsonl"]


def test_hr_demo_end_to_end(tmp_path):
    from forgeai.pipeline import run_factory
    from forgeai.schemas import AgentDefinition, EvalSet

    out = tmp_path / "hr"
    res = run_factory(ROOT / "demos/hr_policy/brief.md", ROOT / "demos/hr_policy/docs", out, settings=_settings(),
                      intake_mode="notes", requester_notes=(ROOT / "demos/hr_policy/requester_notes.md").read_text())
    assert not res["halted"]
    for a in ARTIFACTS:
        assert (out / a).exists(), a
    q = json.loads((out / "01_intake/questions.json").read_text())["questions"]
    assert len(q) <= 5, "intake must ask at most 5 questions"
    gr = json.loads((out / "02_requirements/groundability.json").read_text())
    assert any("salary" in g.lower() for g in gr["flagged_gaps"]), "salary bands are not in the docs -> must be flagged"
    d = AgentDefinition.model_validate_json((out / "agent_definition.json").read_text())
    assert not d.tools, "HR agent must not get tools"
    assert any("salary" in t.lower() for t in d.must_refuse_topics)
    es = EvalSet.model_validate_json((out / "04_evals/eval_set.json").read_text())
    assert len(es.cases) >= 20
    cats = {c.category for c in es.cases}
    assert {"answerable", "cross_doc", "out_of_scope", "edge_ambiguous"} <= cats
    for c in es.cases:
        if c.category == "answerable":
            assert c.expected_sources and c.key_facts
    log = json.loads((out / "05_iterations/iteration_log.json").read_text())
    assert len(log) <= 3
    for it in log:
        for p in it["patches"]:
            assert p["rationale"] and p["addressed_cases"] and "before" in p and "after" in p
    assert "WARNING - PLUMBING TEST RUN" in (out / "REPORT.md").read_text()


def test_spares_demo_selects_exactly_the_needed_tools(tmp_path):
    from forgeai.pipeline import run_factory
    from forgeai.schemas import AgentDefinition

    out = tmp_path / "spares"
    run_factory(ROOT / "demos/ship_spares/brief.md", ROOT / "demos/ship_spares/docs", out, settings=_settings(),
                intake_mode="notes", requester_notes=(ROOT / "demos/ship_spares/requester_notes.md").read_text(),
                n_candidates=1, max_iterations=1)
    d = AgentDefinition.model_validate_json((out / "agent_definition.json").read_text())
    names = {t.name for t in d.tools}
    assert "csv_lookup" in names and "weather" not in names
    es = json.loads((out / "04_evals/eval_set.json").read_text())
    assert any(c["category"] == "tool" for c in es["cases"]), "CSV-backed tool cases must be generated"


def test_groundability_halts_on_unsupported_brief(tmp_path, monkeypatch):
    """A brief the documents cannot support must stop the factory at the requirements stage."""
    import forgeai.pipeline as pl
    from forgeai.schemas import QAPair, RefuseTopic, Requirements, Topic

    crypto = Requirements(agent_name="Crypto desk bot", scope="crypto trading desk questions", audience="traders",
                          tone="concise", must_answer_topics=[
                              Topic(topic="token listing fees", description="fees to list a new token"),
                              Topic(topic="margin call thresholds", description="when margin calls trigger"),
                              Topic(topic="staking reward rates", description="annual staking yields")],
                          must_refuse_topics=[RefuseTopic(topic="investment advice", reason="not allowed")])
    monkeypatch.setattr(pl, "run_intake", lambda ctx, brief, inv: (crypto, [QAPair(question="q", answer="a",
                                                                                     source="default_assumption")]))
    brief = tmp_path / "brief.md"
    brief.write_text("Build an assistant for our crypto trading desk.")
    res = pl.run_factory(brief, ROOT / "demos/hr_policy/docs", tmp_path / "bad", settings=_settings())
    assert res["halted"] is True
    report = (tmp_path / "bad/REPORT.md").read_text()
    assert "stopped at the requirements stage" in report
    assert not (tmp_path / "bad/agent_definition.json").exists(), "no agent may be generated for an ungroundable brief"


def test_chat_runner_loads_any_definition(tmp_path, capsys):
    from forgeai.pipeline import run_factory
    from forgeai.runtime.chat import chat_loop

    out = tmp_path / "hr"
    run_factory(ROOT / "demos/hr_policy/brief.md", ROOT / "demos/hr_policy/docs", out, settings=_settings(),
                n_candidates=1, max_iterations=0)
    chat_loop(out / "agent_definition.json", settings=_settings(), once="How many days of sick leave do I get?")
    printed = capsys.readouterr().out
    assert "12 days" in printed and "leave_policy.pdf" in printed


def test_regression_mode_reports_stale_and_broken(tmp_path):
    from forgeai.pipeline import regression, run_factory

    old = tmp_path / "hr"
    run_factory(ROOT / "demos/hr_policy/brief.md", ROOT / "demos/hr_policy/docs", old, settings=_settings(),
                n_candidates=1, max_iterations=0)
    res = regression(old, ROOT / "demos/hr_policy/docs_v2", tmp_path / "reg", settings=_settings(),
                     n_candidates=1, max_iterations=0)
    assert (tmp_path / "reg/REGRESSION_REPORT.md").exists()
    assert "stale" in res


def test_budget_exhaustion_stops_with_honest_report(tmp_path):
    from forgeai.config import Budget
    from forgeai.pipeline import run_factory

    out = tmp_path / "tiny"
    res = run_factory(ROOT / "demos/hr_policy/brief.md", ROOT / "demos/hr_policy/docs", out, settings=_settings(),
                      budget=Budget(max_tokens=5_000))
    assert res["halted"] and "budget" in res["reason"]
    assert "stopped early" in (out / "REPORT.md").read_text()


def test_optimizer_rejects_rules_that_leak_eval_answers(tmp_path):
    """The optimizer must not 'fix' a failure by pasting the expected answer into the prompt."""
    from forgeai.config import Budget
    from forgeai.pipeline import make_context
    from forgeai.schemas import AgentDefinition, CaseResult, EvalCase, PromptSections
    from forgeai.stages.optimizer import Optimizer

    leaky = {"diagnosis": "x", "edits": [
        {"section": "answering_rules", "action": "add", "new_rule": "Employees get 21 working days of annual leave."},
        {"section": "answering_rules", "action": "add", "new_rule": "State durations exactly as written in the context."}]}
    ctx = make_context(tmp_path, _settings(), Budget(), responder=lambda task, m, s: json.dumps(leaky))
    case = EvalCase(id="ans-1", category="answerable", question="How much annual leave do I get?", should_refuse=False,
                    expected_sources=["leave_policy.pdf"], key_facts=["21 working days"])
    opt = Optimizer(ctx, [], [case])
    d = AgentDefinition(name="a", description="d", refusal_message="no",
                        prompt=PromptSections(role="r", scope="s", answering_rules=[], refusal_rules=[]))
    fail = CaseResult(case_id="ans-1", category="answerable", split="dev", question=case.question, should_refuse=False,
                      answer="You get some leave.", refused=False, citations=[], retrieved_ids=[], passed=False,
                      failure_category="prompt_defect", failure_subtype="missing_facts", checks={"facts": {}})
    patches = opt._llm_rule_patch(d, [fail], "prompt_defect", "missing_facts")
    rules = d.prompt.answering_rules
    assert not any("21" in r for r in rules), "leaking rule must be rejected"
    assert any("exactly" in r for r in rules) and len(patches) == 1
