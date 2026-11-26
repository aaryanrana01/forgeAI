# ForgeAI — the agent that builds agents

ForgeAI takes a **one-paragraph brief** and a **folder of documents**. With no further help, it builds a
working agent and **tests it the way a QA engineer would**. Then it improves its own output until the
evals pass or the budget runs out, and hands back the agent with an **honest report** (it does not claim
100%).

```
brief + docs ──► intake interview ──► groundability guard ──► agent generator ──► eval generator
                (≤5 questions)       (flags gaps, can stop)   (prompt, retrieval,   (≥20 cases, every
                                                               tools, contract)      fact verified by code)
                                                                      │
             REPORT.md ◄── critic–optimizer loop (≤3 iterations) ◄── judge (code checks + calibrated LLM judge)
             agent_definition.json   classify → targeted patch → re-run → keep only if dev improves
```

Every stage runs on a **small local open model** (default `qwen2.5:7b-instruct` through Ollama). Small
models make mistakes, so the factory does not trust its own output. Each step a model does is checked by
code:

| The model does… | …and code checks it |
|---|---|
| says a topic is covered by the documents | the cited passage must exist and really overlap the topic, otherwise the verdict is downgraded |
| picks tools | its evidence quote must exist in the requirements, and the tool's precondition must hold (no CSV → no `csv_lookup`, no weather need → no weather tool) |
| writes test cases | every key fact must be found in the source passage; refusal tests are dropped if the documents actually answer them; table answers are **computed by code** from the CSV |
| judges answers | every number in an answer must exist in the evidence (code); the judge's grounding vote is turned off if it fails a calibration probe |
| writes prompt fixes | fixes that paste test questions or expected facts into the prompt are rejected |
| claims an improvement | a change is kept only if the **dev** score really rises; a **holdout** split the optimizer never sees catches overfitting |

---

## 1. Quick start (macOS / Linux)

Needs **Python 3.10 or newer** (macOS's built-in `python3` is often 3.9; use `brew install python@3.12`
and then `python3.12 -m venv .venv`).

```bash
# 1) Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) Local open model (install Ollama from https://ollama.com/download or `brew install ollama`)
ollama pull qwen2.5:7b-instruct          # 4.7 GB; on an 8 GB Mac use qwen2.5:3b-instruct
cp .env.example .env                     # optional: change models / budget here
python -m forgeai doctor                 # checks the backend is reachable and the model is pulled

# 3) Tests (use a scripted fake model; no GPU needed, ~2 s)
python -m pytest -q

# 4) The two required end-to-end demonstrations + stretch evidence (commit runs/ afterwards)
bash scripts/run_all_demos.sh
```

**How long it takes.** A full run (3 prompt candidates, ≥20 cases, up to 3 iterations) makes about 250–400
model calls. On an Apple-silicon Mac with `qwen2.5:7b-instruct`, expect **40–80 minutes per demo**. With
`qwen2.5:3b-instruct` it takes about half as long (lower quality). Re-runs are much faster because every
call is cached on disk (temperature 0, fixed seed).

### Run it on a new brief (what the reviewers will do)

```bash
# requester answers the ≤5 clarifying questions live in the terminal, and approves the requirements
python -m forgeai build --brief their_brief.md --docs their_folder/ --out runs/review --interactive --checkpoint

# fully unattended: questions are answered with explicit default assumptions (listed in the report)
python -m forgeai build --brief their_brief.md --docs their_folder/ --out runs/review

# faster, for a live session: 1 prompt candidate, 2 iterations, 30-minute budget
python -m forgeai build --brief b.md --docs d/ --out runs/review --candidates 1 --iterations 2 --max-minutes 30

# chat with whatever was produced
python -m forgeai chat runs/review/agent_definition.json
```

Web UI (factory + chat runner + run browser): `python -m forgeai ui` (runs `streamlit run ui/app.py`).

---

## 2. How each core requirement is met

| # | Requirement | Where | How |
|---|---|---|---|
| 1 | **Intake interviewer** | `forgeai/stages/intake.py`, `prompts/intake_*.md` | Reads the brief and a document inventory (headings, key terms, CSV columns). Asks **at most 5** questions; the cap is enforced in code, not left to the model. Each question has a *why* and a *default assumption*. Answers come from the terminal (`--interactive`), the requester's notes (`--notes`) or the defaults. Every default that is used is written into the requirements as an **assumption**. Output: `requirements.json/.md` with scope, audience, tone, must-answer and must-refuse topics. |
| 2 | **Groundability guard** | `stages/groundability.py` | For each must-answer topic it retrieves evidence and asks the model *supported / partial / unsupported*. Then **code checks the verdict**: no valid citation → unsupported; cited text barely mentions the topic → partial. Unsupported topics are moved to the refusal list, so the agent says "not covered, contact X" instead of guessing. If less than 50% of the brief can be answered from the documents, the factory **stops before generating an agent** (`--force` to override). |
| 3 | **Agent generator** | `stages/generator.py`, `schemas.py::AgentDefinition` | Produces one declarative JSON definition: system prompt (stored as editable sections so it can be patched), retrieval settings worked out from document statistics (with the reasoning written down), tools, refusal message and **output contract** (JSON: `answer`, `citations`, `refused`, `refusal_reason`). Tools: the model proposes and quotes the requirement that needs the tool; code vetoes the tool if the quote is invented or the precondition fails. The full audit is in `03_agent/tool_selection.json`. |
| 4 | **Eval generator** | `stages/evalgen.py`, `prompts/evalgen_*.md` | Builds ≥20 cases **from the documents**: answerable (source document + key facts + verbatim evidence), cross-document (a verified fact from each document), out-of-scope (must-refuse topics, groundability gaps, near-domain, off-domain), edge cases (messy paraphrases, prompt-injection attempts), and for CSV data, lookup/total/date cases whose answers are **calculated by code**. Rejected candidates and the reason for each are saved in `dropped_cases.json`. The generation prompts are committed in `forgeai/prompts/`, and their hashes are stored with each eval set. |
| 5 | **Judge** | `stages/judge.py` | Code checks run first: contract validity, refusal flag, per-fact matching, **every number in the answer must appear in the evidence**, retrieval hit. The LLM judge is used only where text matching cannot decide (paraphrased facts, claim support). Bias defences are listed in [section 4](#4-judge-defences). |
| 6 | **Critic–optimizer loop** | `stages/critic.py`, `stages/optimizer.py`, `pipeline.py` | Each failure is put into exactly one category (retrieval miss / prompt defect / hallucination / wrong refusal) by fixed rules, with a reason attached. The most common category gets a **targeted patch**: retrieval → test parameter variants and pick the one with the best measured hit-rate; hallucination → add a grounding rule; wrong refusal → refusal topic, relevance floor or "answer when the context covers it" rule; prompt defect → 1–2 model-written rule edits behind an anti-leak guard. **Max 3 iterations.** Every patch is logged with target, before/after, rationale, the cases it addresses, the scores before and after, and the cases fixed or broken by it. |
| 7 | **Honest reporting** | `stages/report.py` → `REPORT.md` | Pass rate **with a 95% confidence interval**, dev vs untouched holdout (with an overfitting warning), per-iteration scorecard, the tournament spread with a "within noise" note, **every remaining failure with its category and reason**, judge calibration results, and the limitations of the eval set. A 100% score triggers a warning. |
| 8 | **Runnable product** | `runtime/agent.py`, `runtime/chat.py`, `ui/app.py` | A general-purpose runtime that loads *any* definition: retrieval → (optional) tool-planning loop → contract-constrained answer → contract validation with one repair retry. CLI chat (`python -m forgeai chat …`) and a Streamlit chat tab. |
| 9 | **Two full demonstrations** | `demos/`, `runs/` | **HR policy assistant**: 3 policy PDFs, no tools needed, gap = salary bands / payroll calendar. **Ship-spares procurement assistant**: catalogue CSV + procurement policy + 2 supplier agreements, needs `csv_lookup` + `calculator` + `current_date` (never `weather`), gap = live shipment tracking. `scripts/run_all_demos.sh` produces and saves every artifact. |

### Stretch goals implemented

| Stretch goal | How |
|---|---|
| **Prompt tournament** | 3 system-prompt styles (concise / procedural / persona) scored on a stratified dev subset. The winner is chosen by absolute pass rate (not a pairwise LLM preference); the report says when the spread is within noise. |
| **Budget enforcement** | Token, time and call budget per run (`--max-tokens`, `--max-minutes`, `.env`). The loop stops when an iteration "stops paying for itself" (dev gain per 100k tokens below a threshold, with the next fix targeting the same category), or when the remaining budget can't pay for another iteration. Running out of budget ends with a partial report, not a crash. |
| **Human checkpoint** | `--checkpoint`: the requester reads `requirements.md` and approves, edits the JSON and reloads it, or stops the run. |
| **Factory vs human baseline** | `baseline/hr_human_agent.json` (hand-written) vs the factory agent on the same eval set → `COMPARISON.md`, listing where each one wins. |
| **Regression mode** | `forgeai regress`: the leave policy changes (v5.0: 21→24 days and more) → rebuild the agent → re-run the **old** eval set → `REGRESSION_REPORT.md`. **Stale tests** (evidence changed) are reported separately from **real regressions**. |
| **UI and hosting** | Streamlit UI (build with live log, answer intake questions in a form, chat, browse and download runs). It can be hosted on Streamlit Community Cloud / HF Spaces with `FORGE_BACKEND=openai` pointing at a hosted open model (set the key as a secret). |

---

## 3. Demo data

Both document sets are synthetic and fictional (BlueWake Shipping, Meridian Fleet Management). The
assignment allows LLM-synthesized documents; the prompts used are committed in
`demos/synthesis/SYNTHESIS_PROMPTS.md`, the source text is in `demos/synthesis/sources/`, and
`python demos/synthesis/build_docs.py` re-renders the PDFs and the CSV.

The two sets are deliberately different:

| | HR policy | Ship spares |
|---|---|---|
| Data | 3 prose PDFs | 1 CSV table (40 parts) + 3 PDFs |
| Tools the brief needs | none | csv_lookup, calculator, current_date |
| Gap the guard must catch | salary bands, payroll calendar | live shipment tracking |
| Cross-document cases | holiday travel → comp-off (travel + leave policy) | procurement policy × supplier terms (e.g. expedite surcharge vs approval limits) |
| Regression data | `docs_v2/` (leave policy v5.0) | – |

`requester_notes.md` holds the requester's answers, used to answer the factory's clarifying questions in
unattended demo runs. The factory sees these notes only as answers, never as instructions.

---

## 4. Judge defences

| Known failure mode | Defence |
|---|---|
| **Position bias** | No pairwise "which answer is better" grading anywhere (the tournament compares absolute pass rates). When a claim-support check comes back negative, it is repeated with the evidence in **reverse order** and the two scores are averaged; how often the verdict flips is reported. |
| **Self-preference** | The judge can be a different model family (`FORGE_JUDGE_MODEL`, e.g. `llama3.1:8b`). It never sees the system prompt, the agent's name or which model wrote the answer. It grades against **facts taken from the documents**, not its own idea of a good answer. If the two models are the same family, the report says so. |
| **Verbosity bias** | Grounding is the **fraction** of claims supported, so padding can only lower it. Correctness is a yes/no per expected fact. Numbers are checked by code, so a confident long answer with one wrong number fails. |
| **A judge that is simply wrong** | **Calibration probe** before grading: a correct answer, the same answer padded with a made-up claim, and one with a wrong number. If the LLM judge scores below 60% on these, its grounding vote is switched **off** for the run and only code checks decide. Results are in `judge_calibration.json` and the report. |

---

## 5. Repository layout

```
forgeai/
  pipeline.py            orchestrates the stages, tournament, loop, regression, evaluation
  llm.py                 Ollama / OpenAI-compatible client: schema-constrained JSON, repair retries, cache, budget meter
  schemas.py             every artifact's data contract (pydantic) + tolerant parsing for small models
  textutil.py            deterministic fact / number / refusal matching used by the judge and guards
  docs/loader.py         PDF, TXT, MD, CSV, DOCX, JSON loading + inventory
  retrieval/             paragraph-aware chunking with section headings; BM25 (+ optional hybrid, query expansion)
  tools/registry.py      csv_lookup, calculator (safe AST), current_date, weather (open-meteo, keyless)
  stages/                intake, groundability, generator, evalgen, judge, critic, optimizer, report
  runtime/               generic agent runtime + CLI chat runner
  prompts/               ALL factory prompts (including the eval-generation prompts)
  testing/fake_llm.py    scripted stand-in model for tests (never used for committed demo runs)
ui/app.py                Streamlit UI
demos/                   briefs, requester notes, documents, synthesis prompts
baseline/                hand-written HR agent for the factory-vs-human comparison
runs/                    committed run artifacts (see runs/README.md)
tests/                   unit tests for the code checks + end-to-end pipeline tests
```

---

## 6. Design decisions and known limitations

- **Code checks over LLM opinions wherever possible.** The model is used to *propose*; code is used to
  *verify*. It costs more code, but it is the only way to trust a pipeline built on a 7B model.
- **BM25 by default.** It needs no extra model, is deterministic, and is strong on policy text full of
  specific terms. Hybrid retrieval with Ollama embeddings is available (`FORGE_EMBED_MODEL=nomic-embed-text`)
  and the optimizer only switches to it if it measurably improves retrieval hit-rate.
- **Holdout split.** About 30% of the cases are never shown to the optimizer. Paraphrase cases stay in their
  parent's split so they cannot leak from dev into holdout.
- **The eval set is generated by the same factory**, so it can share the factory's blind spots. The report
  says this. Passages that were not sampled are untested, and paraphrase cases are not independent evidence.
- **Small samples.** 20–30 cases give a wide confidence interval; the report shows it rather than hiding it.
- **Tool cases with dates** are resolved against the day the eval runs.

## 7. Using a hosted open model instead of Ollama

Any OpenAI-compatible endpoint works (Groq, OpenRouter, LM Studio, vLLM, llama.cpp server):

```bash
export FORGE_BACKEND=openai FORGE_BASE_URL=https://api.groq.com/openai/v1 FORGE_API_KEY=... FORGE_MODEL=llama-3.1-8b-instant
python -m forgeai doctor
```

Free tiers have rate limits; the client backs off on HTTP 429 and retries.
