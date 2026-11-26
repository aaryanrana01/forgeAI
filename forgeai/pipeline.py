"""The factory: brief + documents -> tested agent + evidence.

Stages (each writes its artifacts into the run folder):
  00_inputs          brief and document list
  01_intake          clarifying questions and answers
  02_requirements    requirements (draft + final), groundability report
  03_agent           tool selection audit, prompt candidates, tournament, definition versions
  04_evals           generated eval set, rejected candidates, judge calibration
  05_iterations      per-iteration case results, scorecards, iteration log
  agent_definition.json, REPORT.md, run_meta.json, llm_calls.jsonl
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Callable

from .config import Budget, Settings
from .context import RunContext
from .docs.loader import inventory, load_folder
from .llm import LLM, BudgetExceeded, Meter
from .runtime.agent import AgentRuntime, render_system_prompt
from .schemas import AgentDefinition, CaseResult, EvalSet, Requirements
from .stages.evalgen import run_evalgen
from .stages.generator import definition_diff, run_generator
from .stages.groundability import report_markdown as gr_md
from .stages.groundability import run_groundability
from .stages.intake import requirements_markdown, run_intake
from .stages.judge import Judge, run_cases, scorecard
from .stages.optimizer import Optimizer
from .stages.report import build_report, iteration_log_markdown, scorecard_table


class FactoryHalt(RuntimeError):
    pass


def make_context(out_dir: Path, settings: Settings, budget: Budget, *, responder=None, **kw) -> RunContext:
    out_dir.mkdir(parents=True, exist_ok=True)
    if responder is None:
        from .llm import default_responder
        responder = default_responder(settings)
    log_path = out_dir / "llm_calls.jsonl"
    if log_path.exists():
        log_path.unlink()
    meter = Meter(budget, log_path)
    llm = LLM(settings, meter, responder=responder)
    judge = LLM(settings, meter, model=settings.judge_model, responder=responder)
    return RunContext(settings=settings, meter=meter, llm=llm, judge=judge, out_dir=out_dir, **kw)


def _stratified(cases, n: int, seed: int):
    import random

    if len(cases) <= n:
        return list(cases)
    rng = random.Random(seed)
    by: dict[str, list] = {}
    for c in cases:
        by.setdefault(c.category, []).append(c)
    for v in by.values():
        rng.shuffle(v)
    out = []
    while len(out) < n:
        for k in sorted(by):
            if by[k] and len(out) < n:
                out.append(by[k].pop())
    return out


def run_factory(brief_path, docs_dir, out_dir, **kw) -> dict:
    """Run the factory; budget exhaustion or a dead model backend ends the run with an
    honest partial report instead of a stack trace."""
    from .llm import LLMError

    try:
        return _run_factory(brief_path, docs_dir, out_dir, **kw)
    except (BudgetExceeded, LLMError) as e:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        done = sorted(str(p.relative_to(out)) for p in out.rglob("*.json"))
        kind = "budget exhausted" if isinstance(e, BudgetExceeded) else "model backend error"
        (out / "REPORT.md").write_text(
            f"# ForgeAI run stopped early - {kind}\n\n{e}\n\nArtifacts produced before the stop:\n\n"
            + "\n".join(f"- {d}" for d in done) + "\n\nNo agent was shipped from this run.\n")
        print(f"\n✗ run stopped: {kind}: {e}")
        return {"halted": True, "out_dir": str(out), "reason": f"{kind}: {e}"}


def _run_factory(brief_path: str | Path, docs_dir: str | Path, out_dir: str | Path, *,
                settings: Settings | None = None, budget: Budget | None = None,
                intake_mode: str = "unattended", requester_notes: str = "",
                ask: Callable[[str], str] | None = None, approve: Callable[[Path], bool] | None = None,
                n_candidates: int = 3, tournament_cases: int = 12, max_iterations: int = 3,
                eval_plan: dict | None = None, force: bool = False, today: dt.date | None = None,
                log_fn: Callable[[str], None] | None = None, responder=None, preset_qa: list | None = None) -> dict:
    settings = settings or Settings()
    budget = budget or Budget()
    out = Path(out_dir)
    if out.exists():
        for sub in ("01_intake", "02_requirements", "03_agent", "04_evals", "05_iterations", "knowledge"):
            shutil.rmtree(out / sub, ignore_errors=True)
    ctx = make_context(out, settings, budget, responder=responder, intake_mode=intake_mode,
                       requester_notes=requester_notes, ask=ask, approve=approve, log_fn=log_fn,
                       preset_qa=preset_qa)
    meta: dict = {"started": dt.datetime.now().isoformat(timespec="seconds"), "settings": settings.describe(),
                  "budget": vars(budget), "intake_mode": intake_mode, "brief": str(brief_path), "docs": str(docs_dir)}

    # ---------------------------------------------------------------- inputs
    ctx.stage("0. Inputs")
    brief = Path(brief_path).read_text().strip()
    knowledge = out / "knowledge"
    shutil.copytree(docs_dir, knowledge)
    ctx.save_text("00_inputs/brief.md", brief + "\n")
    if requester_notes:
        ctx.save_text("00_inputs/requester_notes.md", requester_notes)
    docs = load_folder(knowledge)
    inv = inventory(docs)
    ctx.save_json("00_inputs/inventory.json", inv)
    ctx.log(f"  {len(docs)} documents: {', '.join(d.doc_id for d in docs)}")

    # ------------------------------------------------- intake + groundability
    req_draft, qa = run_intake(ctx, brief, inv)
    req, gr = run_groundability(ctx, req_draft, docs, brief)
    ctx.save_json("02_requirements/requirements.json", req)
    ctx.save_text("02_requirements/requirements.md", requirements_markdown(req, qa))

    if gr.blocking and not force:
        msg = (f"# ForgeAI stopped at the requirements stage\n\n{gr.summary}\n\nThe documents cannot support most of "
               f"the brief, so generating an agent would mean generating hallucinations.\n\n{gr_md(gr)}\n"
               f"Re-run with --force to build an agent that refuses the uncovered topics anyway.\n")
        ctx.save_text("REPORT.md", msg)
        meta.update({"halted": "groundability", "usage": ctx.meter.snapshot()})
        ctx.save_json("run_meta.json", meta)
        ctx.log("  ✗ halted: brief is not groundable in these documents (use --force to override)", "bold red")
        return {"halted": True, "out_dir": str(out), "reason": gr.summary}

    # ------------------------------------------------------ human checkpoint
    if approve is not None:
        ctx.stage("Human checkpoint")
        path = ctx.out_dir / "02_requirements/requirements.json"
        ok = approve(path)
        if not ok:
            ctx.log("  requester rejected the requirements - stopping", "bold red")
            meta.update({"halted": "checkpoint_rejected", "usage": ctx.meter.snapshot()})
            ctx.save_json("run_meta.json", meta)
            return {"halted": True, "out_dir": str(out), "reason": "requirements rejected at checkpoint"}
        edited = Requirements.model_validate_json(path.read_text())
        meta["checkpoint"] = {"approved": True, "edited": edited != req}
        if edited != req:
            ctx.log("  requirements edited by requester - using edited version")
            req = edited
            ctx.save_text("02_requirements/requirements.md", requirements_markdown(req, qa))

    # ------------------------------------------------------------- generator
    candidates, tool_audit = run_generator(ctx, req, gr, brief, docs, inv, n_candidates=n_candidates)

    # -------------------------------------------------------------- evalgen
    es = run_evalgen(ctx, req, gr, docs, eval_plan)
    dev = [c for c in es.cases if c.split == "dev"]
    holdout = [c for c in es.cases if c.split == "holdout"]

    ctx.stage("5. Judge calibration")
    judge = Judge(ctx, today=today)
    cal = judge.calibrate(es)
    ctx.save_json("04_evals/judge_calibration.json", cal)
    ctx.log(f"  judge accuracy on probes: LLM {cal['llm_judge_accuracy']:.0%}, with code checks "
            f"{cal['combined_accuracy']:.0%}; LLM grounding vote {'on' if cal['llm_grounding_vote_enabled'] else 'OFF'}")

    def runtime_for(d: AgentDefinition) -> AgentRuntime:
        return AgentRuntime(d, knowledge, ctx.llm, embed_model=settings.embed_model, docs=docs, today=today)

    # ------------------------------------------------------------ tournament
    tournament = None
    winner = candidates[0]
    winner_dev_results: list[CaseResult] | None = None
    if len(candidates) > 1:
        ctx.stage("6. Prompt tournament")
        tcases = _stratified(dev, tournament_cases, settings.seed)
        rows = []
        all_res = {}
        for d in candidates:
            style = d.generated_by.get("prompt_style")
            res = run_cases(ctx, runtime_for(d), judge, tcases, f"cand:{style}")
            all_res[style] = res
            ans = [r for r in res if not r.should_refuse and not r.refused]
            rows.append({"style": style, "passed": sum(r.passed for r in res), "n": len(res),
                         "fact_recall": round(sum(r.checks.get("fact_recall", 0) for r in ans) / len(ans), 3) if ans else 0,
                         "prompt_words": len(d.system_prompt.split()), "per_case": {r.case_id: r.passed for r in res}})
        best = max(rows, key=lambda r: (r["passed"], r["fact_recall"], -r["prompt_words"]))
        winner = next(d for d in candidates if d.generated_by.get("prompt_style") == best["style"])
        spread = max(r["passed"] for r in rows) - min(r["passed"] for r in rows)
        note = (f"Winner '{best['style']}'. Spread between best and worst candidate: {spread} case(s) of "
                f"{len(tcases)}" + (" - within noise for this sample size; the choice is weakly supported."
                                    if spread <= 1 else "."))
        tournament = {"n_cases": len(tcases), "case_ids": [c.id for c in tcases], "candidates": rows,
                      "winner": best["style"], "note": note}
        ctx.save_json("03_agent/tournament.json", tournament)
        ctx.log(f"  {note}")
        if len(tcases) == len(dev):
            winner_dev_results = all_res[best["style"]]

    # --------------------------------------------------------- iteration 0
    ctx.stage("7. Baseline evaluation (iteration 0)")
    current = winner.model_copy(deep=True)
    current.version = 0
    current.system_prompt = render_system_prompt(current.prompt, current)
    ctx.save_json("03_agent/definitions/v0.json", current)
    if winner_dev_results is not None:
        results = winner_dev_results + run_cases(ctx, runtime_for(current), judge, holdout, "v0")
    else:
        results = run_cases(ctx, runtime_for(current), judge, dev + holdout, "v0")
    cards = [scorecard("iter 0", 0, results)]
    ctx.save_json("05_iterations/iter_0_results.json", [r.model_dump() for r in results])
    ctx.log(f"  v0: {cards[-1].pass_rate:.0%} overall, dev {cards[-1].dev_pass_rate:.0%}, "
            f"holdout {cards[-1].holdout_pass_rate:.0%}")

    # --------------------------------------------------- critic-optimizer
    ctx.stage("8. Critic-optimizer loop")
    opt = Optimizer(ctx, docs, es.cases)
    log: list[dict] = []
    best_def, best_results, best_card = current, results, cards[-1]
    stop_reason = f"completed {max_iterations} iterations"
    last_round_tokens = None
    for it in range(1, max_iterations + 1):
        dev_res = [r for r in best_results if r.split == "dev"]
        if all(r.passed for r in dev_res):
            stop_reason = f"all dev cases pass after iteration {it - 1}"
            break
        if last_round_tokens and ctx.meter.remaining_tokens() < last_round_tokens * 1.1:
            stop_reason = (f"budget: {ctx.meter.remaining_tokens():,} tokens left, an iteration costs "
                           f"~{last_round_tokens:,}")
            break
        tok0 = ctx.meter.total_tokens
        failures_in: dict[str, int] = {}
        for r in dev_res:
            if not r.passed:
                failures_in[r.failure_category] = failures_in.get(r.failure_category, 0) + 1
        ctx.log(f"  iteration {it}: dev failures {failures_in}")
        try:
            candidate, patches = opt.plan(best_def, dev_res)
        except BudgetExceeded as e:
            stop_reason = f"budget exhausted while planning: {e}"
            break
        if not patches:
            stop_reason = f"no further targeted fix available at iteration {it}"
            break
        for p in patches:
            ctx.log(f"  patch {p.id} [{p.category}] {p.target}: {p.rationale[:140]}")
        try:
            new_results = run_cases(ctx, runtime_for(candidate), judge, dev + holdout, f"v{candidate.version}")
        except BudgetExceeded as e:
            stop_reason = f"budget exhausted during evaluation: {e}"
            break
        card = scorecard(f"iter {it}", candidate.version, new_results)
        before = {r.case_id: r.passed for r in best_results}
        fixed = sorted(r.case_id for r in new_results if r.passed and not before.get(r.case_id))
        broken = sorted(r.case_id for r in new_results if not r.passed and before.get(r.case_id))
        # ship a change only with evidence: strictly better on DEV (holdout never drives decisions)
        kept = card.dev_pass_rate > best_card.dev_pass_rate
        spent = ctx.meter.total_tokens - tok0
        last_round_tokens = spent
        entry = {"iteration": it, "definition_version": candidate.version,
                 "decision": "kept" if kept else "reverted (dev score did not improve)",
                 "failures_in": failures_in, "patches": [p.model_dump() for p in patches],
                 "diff": definition_diff(best_def, candidate),
                 "score_before": {"overall": best_card.pass_rate, "dev": best_card.dev_pass_rate,
                                  "holdout": best_card.holdout_pass_rate},
                 "score_after": {"overall": card.pass_rate, "dev": card.dev_pass_rate, "holdout": card.holdout_pass_rate},
                 "fixed": fixed, "broken": broken, "tokens": spent}
        if kept and card.holdout_pass_rate < best_card.holdout_pass_rate:
            entry["note"] = "dev improved but holdout fell - possible overfitting to dev cases"
        log.append(entry)
        if not kept:
            card.label += " (reverted)"
        cards.append(card)
        ctx.save_json(f"03_agent/definitions/v{candidate.version}.json", candidate)
        ctx.save_json(f"05_iterations/iter_{it}_results.json", [r.model_dump() for r in new_results])
        ctx.log(f"  v{candidate.version}: dev {best_card.dev_pass_rate:.0%} -> {card.dev_pass_rate:.0%} "
                f"(fixed {len(fixed)}, broke {len(broken)}) -> {entry['decision']}", "green" if kept else "yellow")
        gain_pp = (card.dev_pass_rate - best_card.dev_pass_rate) * 100
        if kept:
            best_def, best_results, best_card = candidate, new_results, card
        # budget enforcement: stop when an iteration stops paying for itself. An unproductive iteration
        # ends the loop unless the next one would attack a DIFFERENT failure category (a new fixer may pay).
        efficiency = gain_pp / max(spent / 100_000, 1e-9) if spent else gain_pp
        if it < max_iterations and efficiency < budget.min_gain_pp_per_100k_tokens:
            this_cats = {p.category for p in patches}
            nxt: dict[str, int] = {}
            for r in best_results:
                if r.split == "dev" and not r.passed:
                    nxt[r.failure_category] = nxt.get(r.failure_category, 0) + 1
            nxt_cat = max(nxt, key=nxt.get) if nxt else None
            if nxt_cat is None or nxt_cat in this_cats:
                stop_reason = (f"early stop after iteration {it}: {gain_pp:+.1f} pp dev gain for {spent:,} tokens "
                               f"(< {budget.min_gain_pp_per_100k_tokens} pp per 100k) and the next fix would target "
                               f"the same category ({nxt_cat})")
                break

    # --------------------------------------------------------------- final
    ctx.stage("9. Report")
    final_def = best_def.model_copy(deep=True)
    final_def.knowledge_dir = "knowledge"
    final_def.generated_by.update({"run": out.name, "score": best_card.pass_rate, "final_version": final_def.version})
    ctx.save_json("agent_definition.json", final_def)
    ctx.save_json("05_iterations/iteration_log.json", log)
    ctx.save_text("05_iterations/iteration_log.md", iteration_log_markdown(log))
    ctx.save_json("05_iterations/scorecards.json", [c.model_dump() for c in cards])
    ctx.save_text("05_iterations/scorecard.md", "# Scorecard\n\n" + scorecard_table(cards) + "\n")
    ctx.save_json("05_iterations/final_results.json", [r.model_dump() for r in best_results])
    cal.update({"order_checks": judge.order_checks, "order_disagreements": judge.order_disagreements})
    ctx.save_json("04_evals/judge_calibration.json", cal)
    usage = ctx.meter.snapshot()
    report = build_report(req=req, gr=gr, tool_audit=tool_audit, tournament=tournament, cards=cards, log=log,
                          final_results=best_results, final_def=final_def, calibration=cal, meter=usage,
                          settings=settings.describe(), eval_meta=es.meta, stop_reason=stop_reason,
                          best_label=best_card.label, fake_backend=settings.backend == "fake")
    ctx.save_text("REPORT.md", report)
    meta.update({"finished": dt.datetime.now().isoformat(timespec="seconds"), "stop_reason": stop_reason,
                 "final_version": final_def.version, "final_pass_rate": best_card.pass_rate,
                 "final_holdout_pass_rate": best_card.holdout_pass_rate, "usage": usage, "stages": ctx.events})
    ctx.save_json("run_meta.json", meta)
    ctx.log(f"\n  ✓ shipped v{final_def.version}: {best_card.pass_rate:.0%} pass "
            f"(holdout {best_card.holdout_pass_rate:.0%}) - {out / 'REPORT.md'}", "bold green")
    return {"halted": False, "out_dir": str(out), "pass_rate": best_card.pass_rate, "version": final_def.version,
            "stop_reason": stop_reason}


# ------------------------------------------------------------------ extras
def evaluate_definition(definition_path: str | Path, eval_set_path: str | Path, out_dir: str | Path, *,
                        settings: Settings | None = None, label: str = "eval", today=None, responder=None,
                        knowledge_dir: str | Path | None = None) -> dict:
    """Score any definition (e.g. a hand-written baseline, or a regenerated
    agent) on an existing eval set."""
    from .runtime.agent import load_definition

    settings = settings or Settings()
    out = Path(out_dir)
    ctx = make_context(out, settings, Budget(), responder=responder)
    d, kdir = load_definition(definition_path)
    if knowledge_dir:
        kdir = Path(knowledge_dir)
    es = EvalSet.model_validate_json(Path(eval_set_path).read_text())
    judge = Judge(ctx, today=today)
    cal = judge.calibrate(es)
    rt = AgentRuntime(d, kdir, ctx.llm, embed_model=settings.embed_model, today=today)
    res = run_cases(ctx, rt, judge, es.cases, label)
    card = scorecard(label, d.version, res)
    ctx.save_json(f"{label}_results.json", [r.model_dump() for r in res])
    ctx.save_json(f"{label}_scorecard.json", card)
    return {"card": card, "results": res, "calibration": cal, "usage": ctx.meter.snapshot()}


def regression(old_run: str | Path, new_docs: str | Path, out_dir: str | Path, *, settings: Settings | None = None,
               today=None, responder=None, **factory_kw) -> dict:
    """Documents changed -> rebuild the agent on the new documents, re-run the OLD
    eval set against it, and report what broke. Also flags old test cases whose
    expected facts no longer exist in the new documents (stale tests)."""
    settings = settings or Settings()
    old = Path(old_run)
    out = Path(out_dir)
    brief = old / "00_inputs/brief.md"
    notes_p = old / "00_inputs/requester_notes.md"
    notes = notes_p.read_text() if notes_p.exists() else ""
    rebuild = run_factory(brief, new_docs, out / "rebuilt", settings=settings, intake_mode="notes" if notes else "unattended",
                          requester_notes=notes, today=today, responder=responder, **factory_kw)
    if rebuild.get("halted"):
        return rebuild
    from .textutil import normalize

    new_by_id = {d.doc_id: normalize(d.text) for d in load_folder(new_docs)}
    old_es = EvalSet.model_validate_json((old / "04_evals/eval_set.json").read_text())

    def is_stale(c) -> bool:
        """The old test's evidence changed in the new documents (or its source document is gone)."""
        if c.should_refuse or c.category == "tool" or not c.key_facts:
            return False
        src = " ".join(new_by_id.get(s, "") for s in c.expected_sources)
        if not src:
            return True
        # evidence quotes are verbatim sentences from the old documents: if one is no longer there, the
        # expected answer may be outdated (fact matching across a whole document is too lenient for this)
        return any(normalize(e) not in src for e in c.evidence if e)

    stale = [c.id for c in old_es.cases if is_stale(c)]
    old_res = {r["case_id"]: r for r in json.loads((old / "05_iterations/final_results.json").read_text())}
    ev = evaluate_definition(out / "rebuilt/agent_definition.json", old / "04_evals/eval_set.json", out,
                             settings=settings, label="old_evals_on_new_agent", today=today, responder=responder)
    rows = []
    for r in ev["results"]:
        was = old_res.get(r.case_id, {}).get("passed")
        status = ("stale-test" if r.case_id in stale else
                  "BROKE" if was and not r.passed else "fixed" if (was is False and r.passed) else
                  "still passing" if r.passed else "still failing")
        rows.append({"case_id": r.case_id, "category": r.category, "question": r.question, "was": was,
                     "now": r.passed, "status": status, "failure": r.failure_reason})
    broke = [x for x in rows if x["status"] == "BROKE"]
    md = ["# Regression report", "", f"Old run: `{old}`  \nNew documents: `{new_docs}`", "",
          f"Old eval set ({len(rows)} cases) re-run against the agent regenerated on the new documents: "
          f"**{ev['card'].pass_rate:.0%}** pass (old agent on old docs: "
          f"{sum(1 for v in old_res.values() if v['passed']) / max(1, len(old_res)):.0%}).", "",
          f"- broke: {len(broke)}", f"- stale tests (their evidence sentence changed in the new documents): {len(stale)}",
          f"- fixed: {sum(x['status'] == 'fixed' for x in rows)}", "",
          "Stale tests are expected to fail: the documents changed, so the old expected answer is now wrong. "
          "They are reported separately so they are not mistaken for agent regressions.", "",
          "| case | category | was | now | status | why |", "|---|---|---|---|---|---|"]
    for x in rows:
        md.append(f"| {x['case_id']} | {x['category']} | {x['was']} | {x['now']} | {x['status']} | "
                  f"{(x['failure'] or '')[:120].replace('|', '/')} |")
    (out / "REGRESSION_REPORT.md").write_text("\n".join(md) + "\n")
    (out / "regression.json").write_text(json.dumps({"rows": rows, "stale": stale}, indent=2))
    return {"halted": False, "out_dir": str(out), "broke": len(broke), "stale": len(stale),
            "pass_rate": ev["card"].pass_rate}
