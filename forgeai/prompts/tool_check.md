### SYSTEM
You decide whether an AI assistant needs ONE specific tool. Attaching an unneeded tool is a defect,
but missing a needed tool is a defect too. Prove your decision with words copied from the requirements.

### USER
REQUIREMENTS (what the assistant must do):
$requirements

OUT OF SCOPE (never a reason to attach a tool):
$refuse

TOOL: $tool - $description
USE IT WHEN: $when

Does any requirement above need this tool? If yes, copy the requirement line that needs it.
Return {"tool": "$tool", "attach": true or false, "evidence_quote": "requirement line copied exactly, or empty",
"justification": "one sentence"}
