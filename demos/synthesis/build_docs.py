"""Render the synthesized demo documents.

The document TEXT in sources/*.md and the catalogue rows below were written by
an LLM (Claude) from the prompts in SYNTHESIS_PROMPTS.md. This script only
turns them into the files the factory consumes: PDFs (via reportlab) and the
catalogue CSV. All companies, people and e-mail addresses are fictional.

    python demos/synthesis/build_docs.py
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

HERE = Path(__file__).parent
DEMOS = HERE.parent

STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=STYLES["BodyText"], fontSize=10, leading=14, spaceAfter=8)
H1 = ParagraphStyle("h1", parent=STYLES["Title"], fontSize=17, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=STYLES["Heading2"], fontSize=12, spaceBefore=8, spaceAfter=4)
META = ParagraphStyle("meta", parent=STYLES["BodyText"], fontSize=8.5, textColor="#555555", spaceAfter=10)


def render_pdf(src: Path, dst: Path, overrides: dict[str, str] | None = None) -> None:
    text = src.read_text()
    for old, new in (overrides or {}).items():
        assert old in text, f"override target not found in {src.name}: {old!r}"
        text = text.replace(old, new)
    head, body = text.split("\n\n", 1)
    fields = dict(line.split(": ", 1) for line in head.splitlines())
    story = [Paragraph(fields["title"], H1), Paragraph(fields["org"], META), Paragraph(fields["meta"], META)]
    for block in body.strip().split("\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("# "):
            story.append(Paragraph(block[2:], H2))
        else:
            story.append(Paragraph(block, BODY))
    story.append(Spacer(1, 0.5 * cm))
    dst.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(dst), pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm,
                      bottomMargin=2 * cm, title=fields["title"], author="ForgeAI demo (synthetic)").build(story)


# part_no, description, equipment, maker, compatible_models, category, unit_price_usd, stock_qty, warehouse,
# supplier, lead_time_days, min_order_qty
CATALOGUE = [
    ("ME-FI-5021", "Fuel injector nozzle", "Main engine", "MAN B&W", "6S50MC-C; 6S50ME-B", "A", "1245.50", "6", "Singapore", "Poseidon Marine Supply", "14", "2"),
    ("ME-FV-5022", "Fuel valve complete assembly", "Main engine", "MAN B&W", "6S50MC-C", "A", "4380.00", "3", "Singapore", "Poseidon Marine Supply", "21", "1"),
    ("ME-PR-5030", "Piston ring set (one cylinder)", "Main engine", "MAN B&W", "6S50MC-C; 6S50ME-B", "A", "2890.00", "4", "Singapore", "Poseidon Marine Supply", "28", "1"),
    ("ME-CL-5034", "Cylinder liner", "Main engine", "MAN B&W", "6S50MC-C", "A", "18750.00", "1", "Singapore", "Poseidon Marine Supply", "60", "1"),
    ("ME-EV-5040", "Exhaust valve spindle", "Main engine", "MAN B&W", "6S50MC-C; 6S50ME-B", "A", "6120.00", "2", "Rotterdam", "NordMarine Parts AS", "35", "1"),
    ("ME-SA-5045", "Starting air valve", "Main engine", "MAN B&W", "6S50MC-C", "B", "2240.00", "3", "Rotterdam", "NordMarine Parts AS", "30", "1"),
    ("ME-GK-5050", "Cylinder cover gasket kit", "Main engine", "MAN B&W", "6S50MC-C; 6S50ME-B", "B", "385.00", "18", "Singapore", "Poseidon Marine Supply", "10", "5"),
    ("WR-FI-6101", "Fuel injector", "Main engine", "Wartsila", "RT-flex50-D", "A", "1610.00", "5", "Rotterdam", "NordMarine Parts AS", "21", "2"),
    ("WR-PR-6110", "Piston ring set (one cylinder)", "Main engine", "Wartsila", "RT-flex50-D", "A", "3150.00", "2", "Rotterdam", "NordMarine Parts AS", "35", "1"),
    ("WR-SV-6120", "Servo oil pump seal kit", "Main engine", "Wartsila", "RT-flex50-D", "B", "540.00", "9", "Rotterdam", "NordMarine Parts AS", "14", "2"),
    ("AE-FP-7201", "Fuel injection pump", "Auxiliary engine", "Yanmar", "6EY18ALW", "A", "2675.00", "3", "Singapore", "Poseidon Marine Supply", "18", "1"),
    ("AE-NZ-7202", "Injection nozzle tip", "Auxiliary engine", "Yanmar", "6EY18ALW", "A", "212.40", "24", "Singapore", "Poseidon Marine Supply", "7", "6"),
    ("AE-CR-7210", "Connecting rod bearing shell pair", "Auxiliary engine", "Yanmar", "6EY18ALW", "A", "468.00", "12", "Singapore", "Poseidon Marine Supply", "12", "2"),
    ("AE-TC-7220", "Turbocharger cartridge (reconditioned exchange)", "Auxiliary engine", "Yanmar", "6EY18ALW", "B", "5890.00", "1", "Rotterdam", "NordMarine Parts AS", "42", "1"),
    ("AE-HG-7230", "Cylinder head gasket", "Auxiliary engine", "Yanmar", "6EY18ALW", "B", "96.80", "40", "Mumbai", "Konkan Ship Spares", "5", "10"),
    ("AE-FP-7301", "Fuel injection pump", "Auxiliary engine", "Daihatsu", "6DK-20", "A", "2510.00", "2", "Mumbai", "Konkan Ship Spares", "20", "1"),
    ("AE-NZ-7302", "Injection nozzle tip", "Auxiliary engine", "Daihatsu", "6DK-20", "A", "198.00", "30", "Mumbai", "Konkan Ship Spares", "6", "6"),
    ("AE-WP-7310", "Jacket water pump mechanical seal", "Auxiliary engine", "Daihatsu", "6DK-20", "B", "342.00", "8", "Mumbai", "Konkan Ship Spares", "9", "2"),
    ("AE-LF-7315", "Lube oil filter element", "Auxiliary engine", "Daihatsu", "6DK-20", "C", "38.50", "120", "Mumbai", "Konkan Ship Spares", "4", "12"),
    ("TC-NR-8001", "Nozzle ring", "Turbocharger", "ABB", "TPL65-B", "A", "7340.00", "1", "Rotterdam", "NordMarine Parts AS", "45", "1"),
    ("TC-BR-8005", "Bearing bush set", "Turbocharger", "ABB", "TPL65-B", "A", "1890.00", "4", "Rotterdam", "NordMarine Parts AS", "21", "1"),
    ("TC-FL-8010", "Air filter silencer mat", "Turbocharger", "ABB", "TPL65-B; TPL61-A", "C", "164.00", "16", "Rotterdam", "NordMarine Parts AS", "10", "4"),
    ("PU-BS-9001", "Bowl spindle bearing kit", "Fuel oil purifier", "Alfa Laval", "S821; S836", "A", "1420.00", "5", "Singapore", "Poseidon Marine Supply", "14", "1"),
    ("PU-MS-9005", "Major service kit", "Fuel oil purifier", "Alfa Laval", "S821", "B", "2960.00", "3", "Singapore", "Poseidon Marine Supply", "21", "1"),
    ("PU-IS-9006", "Intermediate service kit", "Fuel oil purifier", "Alfa Laval", "S821", "B", "1185.00", "6", "Singapore", "Poseidon Marine Supply", "14", "1"),
    ("PU-OR-9010", "O-ring kit for bowl", "Lube oil purifier", "Alfa Laval", "S836", "C", "145.00", "22", "Mumbai", "Konkan Ship Spares", "6", "2"),
    ("CO-VA-9101", "Suction and delivery valve set", "Main air compressor", "Sperre", "HV2/200", "A", "1275.00", "4", "Rotterdam", "NordMarine Parts AS", "18", "1"),
    ("CO-PR-9105", "Piston ring set (LP and HP stage)", "Main air compressor", "Sperre", "HV2/200", "B", "640.00", "7", "Rotterdam", "NordMarine Parts AS", "18", "1"),
    ("CO-GK-9110", "Overhaul gasket kit", "Main air compressor", "Sperre", "HV2/200", "C", "215.00", "11", "Singapore", "Poseidon Marine Supply", "9", "2"),
    ("BO-BN-9201", "Burner nozzle", "Auxiliary boiler", "Aalborg", "OS-TCi", "B", "310.00", "10", "Rotterdam", "NordMarine Parts AS", "16", "2"),
    ("BO-PC-9205", "Photocell flame sensor", "Auxiliary boiler", "Aalborg", "OS-TCi", "A", "780.00", "3", "Rotterdam", "NordMarine Parts AS", "16", "1"),
    ("BO-GG-9210", "Gauge glass set", "Auxiliary boiler", "Aalborg", "OS-TCi; Mission OL", "B", "265.00", "9", "Singapore", "Poseidon Marine Supply", "11", "2"),
    ("PM-MS-9301", "Mechanical seal", "Main sea water pump", "Shinko", "SVS200-2", "B", "890.00", "4", "Singapore", "Poseidon Marine Supply", "15", "1"),
    ("PM-IM-9305", "Impeller", "Main sea water pump", "Shinko", "SVS200-2", "B", "1740.00", "2", "Singapore", "Poseidon Marine Supply", "25", "1"),
    ("PM-BR-9310", "Bearing set", "Fire pump", "Shinko", "RVP200MS", "A", "420.00", "6", "Mumbai", "Konkan Ship Spares", "10", "2"),
    ("PM-SL-9320", "Gland packing ring set", "Ballast pump", "Naniwa", "FCD-200", "C", "72.00", "35", "Mumbai", "Konkan Ship Spares", "5", "10"),
    ("ST-SE-9401", "Steering gear ram seal kit", "Steering gear", "Rolls-Royce", "SR642", "A", "2380.00", "2", "Rotterdam", "NordMarine Parts AS", "28", "1"),
    ("ST-FL-9405", "Hydraulic return filter element", "Steering gear", "Rolls-Royce", "SR642", "C", "118.00", "14", "Singapore", "Poseidon Marine Supply", "8", "4"),
    ("OW-MB-9501", "Membrane and coalescer pack", "Oily water separator", "RWO", "SKIT/S-DEB 2.5", "B", "1365.00", "3", "Rotterdam", "NordMarine Parts AS", "20", "1"),
    ("OW-OC-9505", "15 ppm oil content meter sensor cell", "Oily water separator", "RWO", "OMD-2008", "A", "2145.00", "2", "Rotterdam", "NordMarine Parts AS", "24", "1"),
]
COLUMNS = ["part_no", "description", "equipment", "maker", "compatible_models", "category", "unit_price_usd",
           "stock_qty", "warehouse", "supplier", "lead_time_days", "min_order_qty"]

# Regression demo: the leave policy is revised (v5.0) - the factory must notice what broke.
LEAVE_V2 = {
    "Version 4.2 | Effective 1 April 2026": "Version 5.0 | Effective 1 October 2026",
    "21 working days of annual leave": "24 working days of annual leave",
    "accrues at 1.75 days": "accrues at 2 days",
    "A maximum of 10 days of unused annual leave": "A maximum of 12 days of unused annual leave",
    "Any balance above 10 days lapses": "Any balance above 12 days lapses",
    "must be used within 60 days of the holiday worked": "must be used within 90 days of the holiday worked",
}


def main() -> None:
    src = HERE / "sources"
    hr, hr2, sp = DEMOS / "hr_policy/docs", DEMOS / "hr_policy/docs_v2", DEMOS / "ship_spares/docs"
    render_pdf(src / "hr_leave_policy.md", hr / "leave_policy.pdf")
    render_pdf(src / "hr_travel_expense_policy.md", hr / "travel_expense_policy.pdf")
    render_pdf(src / "hr_hybrid_work_and_conduct.md", hr / "hybrid_work_and_conduct_policy.pdf")
    render_pdf(src / "hr_leave_policy.md", hr2 / "leave_policy.pdf", LEAVE_V2)
    render_pdf(src / "hr_travel_expense_policy.md", hr2 / "travel_expense_policy.pdf")
    render_pdf(src / "hr_hybrid_work_and_conduct.md", hr2 / "hybrid_work_and_conduct_policy.pdf")
    render_pdf(src / "spares_procurement_policy.md", sp / "procurement_policy.pdf")
    render_pdf(src / "spares_supplier_terms_poseidon.md", sp / "supplier_terms_poseidon.pdf")
    render_pdf(src / "spares_supplier_terms_nordmarine.md", sp / "supplier_terms_nordmarine.pdf")
    with open(sp / "spares_catalogue.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(CATALOGUE)
    for p in sorted(DEMOS.rglob("docs*/*")):
        print(f"wrote {p.relative_to(DEMOS)}")


if __name__ == "__main__":
    main()
