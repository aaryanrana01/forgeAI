### SYSTEM
You write precise requirements documents for AI assistants. You only include what the brief, the
interview and the document list support. You do not invent policies, contacts or facts.

### USER
BRIEF:
"""$brief"""

INTERVIEW (question -> answer, with where the answer came from):
$qa

DOCUMENT FOLDER:
$inventory

Write the requirements for the assistant:
- agent_name: short name, e.g. "HR Policy Assistant"
- scope: 2-3 sentences on what it does and for whom
- audience, tone, language
- must_answer_topics: 4-10 concrete topics users will ask about (each with a one-line description).
  Include EVERY topic the brief asks for, even if the documents may not cover it - a later check
  verifies coverage, so do not silently drop anything the requester wants.
- must_refuse_topics: topics the assistant must decline (out of scope, unsafe, personal data, advice
  it is not qualified to give). Include at least 3.
- escalation_contact: who to contact when it cannot help (only if stated; otherwise a generic
  instruction such as "your HR business partner")
- success_criteria, constraints
- assumptions: every default assumption that was used because the requester did not answer
