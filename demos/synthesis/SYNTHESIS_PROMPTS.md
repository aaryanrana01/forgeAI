# Synthesis prompts for the demo documents

The demo document sets are **LLM-synthesized** (the assignment allows this, provided the synthesis prompts
are committed). The text in `sources/*.md` and the catalogue rows in `build_docs.py` were written by an LLM
(Claude, Anthropic) from the prompts below. `build_docs.py` then renders them into the PDFs and the CSV that
the factory reads. All companies, people, e-mail addresses and part numbers are fictional.

The two sets were designed to be *deliberately different*: unstructured policy prose vs. a structured
catalogue plus contract terms; no tools needed vs. three tools needed; one gap each that the brief asks
for but the documents cannot support (so the groundability guard has something real to catch).

---

## Prompt 1 - HR policy set (3 PDFs)

> You are writing internal policy documents for a fictional Indian shipping company, "BlueWake Shipping
> Pvt. Ltd.", with shore offices in Mumbai and Chennai. Write three policies for shore staff:
> (1) a Leave Policy, (2) a Travel and Expense Policy, (3) a Hybrid Work and Code of Conduct Policy.
>
> Requirements:
> - Each policy has a title, a policy number, version, effective date and owner, then 10-11 numbered
>   sections with short headings. 350-600 words per policy. Plain, realistic corporate English.
> - Use concrete, checkable facts: day counts, money limits in INR/USD, deadlines, grades, portals
>   (the HR portal is called "BlueDesk"), e-mail contacts on the `bluewake.example` domain.
> - Include deliberate cross-references so some questions need two documents: business travel on a
>   public holiday earns a compensatory off defined in the Leave Policy; the home-office allowance follows
>   the expense-claim rules; probation length appears in both leave and hybrid-work rules.
> - State scope limits explicitly: seafarers / crew are NOT covered (their terms are in a separate CBA).
> - Do NOT include anything about salary bands, pay grades' salary ranges or the payroll calendar
>   (salary credit dates) - the brief will ask for these to test the groundability guard.
> - Avoid sub-numbered clauses inside paragraphs (keep sections as plain paragraphs).

## Prompt 2 - HR policy v2 (regression demo)

> Revise the Leave Policy to version 5.0 effective 1 October 2026 with exactly these changes: annual leave
> 21 -> 24 working days; accrual 1.75 -> 2 days per month; carry-forward cap 10 -> 12 days;
> compensatory-off validity 60 -> 90 days. Leave every other sentence unchanged.

(Applied as find-and-replace overrides in `build_docs.py`, so the diff is exact and auditable.)

## Prompt 3 - Ship-spares procurement set (1 CSV + 3 PDFs)

> You are creating procurement data for a fictional ship manager, "Meridian Fleet Management".
>
> (a) A spares catalogue table with ~40 rows and columns: part_no, description, equipment, maker,
> compatible_models, category (A = critical, B, C), unit_price_usd, stock_qty, warehouse (Singapore,
> Rotterdam or Mumbai), supplier (Poseidon Marine Supply, NordMarine Parts AS, Konkan Ship Spares),
> lead_time_days, min_order_qty. Cover main engines (MAN B&W 6S50MC-C, Wartsila RT-flex50-D), auxiliary
> engines (Yanmar 6EY18ALW, Daihatsu 6DK-20), ABB turbochargers, Alfa Laval purifiers, Sperre compressors,
> boilers, pumps, steering gear and an oily water separator. Realistic prices and lead times; part numbers
> with an equipment prefix (ME-, AE-, TC-, PU-, CO-, BO-, PM-, ST-, OW-). Some parts must share a
> description across makers (e.g. "Fuel injection pump" for Yanmar and Daihatsu) to create ambiguity.
>
> (b) A Technical Procurement Policy (9 numbered sections): ShipNet ERP purchase orders, approval limits
> by order value (USD 5,000 / 25,000), three quotations above USD 10,000, preferred supplier by delivery
> port, emergency procurement when off-hire, minimum on-board stock of category A spares, receiving
> inspection deadlines.
>
> (c) Supply terms for two of the three suppliers (Poseidon, NordMarine) - payment days, minimum order
> value, delivery terms, expedite time and surcharge, warranty, returns and restocking fee, and (for one)
> a volume discount. Make the two suppliers' numbers differ so comparison questions are meaningful.
> Do NOT write terms for Konkan Ship Spares (so questions about Konkan's payment terms are a real gap).
> Do NOT include any shipment tracking or order status data (the brief will ask for it).

## Prompt 4 - Briefs and requester notes

> Write a one-paragraph brief that an operations lead would send to an AI team for each assistant. Each
> brief must ask for one thing the documents cannot support (HR: salary bands and payroll calendar;
> spares: live shipment tracking). Then write the requester's notes: audience, tone, must-refuse topics,
> escalation contact, and how they want the uncovered request handled. The notes are used to answer the
> factory's clarifying questions in unattended demo runs - the factory never sees them as instructions,
> only as the requester's answers.
