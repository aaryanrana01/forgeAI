### SYSTEM
You write test questions for an AI assistant from source documents. Every fact you give must be
copied exactly from the passage. You never invent information.

### USER
PASSAGE (from document "$doc_id"):
"""
$passage
"""

THE ASSISTANT: $scope
ITS USERS: $audience

Write ONE question that a real user would ask and that THIS passage answers.
- Ask the way a user talks; do not copy the passage's sentences into the question.
- The question must not contain the answer, and must not mention "the passage" or "the document"
  (real users do not know which document holds the answer).
- key_facts: 1 to 3 short facts (2 to 8 words each) COPIED EXACTLY from the passage that any correct
  answer must state. Prefer numbers, durations, amounts, limits, deadlines and named procedures.
- evidence_quote: the sentence from the passage that contains the answer, copied exactly.
- answer: a correct 1-2 sentence answer.
Avoid these already-used questions: $avoid

Return {"question": "...", "answer": "...", "key_facts": ["..."], "evidence_quote": "..."}
