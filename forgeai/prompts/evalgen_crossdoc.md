### SYSTEM
You write hard test questions that can only be answered by combining two documents. Every fact
must be copied exactly from the passages.

### USER
PASSAGE A (from "$doc_a"):
"""
$passage_a
"""

PASSAGE B (from "$doc_b"):
"""
$passage_b
"""

THE ASSISTANT: $scope

Write ONE realistic user question whose complete answer needs information from BOTH passages.
If the passages are unrelated, still find a natural question that a user could ask touching both.
- facts_from_a: 1-2 short facts copied exactly from passage A that the answer needs
- facts_from_b: 1-2 short facts copied exactly from passage B that the answer needs
- answer: a correct 2-3 sentence answer combining both

Return {"question": "...", "answer": "...", "facts_from_a": ["..."], "facts_from_b": ["..."]}
