"""Deterministic building blocks: these are what the judge and guards rely on,
so they get direct tests."""

import datetime as dt

from forgeai.docs.loader import load_folder
from forgeai.jsonutil import extract_json
from forgeai.retrieval.index import Retriever
from forgeai.schemas import RetrievalConfig
from forgeai.stages.judge import resolve_fact_present
from forgeai.textutil import fact_present, looks_like_refusal, ngram_overlap, unsupported_numbers, wilson_interval
from forgeai.tools.registry import REGISTRY, calculator, csv_lookup, current_date

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


def test_extract_json_handles_fences_prose_and_trailing_commas():
    assert extract_json('Sure!\n```json\n{"a": 1,}\n```') == {"a": 1}
    assert extract_json('noise {"a": {"b": [1, 2]}} more') == {"a": {"b": [1, 2]}}
    assert extract_json("{'x': True}".replace("'", '"')) == {"x": True}


def test_fact_present_is_strict_on_numbers():
    assert fact_present("21 working days", "You get 21 working days of annual leave.")
    assert not fact_present("21 working days", "You get 24 working days of annual leave.")
    assert fact_present("USD 1,245.50", "The unit price is 1245.5 dollars")
    assert fact_present("10 days", "you can carry forward ten days")
    assert not fact_present("within 60 days", "within 90 days")


def test_unsupported_numbers_flags_invented_values():
    ev = "Hotel limit is INR 7,500 per night in Tier-1 cities."
    assert unsupported_numbers("The limit is INR 7,500.", ev) == []
    assert unsupported_numbers("The limit is INR 8,000.", ev) == [8000.0]


def test_date_fact_resolution():
    today = dt.date(2026, 11, 26)
    assert resolve_fact_present("date:+14", "It should arrive by 10 December 2026.", today)
    assert resolve_fact_present("date:+14", "ETA 2026-12-10", today)
    assert not resolve_fact_present("date:+14", "ETA 2026-12-11", today)


def test_refusal_detection_and_leak_guard():
    assert looks_like_refusal("I'm sorry, I cannot help with that. Please contact HR.")
    assert not looks_like_refusal("You get 21 days of annual leave.")
    assert ngram_overlap("how many days of annual leave do I get per year",
                         "Rule: how many days of annual leave do I get per year -> 21") > 0.5


def test_wilson_interval_is_wide_for_small_samples():
    lo, hi = wilson_interval(18, 23)
    assert lo < 0.65 and hi > 0.9


def test_calculator_is_safe_and_exact():
    assert calculator({"expression": "3 x 1,245.50"}, {})["result"] == 3736.5
    assert calculator({"expression": "round(12000 * 0.95, 2)"}, {})["result"] == 11400.0
    assert "error" in calculator({"expression": "__import__('os').system('ls')"}, {})


def test_current_date_arithmetic():
    r = current_date({"add_days": 14}, {"today": dt.date(2026, 11, 26)})
    assert r["result_date"] == "2026-12-10"


def test_csv_lookup_filters_and_keywords():
    ctx = {"config": {"files": ["spares_catalogue.csv"]}, "knowledge_dir": str(ROOT / "demos/ship_spares/docs")}
    r = csv_lookup({"filters": {"part_no": "ME-FI-5021"}}, ctx)
    assert r["rows"][0]["unit_price_usd"] == "1245.50"
    r = csv_lookup({"query": "Daihatsu fuel injection pump"}, ctx)
    assert r["rows"][0]["part_no"] == "AE-FP-7301"


def test_tool_preconditions_veto_unneeded_tools():
    hr = load_folder(ROOT / "demos/hr_policy/docs")
    ok, _ = REGISTRY["csv_lookup"].precondition("annual leave questions", hr)
    assert not ok, "no CSV in HR docs -> csv_lookup must be vetoed"
    ok, _ = REGISTRY["weather"].precondition("leave, travel claims, hybrid work", hr)
    assert not ok, "an HR agent with a weather tool is a factory defect"
    ok, _ = REGISTRY["weather"].precondition("give the wind forecast for the port", hr)
    assert ok


def test_retriever_finds_policy_passages():
    docs = load_folder(ROOT / "demos/hr_policy/docs")
    r = Retriever(docs, RetrievalConfig(top_k=3))
    hits = r.search("how many days of sick leave do I get")
    assert any("12 days of paid sick leave" in c.text for c, _ in hits)
    hits = r.search("hotel limit per night in Singapore")
    assert hits[0][0].doc_id == "travel_expense_policy.pdf"


def test_placeholder_copied_from_shape_is_rejected_and_retried(tmp_path):
    """Real bug seen with qwen2.5: the model answered {"answer": "string"} (copied the example shape)."""
    import json as _json

    from forgeai.config import Budget, Settings
    from forgeai.llm import LLM, Meter
    from forgeai.schemas import BaseModel

    class A(BaseModel):
        answer: str

    replies = iter([_json.dumps({"answer": "string"}), _json.dumps({"answer": "HR helpdesk, extension 2400"})])
    s = Settings(backend="fake", use_cache=False, cache_dir=str(tmp_path))
    llm = LLM(s, Meter(Budget()), responder=lambda task, m, sc: next(replies))
    assert llm.json([{"role": "user", "content": "who to contact?"}], A, task="t").answer == "HR helpdesk, extension 2400"


# ---------------------------------------------------------------- regressions seen in real qwen2.5:3b runs

def test_computed_table_topics_are_recognised():
    from forgeai.docs.loader import table_computable
    sp = load_folder(ROOT / "demos/ship_spares/docs")
    hr = load_folder(ROOT / "demos/hr_policy/docs")
    assert table_computable("order total", sp)[1] == "calculator"
    assert table_computable("estimate the arrival date if ordered today", sp)[1] == "current_date"
    assert table_computable("live shipment status", sp) == ("", "")
    assert table_computable("order total", hr) == ("", ""), "no CSV -> nothing is computed from a table"


def test_tool_rules_recover_tools_the_model_skipped(tmp_path):
    """Real run: the model attached nothing / misquoted, although the brief needs totals and dates."""
    import json as _json

    from forgeai.config import Budget, Settings
    from forgeai.pipeline import make_context
    from forgeai.schemas import Requirements, Topic
    from forgeai.stages.generator import select_tools

    def responder(task, messages, schema):
        if task == "tool_selection":
            return _json.dumps({"decisions": [{"tool": "csv_lookup", "attach": True, "evidence_quote": "invented words",
                                               "justification": "x"}]})
        return _json.dumps({"tool": "calculator", "attach": False, "evidence_quote": "", "justification": "no"})

    ctx = make_context(tmp_path, Settings(backend="fake", cache_dir=str(tmp_path)), Budget(), responder=responder)
    sp = load_folder(ROOT / "demos/ship_spares/docs")
    req = Requirements(agent_name="a", scope="s", audience="u", tone="t", must_refuse_topics=[],
                       must_answer_topics=[Topic(topic="part number lookup", description="find a part in the spares catalogue"),
                                           Topic(topic="order total", description="price times quantity"),
                                           Topic(topic="arrival date", description="when parts arrive if ordered today")])
    from forgeai.docs.loader import inventory
    bindings, audit = select_tools(ctx, req, "", sp, inventory(sp))
    names = {b.name for b in bindings}
    assert names == {"csv_lookup", "calculator", "current_date"}, audit
    hr = load_folder(ROOT / "demos/hr_policy/docs")
    req_hr = Requirements(agent_name="a", scope="s", audience="u", tone="t", must_refuse_topics=[],
                          must_answer_topics=[Topic(topic="annual leave", description="days per year")])
    assert select_tools(ctx, req_hr, "", hr, inventory(hr))[0] == []


def test_groundability_keeps_uncited_topic_as_partial(tmp_path):
    """Real run: the model said 'supported' for 'leave policy' but forgot to cite -> it must not become a gap."""
    import json as _json

    from forgeai.config import Budget, Settings
    from forgeai.pipeline import make_context
    from forgeai.schemas import Requirements, Topic
    from forgeai.stages.groundability import assess

    ctx = make_context(tmp_path, Settings(backend="fake", cache_dir=str(tmp_path)), Budget(),
                       responder=lambda t, m, s: _json.dumps({"verdict": "supported", "evidence_chunk_ids": [], "missing": ""}))
    req = Requirements(agent_name="a", scope="s", audience="u", tone="t", must_refuse_topics=[],
                       must_answer_topics=[Topic(topic="leave policy", description="annual and sick leave"),
                                           Topic(topic="crew wages", description="pay of seafarers")])
    rep = assess(ctx, req, load_folder(ROOT / "demos/hr_policy/docs"))
    verdicts = {t.topic: t.verdict for t in rep.topics}
    assert verdicts["leave policy"] == "partial"
    assert verdicts["crew wages"] == "unsupported"


def test_note_fallback_finds_plain_answers():
    from forgeai.stages.intake import best_note_line
    notes = (ROOT / "demos/hr_policy/requester_notes.md").read_text()
    assert "friendly" in best_note_line("What is the expected tone for the assistant's responses?", notes).lower()
    assert "hr.helpdesk" in best_note_line("Who should staff contact if the assistant cannot help?", notes)
