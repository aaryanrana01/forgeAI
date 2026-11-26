# Groundability report

3 supported, 2 partial, 2 unsupported (groundable fraction 57%). Unsupported topics will be REFUSED by the agent instead of answered: payroll calendar; tell employees their salary band; salary bands and payroll dates.

| Topic | Verdict | Evidence | Note |
|---|---|---|---|
| leave policy | supported | leave_policy.pdf#4, leave_policy.pdf#2, leave_policy.pdf#5, leave_policy.pdf#3, leave_policy.pdf#1, leave_policy.pdf#0 | none |
| travel and expense policy | supported | travel_expense_policy.pdf#2, travel_expense_policy.pdf#3, travel_expense_policy.pdf#1, travel_expense_policy.pdf#0, leave_policy.pdf#3, hybrid_work_and_conduct_policy.pdf#1 | none |
| payroll calendar | unsupported | - | None of the provided excerpts contain any information related to payroll calendars or date salary is credited each month. |
| working from home | partial (guard) | hybrid_work_and_conduct_policy.pdf#0 | guard: model said unsupported, but excerpt hybrid_work_and_conduct_policy.pdf#0 contains every word of the topic - changed to partial. working from home policies, such as core hours, equipment and allowances, and information security measures. |
| hybrid work and conduct policy | supported | hybrid_work_and_conduct_policy.pdf#1, hybrid_work_and_conduct_policy.pdf#2, hybrid_work_and_conduct_policy.pdf#3, hybrid_work_and_conduct_policy.pdf#0, hybrid_work_and_conduct_policy.pdf#1 | none |
| answer leave policy questions | partial | leave_policy.pdf#5, leave_policy.pdf#2, leave_policy.pdf#1 | 6. Travel on Weekends and Public Holidays, 9. Travel Advance, 10. Non-Reimbursable Items, 4. Carry Forward and Encashment, 5. Sick Leave, 3. Annual Leave, 7. Local Conveyance, 8. Expense Claims |
| tell employees their salary band | unsupported | - | tell employees their salary band |
| salary bands and payroll dates | unsupported | - | requested in the brief; intake already set it to REFUSE. salary bands and payroll dates |

## Flagged gaps
The brief asks for these but the documents cannot support them. The agent is configured to refuse them rather than guess:
- payroll calendar
- tell employees their salary band
- salary bands and payroll dates
