PY ?= python3

.PHONY: setup test docs doctor demos demo-hr demo-spares regress compare ui all clean-runs

setup:            ## create venv and install
	$(PY) -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

test:             ## plumbing tests with the scripted fake model (no GPU needed)
	$(PY) -m pytest -q

docs:             ## re-render the synthesized demo documents
	$(PY) demos/synthesis/build_docs.py

doctor:           ## check the model backend
	$(PY) -m forgeai doctor

demo-hr:
	$(PY) -m forgeai demo hr

demo-spares:
	$(PY) -m forgeai demo spares

demos: demo-hr demo-spares   ## the two required end-to-end demonstrations

regress:          ## stretch: documents changed -> re-run old evals on the rebuilt agent
	$(PY) -m forgeai regress --old-run runs/hr_policy --new-docs demos/hr_policy/docs_v2 --out runs/hr_regression

compare:          ## stretch: factory vs hand-written baseline
	$(PY) -m forgeai compare --run runs/hr_policy --definition baseline/hr_human_agent.json

all: doctor test demos regress compare   ## everything that produces committed evidence

ui:
	$(PY) -m streamlit run ui/app.py

clean-runs:
	rm -rf runs/hr_policy runs/ship_spares runs/hr_regression runs/ui_* runs/smoke_*
