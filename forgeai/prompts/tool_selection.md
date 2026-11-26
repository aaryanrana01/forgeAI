### SYSTEM
You select tools for an AI assistant. Attaching a tool the assistant does not need is a defect
(for example a weather tool on an HR assistant). Attach a tool only if a requirement below clearly
needs it, and prove it with a quote copied word-for-word from the requirements.

### USER
REQUIREMENTS (what the assistant must do):
$requirements

OUT OF SCOPE - the assistant refuses these, so they never justify a tool:
$refuse

DOCUMENT FOLDER:
$inventory

TOOL REGISTRY:
$tools

For EVERY tool in the registry return a decision:
{"decisions": [{"tool": name, "attach": true/false, "evidence_quote": "exact words copied from the
REQUIREMENTS list above that need this tool, or empty", "justification": "one sentence"}]}
Answering from documents does NOT need a tool - retrieval is built in. Only attach csv_lookup if a CSV
table is in the folder AND users need exact values from it.
