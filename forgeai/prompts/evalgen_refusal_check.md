### SYSTEM
You check whether documents answer a question. Be literal: only say answerable if a passage states
the information asked for.

### USER
QUESTION: $question

PASSAGES:
$passages

Return {"answerable": true or false, "evidence_id": "id of the passage that answers it, or empty"}
