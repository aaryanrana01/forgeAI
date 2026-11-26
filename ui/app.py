"""ForgeAI web UI (stretch goal): run the factory, chat with any produced agent,
and browse run artifacts.

    streamlit run ui/app.py        # or: python -m forgeai ui
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from forgeai.config import Budget, Settings  # noqa: E402
from forgeai.docs.loader import inventory, load_folder  # noqa: E402
from forgeai.llm import LLM, Meter, default_responder, ping  # noqa: E402
from forgeai.pipeline import make_context, run_factory  # noqa: E402
from forgeai.runtime.agent import AgentRuntime, load_definition  # noqa: E402
from forgeai.schemas import QAPair  # noqa: E402
from forgeai.stages.intake import generate_questions  # noqa: E402

RUNS = ROOT / "runs"
DEMOS = {"HR policy assistant (BlueWake)": ROOT / "demos/hr_policy",
         "Ship-spares procurement assistant (Meridian)": ROOT / "demos/ship_spares"}

st.set_page_config(page_title="ForgeAI - the agent that builds agents", layout="wide")


# ------------------------------------------------------------------ sidebar
def settings_from_sidebar() -> Settings:
    st.sidebar.header("Model backend")
    s = Settings()
    backends = ["ollama", "openai", "fake"]
    s.backend = st.sidebar.selectbox("Backend", backends, index=backends.index(s.backend) if s.backend in backends else 0,
                                     help="ollama = local open model; openai = any OpenAI-compatible server; fake = tests only")
    s.model = st.sidebar.text_input("Factory / agent model", s.model)
    s.judge_model = st.sidebar.text_input("Judge model", s.judge_model,
                                          help="A different model family reduces self-preference bias")
    s.embed_model = st.sidebar.text_input("Embedding model (optional, Ollama)", s.embed_model)
    default_url = s.base_url if s.backend == Settings().backend else (
        "http://localhost:11434" if s.backend == "ollama" else os.getenv("FORGE_BASE_URL", "https://api.groq.com/openai/v1"))
    s.base_url = st.sidebar.text_input("Base URL", default_url)
    if s.backend == "openai":
        s.api_key = st.sidebar.text_input("API key", s.api_key, type="password")
    if st.sidebar.button("Check backend"):
        ok, msg = ping(s)
        (st.sidebar.success if ok else st.sidebar.error)(msg)
    if s.backend == "fake":
        st.sidebar.warning("Fake backend: plumbing test only, scores are meaningless.")
    return s


settings = settings_from_sidebar()
tab_build, tab_chat, tab_runs = st.tabs(["🏭 Build an agent", "💬 Chat with an agent", "📊 Runs & reports"])


# -------------------------------------------------------------------- build
with tab_build:
    st.subheader("1. Brief and documents")
    src = st.radio("Input", ["Use a demo", "Upload my own"], horizontal=True)
    brief, docs_dir, notes_default = "", None, ""
    if src == "Use a demo":
        demo = st.selectbox("Demo", list(DEMOS))
        d = DEMOS[demo]
        brief = st.text_area("Brief", (d / "brief.md").read_text(), height=120)
        docs_dir = d / "docs"
        notes_default = (d / "requester_notes.md").read_text()
        st.caption("Documents: " + ", ".join(p.name for p in sorted(docs_dir.iterdir())))
    else:
        brief = st.text_area("Brief (one paragraph)", height=120,
                             placeholder="I need an assistant that answers HR policy questions for shore staff...")
        files = st.file_uploader("Documents (PDF, TXT, MD, CSV, DOCX)", accept_multiple_files=True)
        if files:
            tmp = Path(st.session_state.setdefault("upload_dir", tempfile.mkdtemp(prefix="forge_docs_")))
            for f in tmp.iterdir():
                f.unlink()
            for f in files:
                (tmp / f.name).write_bytes(f.getvalue())
            docs_dir = tmp

    st.subheader("2. Intake interview")
    mode = st.radio("How should the clarifying questions be answered?",
                    ["Answer them here", "From requester notes", "Unattended (default assumptions)"], horizontal=True)
    notes = ""
    if mode == "From requester notes":
        notes = st.text_area("Requester notes", notes_default, height=160)
    if mode == "Answer them here" and brief and docs_dir:
        if st.button("Ask me the questions"):
            ctx = make_context(Path(tempfile.mkdtemp()), settings, Budget())
            with st.spinner("Reading the documents and drafting questions..."):
                st.session_state["questions"] = generate_questions(ctx, brief, inventory(load_folder(docs_dir))).questions
        for i, q in enumerate(st.session_state.get("questions", [])):
            st.text_input(f"Q{i + 1}. {q.question}", key=f"ans_{i}", placeholder=f"(blank = assume: {q.default_assumption})",
                          help=q.why_it_matters)

    st.subheader("3. Factory settings")
    c1, c2, c3, c4 = st.columns(4)
    n_cand = c1.number_input("Prompt candidates", 1, 3, 3)
    iters = c2.number_input("Max iterations", 0, 3, 3)
    tcases = c3.number_input("Tournament cases", 4, 30, 12)
    max_min = c4.number_input("Time budget (min)", 5, 480, 240)
    run_name = st.text_input("Run folder name", f"ui_{time.strftime('%Y%m%d_%H%M%S')}")

    if st.button("🚀 Run the factory", type="primary", disabled=not (brief and docs_dir)):
        preset = None
        if mode == "Answer them here":
            qs = st.session_state.get("questions", [])
            preset = []
            for i, q in enumerate(qs):
                a = (st.session_state.get(f"ans_{i}") or "").strip()
                preset.append(QAPair(question=q.question, answer=a or q.default_assumption or "No preference stated.",
                                     source="requester" if a else "default_assumption"))
        brief_file = Path(tempfile.mkdtemp()) / "brief.md"
        brief_file.write_text(brief)
        lines: list[str] = []
        box = st.empty()
        result: dict = {}

        def worker():
            try:
                result.update(run_factory(
                    brief_file, docs_dir, RUNS / run_name, settings=settings,
                    budget=Budget(max_seconds=int(max_min * 60)),
                    intake_mode="notes" if mode == "From requester notes" else "unattended",
                    requester_notes=notes, preset_qa=preset, n_candidates=int(n_cand),
                    tournament_cases=int(tcases), max_iterations=int(iters), log_fn=lines.append))
            except Exception as e:  # surface errors in the UI
                result["error"] = f"{type(e).__name__}: {e}"

        th = threading.Thread(target=worker, daemon=True)
        th.start()
        while th.is_alive():
            box.code("\n".join(lines[-40:]) or "starting...")
            time.sleep(1.0)
        box.code("\n".join(lines[-60:]))
        if "error" in result:
            st.error(result["error"])
        elif result.get("halted"):
            st.warning(f"Factory stopped: {result.get('reason')}")
        else:
            st.success(f"Shipped v{result['version']} - {result['pass_rate']:.0%} of generated cases pass. "
                       f"See the Runs tab or chat with it.")
            st.markdown((RUNS / run_name / "REPORT.md").read_text())


# --------------------------------------------------------------------- chat
def list_runs() -> list[Path]:
    return sorted([p.parent for p in RUNS.glob("*/agent_definition.json")], key=lambda p: p.name)


with tab_chat:
    runs = list_runs()
    if not runs:
        st.info("No agents yet - build one first (or run `python -m forgeai demo all`).")
    else:
        run = st.selectbox("Agent", runs, format_func=lambda p: p.name)
        d, kdir = load_definition(run / "agent_definition.json")
        st.caption(f"{d.name} · v{d.version} · tools: {[t.name for t in d.tools] or 'none'} · {d.description}")
        key = f"chat_{run.name}"
        hist = st.session_state.setdefault(key, [])
        for m in hist:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                if m.get("meta"):
                    st.caption(m["meta"])
        if q := st.chat_input("Ask the agent..."):
            hist.append({"role": "user", "content": q})
            rt_key = f"rt_{run.name}_{settings.backend}_{settings.model}"
            if rt_key not in st.session_state:
                llm = LLM(settings, Meter(Budget()), responder=default_responder(settings))
                st.session_state[rt_key] = AgentRuntime(d, kdir, llm, embed_model=settings.embed_model)
            with st.spinner("thinking..."):
                r = st.session_state[rt_key].answer(q, history=[{"role": m["role"], "content": m["content"]} for m in hist[:-1]])
            meta = (f"sources: {', '.join(r.citations) or '-'}"
                    + (f" · tools: {', '.join(t['tool'] for t in r.tool_calls)}" if r.tool_calls else "")
                    + (" · refused" if r.refused else "") + (f" · contract: {r.contract_errors}" if r.contract_errors else ""))
            hist.append({"role": "assistant", "content": r.answer, "meta": meta})
            st.rerun()


# --------------------------------------------------------------------- runs
with tab_runs:
    all_runs = sorted([p for p in RUNS.iterdir() if (p / "REPORT.md").exists()]) if RUNS.exists() else []
    if not all_runs:
        st.info("No runs yet.")
    else:
        run = st.selectbox("Run", all_runs, format_func=lambda p: p.name, key="run_browse")
        view = st.radio("Show", ["Report", "Requirements", "Groundability", "Eval set", "Iteration log",
                                 "Agent definition"], horizontal=True)
        files = {"Report": "REPORT.md", "Requirements": "02_requirements/requirements.md",
                 "Groundability": "02_requirements/groundability.md", "Eval set": "04_evals/eval_set.md",
                 "Iteration log": "05_iterations/iteration_log.md"}
        if view == "Agent definition":
            p = run / "agent_definition.json"
            if p.exists():
                st.json(json.loads(p.read_text()))
        else:
            p = run / files[view]
            st.markdown(p.read_text() if p.exists() else "_not produced in this run_")
        zip_path = shutil.make_archive(str(Path(tempfile.gettempdir()) / run.name), "zip", run)
        st.download_button("Download all artifacts (.zip)", Path(zip_path).read_bytes(), file_name=f"{run.name}.zip")
