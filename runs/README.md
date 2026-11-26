# Run artifacts (committed evidence)

Each folder is one complete, unattended factory run:

| Folder | What |
|---|---|
| `hr_policy/` | Demo 1 - HR policy assistant over 3 policy PDFs |
| `ship_spares/` | Demo 2 - ship-spares procurement assistant over a catalogue CSV + 3 PDFs |
| `hr_regression/` | Stretch - leave policy changed (v5.0): old eval set re-run on the rebuilt agent |
| `hr_policy/06_human_baseline/` | Stretch - factory vs hand-written agent |

Inside a run folder:

```
00_inputs/          brief, requester notes, document inventory
01_intake/          clarifying questions (max 5) and the answers + their source
02_requirements/    requirements_draft -> groundability report -> final requirements (gaps turned into refusals)
03_agent/           tool_selection.json (with vetoes), prompt candidates, tournament.json, definitions/v0..vN
04_evals/           eval_set.json/.md (generated), dropped_cases.json (rejected by verification), judge_calibration.json
05_iterations/      per-iteration results, scorecards, iteration_log.json/.md, final_results.json
agent_definition.json   the shipped agent (load it with `python -m forgeai chat`)
REPORT.md           honest report: score + CI, what changed, what still fails and why
run_meta.json       models, budget, tokens and time per stage
llm_calls.jsonl     every model call (task, tokens, latency, cache hit)
knowledge/          the documents the agent uses (copied, so the folder is self-contained)
```

Regenerate everything with `bash scripts/run_all_demos.sh`.
