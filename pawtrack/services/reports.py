"""
PawTrack - report building
==========================
The filterable/exportable reports shown under Reports: population,
vaccination, overdue, upcoming, inventory and vaccine stock. The same
structure is rendered on screen, exported as CSV and printed as PDF.
"""
import io
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from flask import send_file, url_for

from ..config import BASE_DIR
from ..helpers import days_until, fmt_date, money, now_str
from ..storage import get_settings, load
from .analytics import tally
from .inventory import enriched_inventory
from .vaccinations import all_vax_rows

REPORTS = {
    "population": "Animal Population", "vaccination": "Vaccination",
    "overdue": "Overdue Vaccination", "upcoming": "Upcoming Vaccination", "inventory": "Inventory",
    "vaccine_stock": "Vaccine Stock",
}
# Reports are shown in three groups on the Reports page.
REPORT_GROUPS = [          # (tab title, icon, report kinds) - shown as the big tabs on the Reports page
    ("Vaccination Reports", "syringe", ["vaccination", "overdue", "upcoming"]),
    ("Animal Reports", "paw", ["population"]),
    ("Inventory Reports", "box", ["inventory", "vaccine_stock"]),
]
REPORT_TAB_LABELS = {"vaccination": "All Vaccinations", "overdue": "Overdue Vaccination",
                     "upcoming": "Upcoming Vaccination", "population": "Animal Population",
                     "inventory": "Inventory", "vaccine_stock": "Vaccine Stock"}
FILTER_LABELS = {"date_from": "From", "date_to": "To", "species": "Species", "breed": "Breed", "sex": "Sex",
                 "ownership": "Ownership", "status": "Vaccination status", "vaccine": "Vaccine",
                 "category": "Category", "stock_status": "Stock status", "exp_status": "Expiration status"}
REPORT_FILTERS = {
    "population": ["date_from", "date_to", "species", "breed", "sex", "ownership"],
    "vaccination": ["date_from", "date_to", "species", "breed", "sex", "ownership", "status", "vaccine"],
    "overdue": ["date_from", "date_to", "species", "breed", "sex", "ownership", "vaccine"],
    "upcoming": ["date_from", "date_to", "species", "breed", "sex", "ownership", "vaccine"],
    "inventory": ["category", "stock_status", "exp_status"],
    "vaccine_stock": ["stock_status", "exp_status"],
}


def animal_matches(a, args):
    return ((not args.get("species") or a["species"] == args["species"])
            and (not args.get("breed") or args["breed"].lower() in a["breed"].lower())
            and (not args.get("sex") or a["sex"] == args["sex"])
            and (not args.get("ownership") or a["ownership_status"] == args["ownership"]))


def summary_icon(label):
    """Icon name for a summary card on the Reports page, chosen from its label."""
    l = label.lower()
    for words, name in ((("overdue", "expired", "out of stock"), "alert"), (("due today", "near", "expiring"), "calclock"),
                        (("completed",), "check"), (("upcoming", "earliest"), "clock"), (("low stock",), "alertc"),
                        (("animals", "owned", "stray", "species"), "paw"), (("value",), "chart"),
                        (("units", "vaccine products"), "box")):
        if any(w in l for w in words):
            return name
    return "file"


def build_report(kind, args):
    """Return {'title', 'sections': [{'title','headers','rows'}]} for screen, CSV and PDF."""
    sections = []
    if kind == "population":
        animals = [a for a in load("animals") if animal_matches(a, args)
                   and (not args.get("date_from") or a["registration_date"] >= args["date_from"])
                   and (not args.get("date_to") or a["registration_date"] <= args["date_to"])]
        sections.append({"title": "Summary", "headers": ["Measure", "Value"], "rows": [["Total animals", len(animals)]]})
        summary = [("Total animals", len(animals), ""),
                   ("Owned", sum(1 for a in animals if a["ownership_status"] == "Owned"), ""),
                   ("Stray", sum(1 for a in animals if a["ownership_status"] == "Stray"), ""),
                   ("Species", len({a["species"] for a in animals}), "")]
        for title, key in (("By species", "species"), ("By breed", "breed"), ("By sex", "sex"),
                           ("By ownership", "ownership_status")):
            sections.append({"title": title, "headers": [title.replace("By ", "").title(), "Animals"],
                             "rows": [[k, v] for k, v in tally(a[key] for a in animals).items()]})
        sections.append({"title": "Animal Records", "primary": True,
                         "meta": [{"href": url_for("animal_view", animal_id=a["animal_id"]),
                                   "search": " ".join([a["animal_id"], a["animal_name"], a["species"], a["breed"],
                                                       a["owner_name"] or ""]).lower()} for a in animals],
                         "headers": ["Animal ID", "Name", "Species", "Breed", "Sex", "Age", "Ownership", "Owner", "Registered"],
                         "rows": [[a["animal_id"], a["animal_name"], a["species"], a["breed"], a["sex"], a["age"],
                                   a["ownership_status"], a["owner_name"] or "-", a["registration_date"]]
                                  for a in animals]})
    elif kind in ("vaccination", "overdue", "upcoming"):
        rows = []
        stat_rows = []
        meta = []
        for r in all_vax_rows():
            if not animal_matches(r["animal"], args):
                continue
            if args.get("vaccine") and args["vaccine"].lower() not in r["vaccine_name"].lower():
                continue
            if args.get("date_from") and r["date_administered"] < args["date_from"]:
                continue
            if args.get("date_to") and r["date_administered"] > args["date_to"]:
                continue
            if kind == "overdue" and not (r["is_current"] and r["status"] == "Overdue"):
                continue
            if kind == "upcoming" and not (r["is_current"] and r["status"] == "Upcoming"):
                continue
            if kind == "vaccination" and args.get("status") and r["status"] != args["status"]:
                continue
            stat_rows.append(r)
            days = days_until(r.get("next_due_date"))
            note = ("" if days is None else "Due today" if days == 0 else
                    f"{-days} day{'s' if days != -1 else ''} overdue" if days < 0 else
                    f"in {days} day{'' if days == 1 else 's'}")
            meta.append({"href": url_for("animal_view", animal_id=r["animal_id"]),
                         "notify": url_for("animal_notify", animal_id=r["animal_id"]),
                         "status": r["status"], "note": note,
                         "search": " ".join([r["animal_id"], r["animal"]["animal_name"], r["animal"]["species"],
                                             r["vaccine_name"], r["animal"].get("owner_name") or ""]).lower()})
            rows.append([r["animal_id"], r["animal"]["animal_name"], r["animal"]["species"], r["vaccine_name"],
                         r["date_administered"], r.get("next_due_date") or "-", r["status"]])
        count = lambda st: sum(1 for r in stat_rows if r["status"] == st)
        if kind == "vaccination":
            summary = [("Total Records", len(stat_rows), ""), ("Overdue", count("Overdue"), "bad" if count("Overdue") else ""),
                       ("Due Today", count("Due Today"), "warn" if count("Due Today") else ""),
                       ("Completed", count("Completed"), "good")]
        else:
            nxt = min((r["next_due_date"] for r in stat_rows if r.get("next_due_date")), default="")
            summary = [("Total Records", len(stat_rows), "bad" if kind == "overdue" and stat_rows else ""),
                       ("Animals affected", len({r["animal_id"] for r in stat_rows}), ""),
                       ("Earliest due date", fmt_date(nxt) if nxt else "-", "")]
        sections.append({"title": REPORTS[kind] + " Records", "primary": True, "meta": meta,
                         "headers": ["Animal ID", "Animal", "Species", "Vaccine", "Date Administered", "Due Date", "Status"],
                         "rows": rows})
    elif kind == "vaccine_stock":
        items = [i for i in enriched_inventory() if i["category"] == "Vaccines"
                 and (not args.get("stock_status") or i["stock_status"] == args["stock_status"])
                 and (not args.get("exp_status") or i["expiry_status"] == args["exp_status"])]
        items.sort(key=lambda i: i["item_name"].lower())
        n = lambda f: sum(1 for i in items if f(i))
        usable = sum(i["quantity"] for i in items if i["expiry_status"] != "Expired")
        expired_units = sum(i["quantity"] for i in items if i["expiry_status"] == "Expired")
        total_value = float(sum(Decimal(str(i["value"])) for i in items))
        head = ["Vaccine", "Type", "Manufacturer / brand", "Batch / lot", "Quantity", "Minimum stock", "Unit cost",
                "Total value", "Expiration date", "Stock status", "Expiration status"]
        row = lambda i: [i["item_name"], i.get("vaccine_type") or "-", i.get("manufacturer") or "-",
                         i.get("batch_number") or "-", f"{i['quantity']} {i['unit']}", i["min_stock"],
                         money(i["unit_cost"]), money(i["value"]), i["expiration_date"] or "-",
                         i["stock_status"], i["expiry_status"]]
        low = [i for i in items if i["stock_status"] in ("Low Stock", "Out of Stock")]
        expired = [i for i in items if i["expiry_status"] == "Expired"]
        soon = [i for i in items if i["expiry_status"] == "Expiring Soon"]
        sections.append({"title": "Summary", "headers": ["Measure", "Value"], "rows": [
            ["Vaccine products", len(items)], ["Units in stock (not expired)", usable],
            ["Units expired", expired_units], ["Low-stock vaccines", n(lambda i: i["stock_status"] == "Low Stock")],
            ["Out-of-stock vaccines", n(lambda i: i["stock_status"] == "Out of Stock")],
            ["Expired vaccines", len(expired)], ["Near-expiration vaccines", len(soon)],
            ["Total stock value", money(total_value)]]})
        sections.append({"title": "Vaccine Stock Items", "headers": head, "rows": [row(i) for i in items], "primary": True,
                         "meta": [{"href": url_for("inventory_view", item_id=i["item_id"]),
                                   "search": " ".join([i["item_name"], i.get("manufacturer") or "", i.get("batch_number") or ""]).lower()}
                                  for i in items]})
        sections.append({"title": "Low-stock and out-of-stock vaccines", "headers": head, "rows": [row(i) for i in low]})
        sections.append({"title": "Expired vaccines", "headers": head, "rows": [row(i) for i in expired]})
        sections.append({"title": "Near-expiration vaccines", "headers": head, "rows": [row(i) for i in soon]})
        summary = [("Vaccine products", len(items), ""), ("Units in stock (not expired)", usable, "good"),
                   ("Low stock", n(lambda i: i["stock_status"] == "Low Stock"), "warn" if n(lambda i: i["stock_status"] == "Low Stock") else ""),
                   ("Out of stock", n(lambda i: i["stock_status"] == "Out of Stock"), "bad" if n(lambda i: i["stock_status"] == "Out of Stock") else ""),
                   ("Expired", len(expired), "bad" if expired else ""),
                   ("Near expiration", len(soon), "warn" if soon else ""),
                   ("Stock value", money(total_value), "")]
    else:
        items = [i for i in enriched_inventory()
                 if (not args.get("category") or i["category"] == args["category"])
                 and (not args.get("stock_status") or i["stock_status"] == args["stock_status"])
                 and (not args.get("exp_status") or i["expiry_status"] == args["exp_status"])]
        total_value = float(sum(Decimal(str(i["value"])) for i in items))
        sections.append({"title": "Summary", "headers": ["Measure", "Value"],
                         "rows": [["Items listed", len(items)], ["Total value", money(total_value)]]})
        sections.append({"title": "Inventory Items", "primary": True,
                         "meta": [{"href": url_for("inventory_view", item_id=i["item_id"]),
                                   "search": " ".join([i["item_name"], i["category"], i["supplier"] or ""]).lower()} for i in items],
                         "headers": ["Item", "Category", "Quantity", "Minimum stock", "Unit cost", "Total value",
                                     "Supplier", "Expiration date", "Stock status", "Expiration status"],
                         "rows": [[i["item_name"], i["category"], f"{i['quantity']} {i['unit']}", i["min_stock"],
                                   money(i["unit_cost"]), money(i["value"]),
                                   i["supplier"] or "-", i["expiration_date"] or "-", i["stock_status"],
                                   i["expiry_status"]] for i in items]})
        n = lambda f: sum(1 for i in items if f(i))
        summary = [("Items listed", len(items), ""), ("Total value", money(total_value), "good"),
                   ("Low stock", n(lambda i: i["stock_status"] == "Low Stock"), "warn" if n(lambda i: i["stock_status"] == "Low Stock") else ""),
                   ("Out of stock", n(lambda i: i["stock_status"] == "Out of Stock"), "bad" if n(lambda i: i["stock_status"] == "Out of Stock") else ""),
                   ("Expired / expiring", n(lambda i: i["expiry_status"] != "Valid"), "warn" if n(lambda i: i["expiry_status"] != "Valid") else "")]
    return {"title": f"{REPORTS[kind]} Report", "sections": sections,
            "summary": [{"label": a, "value": b, "tone": c, "icon": summary_icon(a)} for a, b, c in summary]}


def pdf_fonts():
    """Register a font that can draw the peso sign. Returns (regular, bold, peso_ok).
    The built-in PDF fonts have no peso symbol, so without this it prints as a blank box."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pairs = [(BASE_DIR / "static/fonts/DejaVuSans.ttf", BASE_DIR / "static/fonts/DejaVuSans-Bold.ttf"),
             (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/segoeuib.ttf"))]
    for reg, bold in pairs:
        try:
            if reg.is_file() and bold.is_file():
                f = TTFont("PT-Regular", str(reg))
                if 0x20B1 in f.face.charToGlyph:
                    pdfmetrics.registerFont(f)
                    pdfmetrics.registerFont(TTFont("PT-Bold", str(bold)))
                    return "PT-Regular", "PT-Bold", True
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold", False


def pdf_report(report, filters, filename):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    font, bold, peso_ok = pdf_fonts()
    fix = (lambda t: t) if peso_ok else (lambda t: t.replace("\u20b1", "PHP "))
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10, fontName=font)
    head = ParagraphStyle("head", parent=cell, textColor=colors.white, fontName=bold)
    story = [Paragraph(xml_escape(get_settings()["clinic"]["name"]), styles["Title"]),
             Paragraph(xml_escape(report["title"]), styles["Heading2"]),
             Paragraph(f"Generated {now_str()} | Filters: {xml_escape(filters)}", cell), Spacer(1, 10)]
    for sec in report["sections"]:
        story.append(Paragraph(xml_escape(sec["title"]), styles["Heading3"]))
        data = [[Paragraph(xml_escape(h), head) for h in sec["headers"]]]
        data += [[Paragraph(xml_escape(fix(str(c))), cell) for c in row] for row in sec["rows"]] or \
                [[Paragraph("No records match the selected filters.", cell)] + [""] * (len(sec["headers"]) - 1)]
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3159A8")),
                                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF4FF")]),
                                   ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#AFCDF5")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [table, Spacer(1, 12)]
    doc.build(story)
    out.seek(0)
    return send_file(out, mimetype="application/pdf", as_attachment=True, download_name=filename)
