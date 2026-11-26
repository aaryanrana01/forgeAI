# Before you submit - checklist

The code and tests are complete. The **two demo runs must be produced with a real open model** (the
assignment wants real evidence; the fake test model's scores mean nothing and its reports carry a
warning banner). On your Mac:

1. `brew install python@3.12 ollama` (or install the Ollama app), then open Ollama.
2. In the project folder:
   ```bash
   python3.12 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python -m pytest -q                      # 18 tests should pass
   bash scripts/run_all_demos.sh            # ~1.5-3 h on a 16 GB Apple-silicon Mac with qwen2.5:7b
   ```
   On an 8 GB Mac: `FORGE_MODEL=qwen2.5:3b-instruct bash scripts/run_all_demos.sh`.
   Optional, stronger judge (16 GB+): `FORGE_JUDGE_MODEL=llama3.1:8b bash scripts/run_all_demos.sh`.
3. Open `runs/hr_policy/REPORT.md` and `runs/ship_spares/REPORT.md` and check:
   - the groundability gaps were flagged (salary/payroll for HR, shipment tracking for spares)
   - HR has no tools; spares has csv_lookup / calculator / current_date and no weather
   - the eval sets have 20+ cases
   - the "what still fails" section reads sensibly
4. Try the agents: `python -m forgeai chat runs/ship_spares/agent_definition.json`
5. Commit everything **including `runs/`** (but not `.env` or `.forge_cache/`) and push to GitHub:
   ```bash
   git init && git add . && git commit -m "ForgeAI: agent factory with two demo runs"
   git branch -M main && git remote add origin <your-repo-url> && git push -u origin main
   ```

If a run stops early (budget or Ollama crash), just run the same command again: finished model calls are
cached, so it continues quickly.
