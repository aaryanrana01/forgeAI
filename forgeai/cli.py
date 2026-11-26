"""Command line interface.

    python -m forgeai doctor
    python -m forgeai build --brief brief.md --docs docs/ --out runs/x [--interactive | --notes notes.md]
    python -m forgeai chat runs/x/agent_definition.json
    python -m forgeai demo all
    python -m forgeai regress --old-run runs/hr_policy --new-docs demos/hr_policy/docs_v2 --out runs/hr_regression
    python -m forgeai compare --run runs/hr_policy --definition baseline/hr_human_agent.json
    python -m forgeai ui
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import Budget, Settings
from .llm import ping

ROOT = Path(__file__).resolve().parent.parent

DEMOS = {
    "hr": {"brief": "demos/hr_policy/brief.md", "docs": "demos/hr_policy/docs",
           "notes": "demos/hr_policy/requester_notes.md", "out": "runs/hr_policy"},
    "spares": {"brief": "demos/ship_spares/brief.md", "docs": "demos/ship_spares/docs",
               "notes": "demos/ship_spares/requester_notes.md", "out": "runs/ship_spares"},
}


def _settings(args) -> Settings:
    s = Settings()
    if getattr(args, "model", None):
        s.model = args.model
        if not os.getenv("FORGE_JUDGE_MODEL"):
            s.judge_model = args.model
    if getattr(args, "judge_model", None):
        s.judge_model = args.judge_model
    if getattr(args, "no_cache", False):
        s.use_cache = False
    return s


def _budget(args) -> Budget:
    b = Budget()
    if getattr(args, "max_tokens", None):
        b.max_tokens = args.max_tokens
    if getattr(args, "max_minutes", None):
        b.max_seconds = int(args.max_minutes * 60)
    return b


def _ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def _approve(path: Path) -> bool:
    print(f"\nHUMAN CHECKPOINT - review the requirements before the agent is generated:\n  {path}\n"
          f"  (a readable version is next to it: requirements.md)")
    print(path.with_suffix(".md").read_text() if path.with_suffix(".md").exists() else path.read_text())
    while True:
        a = _ask("Approve? [y] approve / [e] I edited the JSON file, reload it / [n] stop: ").strip().lower()
        if a in ("", "y", "yes"):
            return True
        if a in ("e", "edit"):
            try:
                json.loads(path.read_text())
                return True
            except json.JSONDecodeError as e:
                print(f"  file is not valid JSON ({e}); fix it and press e again")
        if a in ("n", "no"):
            return False


def cmd_build(args) -> int:
    from .pipeline import run_factory

    mode = "interactive" if args.interactive else ("notes" if args.notes else "unattended")
    notes = Path(args.notes).read_text() if args.notes else ""
    res = run_factory(args.brief, args.docs, args.out, settings=_settings(args), budget=_budget(args),
                      intake_mode=mode, requester_notes=notes, ask=_ask if args.interactive else None,
                      approve=_approve if args.checkpoint else None, n_candidates=args.candidates,
                      tournament_cases=args.tournament_cases, max_iterations=args.iterations, force=args.force)
    print(json.dumps(res, indent=2))
    return 0 if not res.get("halted") else 2


def cmd_demo(args) -> int:
    from .pipeline import run_factory

    names = list(DEMOS) if args.name == "all" else [args.name]
    for n in names:
        d = DEMOS[n]
        res = run_factory(ROOT / d["brief"], ROOT / d["docs"], ROOT / d["out"], settings=_settings(args),
                          budget=_budget(args), intake_mode="notes", requester_notes=(ROOT / d["notes"]).read_text(),
                          n_candidates=args.candidates, tournament_cases=args.tournament_cases,
                          max_iterations=args.iterations)
        print(json.dumps(res, indent=2))
    return 0


def cmd_chat(args) -> int:
    from .runtime.chat import chat_loop

    chat_loop(args.definition, settings=_settings(args), show_json=args.json, once=args.ask)
    return 0


def cmd_regress(args) -> int:
    from .pipeline import regression

    res = regression(args.old_run, args.new_docs, args.out, settings=_settings(args),
                     n_candidates=args.candidates, tournament_cases=args.tournament_cases,
                     max_iterations=args.iterations)
    print(json.dumps(res, indent=2))
    return 0


def cmd_compare(args) -> int:
    """Factory vs human baseline on the factory's eval set."""
    from .pipeline import evaluate_definition
    from .stages.report import pct, scorecard_table
    run = Path(args.run)
    out = Path(args.out or run / "06_human_baseline")
    ev = evaluate_definition(args.definition, run / "04_evals/eval_set.json", out, settings=_settings(args),
                             label="human_baseline", knowledge_dir=run / "knowledge")
    from .schemas import CaseResult
    from .stages.judge import scorecard

    final = [CaseResult.model_validate(r) for r in json.loads((run / "05_iterations/final_results.json").read_text())]
    shipped_version = json.loads((run / "agent_definition.json").read_text()).get("version", 0)
    factory_card = scorecard("factory (shipped)", shipped_version, final)
    factory_res = {r.case_id: r.model_dump() for r in final}
    human = ev["card"]
    human.label = "human baseline"
    factory_card.label = "factory (shipped)"
    wins = [r.case_id for r in ev["results"] if factory_res.get(r.case_id, {}).get("passed") and not r.passed]
    losses = [r.case_id for r in ev["results"] if r.passed and not factory_res.get(r.case_id, {}).get("passed")]
    md = ["# Factory vs human baseline", "", scorecard_table([factory_card, human]), "",
          f"Factory beats the hand-written agent on {len(wins)} case(s): {', '.join(wins) or '-'}  ",
          f"Hand-written agent beats the factory on {len(losses)} case(s): {', '.join(losses) or '-'}", "",
          "| case | category | factory | human | human failure |", "|---|---|---|---|---|"]
    for r in ev["results"]:
        f = factory_res.get(r.case_id, {})
        md.append(f"| {r.case_id} | {r.category} | {'pass' if f.get('passed') else 'fail'} | "
                  f"{'pass' if r.passed else 'fail'} | {(r.failure_reason or '')[:100].replace('|', '/')} |")
    (out / "COMPARISON.md").write_text("\n".join(md) + "\n")
    print(f"factory {pct(factory_card.pass_rate)} vs human {pct(human.pass_rate)} -> {out / 'COMPARISON.md'}")
    return 0


def cmd_doctor(args) -> int:
    s = _settings(args)
    ok, msg = ping(s)
    print(json.dumps(s.describe(), indent=2))
    print(("OK  " if ok else "FAIL ") + msg)
    return 0 if ok else 1


def cmd_ui(args) -> int:
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(ROOT / "ui/app.py")])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="forgeai", description="ForgeAI - the agent that builds agents")
    p.add_argument("--model", help="factory/agent model (overrides FORGE_MODEL)")
    p.add_argument("--judge-model", help="judge model (overrides FORGE_JUDGE_MODEL)")
    p.add_argument("--no-cache", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def loop_opts(sp):
        sp.add_argument("--candidates", type=int, default=3, help="prompt tournament size (1 = no tournament)")
        sp.add_argument("--tournament-cases", type=int, default=12)
        sp.add_argument("--iterations", type=int, default=3, help="max critic-optimizer iterations (spec: 3)")
        sp.add_argument("--max-tokens", type=int, help="token budget for the run")
        sp.add_argument("--max-minutes", type=float, help="wall-clock budget for the run")

    b = sub.add_parser("build", help="run the factory on a brief + document folder")
    b.add_argument("--brief", required=True)
    b.add_argument("--docs", required=True)
    b.add_argument("--out", required=True)
    g = b.add_mutually_exclusive_group()
    g.add_argument("--interactive", action="store_true", help="ask the clarifying questions in this terminal")
    g.add_argument("--notes", help="file with the requester's notes; questions are answered from it")
    b.add_argument("--checkpoint", action="store_true", help="human approves/edits requirements before generation")
    b.add_argument("--force", action="store_true", help="continue even if the brief is mostly not groundable")
    loop_opts(b)
    b.set_defaults(fn=cmd_build)

    d = sub.add_parser("demo", help="run the committed demos end to end")
    d.add_argument("name", choices=["hr", "spares", "all"])
    loop_opts(d)
    d.set_defaults(fn=cmd_demo)

    c = sub.add_parser("chat", help="chat with any produced agent definition")
    c.add_argument("definition")
    c.add_argument("--json", action="store_true")
    c.add_argument("--ask", help="ask one question and exit")
    c.set_defaults(fn=cmd_chat)

    r = sub.add_parser("regress", help="documents changed: rebuild and re-run the old eval set")
    r.add_argument("--old-run", required=True)
    r.add_argument("--new-docs", required=True)
    r.add_argument("--out", required=True)
    loop_opts(r)
    r.set_defaults(fn=cmd_regress)

    cp = sub.add_parser("compare", help="factory vs a hand-written definition on the run's eval set")
    cp.add_argument("--run", required=True)
    cp.add_argument("--definition", required=True)
    cp.add_argument("--out")
    cp.set_defaults(fn=cmd_compare)

    sub.add_parser("doctor", help="check the model backend").set_defaults(fn=cmd_doctor)
    sub.add_parser("ui", help="launch the Streamlit UI").set_defaults(fn=cmd_ui)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
