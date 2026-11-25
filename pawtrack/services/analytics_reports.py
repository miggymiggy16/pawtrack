"""PawTrack - detailed reports for Analytics cards.

Each report is built from the saved records at request time; this module owns
the report definitions and table/chart assembly. Data-gathering helpers live
in services.analytics.
"""
from datetime import date
from decimal import Decimal

from flask import current_app, url_for

from ..config import UP_TO_DATE
from ..helpers import fmt_date, money, parse_date
from ..storage import load
from .analytics import tally
from .inventory import enriched_inventory, inventory_counts
from .vaccinations import all_vax_rows, animal_vax_info, vax_counts


# Each Analytics card has a "View Report" link that opens one of these detailed reports.
ANALYTICS_REPORTS = {
    "species": "Animals by Species", "ownership": "Animals by Ownership", "sex": "Animals by Sex",
    "breed": "Animals by Breed", "status": "Vaccination Status", "monitoring": "Vaccination Monitoring",
    "trends": "Vaccination Trends", "vaccines": "Most Administered Vaccines",
    "coverage-species": "Vaccination Coverage by Species", "coverage-ownership": "Vaccination Coverage by Ownership",
    "inventory-value": "Inventory Value by Category", "inventory-alerts": "Inventory Alerts",
    "vaccine-stock": "Vaccine Stock",
}
ANALYTICS_OPEN_IN_REPORTS = {          # where the matching filterable / exportable report lives
    "species": "population", "ownership": "population", "sex": "population", "breed": "population",
    "status": "vaccination", "monitoring": "vaccination", "trends": "vaccination", "vaccines": "vaccination",
    "coverage-species": "vaccination", "coverage-ownership": "vaccination",
    "inventory-value": "inventory", "inventory-alerts": "inventory", "vaccine-stock": "vaccine_stock",
}


def share(n, total):
    return f"{round(n / total * 100, 1)}%" if total else "0%"


def animal_link(a):
    return {"text": a["animal_id"], "href": url_for("animal_view", animal_id=a["animal_id"])}


def build_analytics_report(key):
    """Detailed report for one Analytics card. Everything is counted from the saved records."""
    animals = sorted(load("animals"), key=lambda a: a["animal_id"])
    total = len(animals)
    info = {a["animal_id"]: animal_vax_info(a["animal_id"]) for a in animals}
    uptodate = lambda a: info[a["animal_id"]]["status"] in UP_TO_DATE
    animal_headers = ["Animal ID", "Name", "Species", "Breed", "Sex", "Ownership", "Vaccination status"]
    animal_row = lambda a: [animal_link(a), a["animal_name"], a["species"], a["breed"] or "-", a["sex"],
                            a["ownership_status"], info[a["animal_id"]]["status"]]
    rep_ = {"key": key, "title": ANALYTICS_REPORTS[key], "note": "", "chart": None, "summary": [], "tables": []}
    S = lambda label, value, tone="": rep_["summary"].append({"label": label, "value": value, "tone": tone})
    T = lambda title, headers, rows: rep_["tables"].append({"title": title, "headers": headers, "rows": rows})

    def group_report(field, label, chart_type, order=None):
        counts = tally(a[field] for a in animals)
        groups = list(counts)
        rep_["chart"] = {"type": chart_type, "labels": groups, "values": [counts[g] for g in groups],
                         "opts": {"label": "Animals"}}
        S("Total animals", total)
        S(f"{label} groups", len(groups))
        if counts:
            top = next(iter(counts))
            S("Most common", f"{top} ({counts[top]})")
        rows = []
        for g in groups:
            members = [a for a in animals if (a[field] or "Unspecified") == g]
            rows.append([g, len(members), share(len(members), total),
                         sum(1 for a in members if a["ownership_status"] == "Owned"),
                         sum(1 for a in members if a["ownership_status"] == "Stray"),
                         sum(1 for a in members if uptodate(a))])
        T(f"Number of animals per {label.lower()}", [label, "Animals", "Share", "Owned", "Stray", "Vaccinated"], rows)
        ordered = sorted(animals, key=lambda a: (-(counts.get(a[field] or "Unspecified", 0)), a[field] or "", a["animal_id"]))
        T("Animal list", animal_headers, [animal_row(a) for a in ordered])

    if key == "species":
        group_report("species", "Species", "doughnut")
    elif key == "ownership":
        group_report("ownership_status", "Ownership", "doughnut")
    elif key == "sex":
        group_report("sex", "Sex", "pie")
    elif key == "breed":
        group_report("breed", "Breed", "bar")
        rep_["chart"]["labels"], rep_["chart"]["values"] = rep_["chart"]["labels"][:10], rep_["chart"]["values"][:10]
        rep_["chart"]["opts"] = {"label": "Animals", "horizontal": True}
        rep_["note"] = "The chart shows the 10 most common breeds; the table lists every breed."
    elif key == "status":
        counts = tally(info[a["animal_id"]]["status"] for a in animals)
        rep_["chart"] = {"type": "bar", "labels": list(counts), "values": list(counts.values()), "opts": {"label": "Animals"}}
        ok = sum(1 for a in animals if uptodate(a))
        S("Total animals", total); S("Vaccinated (up to date)", ok, "good")
        S("Not vaccinated", total - ok, "bad" if total - ok else "")
        T("Animals per vaccination status", ["Status", "Animals", "Share"],
          [[k, v, share(v, total)] for k, v in counts.items()])
        T("Animal list", animal_headers + ["Next due"],
          [animal_row(a) + [fmt_date(info[a["animal_id"]]["next_due"]) if info[a["animal_id"]]["next_due"] else "-"]
           for a in sorted(animals, key=lambda a: (info[a["animal_id"]]["status"], a["animal_id"]))])
    elif key == "monitoring":
        vc = vax_counts()
        rep_["chart"] = {"type": "bar", "labels": ["Upcoming", "Due Today", "Overdue"],
                         "values": [vc["Upcoming"], vc["Due Today"], vc["Overdue"]],
                         "opts": {"label": "Records", "colors": ["#7FB4F5", "#F5A04A", "#F26B6B"]}}
        S("Overdue", vc["Overdue"], "bad" if vc["Overdue"] else ""); S("Due today", vc["Due Today"], "warn" if vc["Due Today"] else "")
        S("Upcoming", vc["Upcoming"])
        order = {"Overdue": 0, "Due Today": 1, "Upcoming": 2}
        recs = sorted([r for r in all_vax_rows() if r["is_current"] and r["status"] in order],
                      key=lambda r: (order[r["status"]], r.get("next_due_date") or ""))
        today = date.today()
        T("Records that need attention", ["Animal ID", "Animal", "Vaccine", "Administered", "Due date", "Days", "Status"],
          [[animal_link(r["animal"]), r["animal"]["animal_name"], r["vaccine_name"], r["date_administered"],
            r["next_due_date"], (parse_date(r["next_due_date"]) - today).days, r["status"]] for r in recs])
        rep_["note"] = "Days is negative when the due date has already passed. Only the latest record of each vaccine is monitored."
    elif key == "trends":
        recs = load("vaccinations")
        by_month = {}
        for v in recs:
            by_month.setdefault(v["date_administered"][:7], []).append(v)
        months = []
        if by_month:                                           # include months with no vaccinations
            y, m = map(int, min(by_month).split("-")); ey, em = map(int, max(by_month).split("-"))
            while (y, m) <= (ey, em):
                months.append(f"{y:04d}-{m:02d}")
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        counts = [len(by_month.get(mo, [])) for mo in months]
        rep_["chart"] = {"type": "line", "labels": months, "values": counts, "opts": {"label": "Vaccinations"}}
        S("Total vaccinations", len(recs))
        if months:
            best = max(range(len(months)), key=lambda i: counts[i])
            S("Busiest month", f"{months[best]} ({counts[best]})"); S("Monthly average", round(len(recs) / len(months), 1))
        rows = []
        for idx, mo in enumerate(months):
            top = tally(v["vaccine_name"] for v in by_month.get(mo, []))
            change = "-" if idx == 0 else f"{counts[idx] - counts[idx - 1]:+d}"
            rows.append([mo, counts[idx], change, next(iter(top)) if top else "-"])
        T("Vaccinations administered per month", ["Month", "Vaccinations", "Change vs previous month", "Most given vaccine"], rows)
        by_id = {a["animal_id"]: a for a in animals}
        T("Vaccination records", ["Date", "Animal ID", "Animal", "Vaccine"],
          [[v["date_administered"], animal_link(by_id[v["animal_id"]]) if v["animal_id"] in by_id else v["animal_id"],
            by_id[v["animal_id"]]["animal_name"] if v["animal_id"] in by_id else "-", v["vaccine_name"]]
           for v in sorted(recs, key=lambda v: (v["date_administered"], v["vaccination_id"]), reverse=True)])
    elif key == "vaccines":
        recs = load("vaccinations")
        counts = tally(v["vaccine_name"] for v in recs)
        rep_["chart"] = {"type": "bar", "labels": list(counts)[:8], "values": list(counts.values())[:8],
                         "opts": {"label": "Times given", "horizontal": True}}
        S("Total vaccinations", len(recs)); S("Different vaccines", len(counts))
        if counts:
            S("Most administered", next(iter(counts)))
        T("Times each vaccine was given", ["Vaccine", "Times given", "Animals vaccinated", "Share", "Last given"],
          [[name, n, len({v["animal_id"] for v in recs if v["vaccine_name"] == name}), share(n, len(recs)),
            max(v["date_administered"] for v in recs if v["vaccine_name"] == name)] for name, n in counts.items()])
        rep_["note"] = "The chart shows the 8 most given vaccines; the table lists all of them."
    elif key in ("coverage-species", "coverage-ownership"):
        field = "species" if key == "coverage-species" else "ownership_status"
        label = "Species" if key == "coverage-species" else "Ownership"
        names = sorted({a[field] for a in animals})
        rows, vals = [], []
        for nm in names:
            grp = [a for a in animals if a[field] == nm]
            ok = sum(1 for a in grp if uptodate(a))
            pct = round(ok / len(grp) * 100, 1)
            rows.append([nm, len(grp), ok, len(grp) - ok, f"{pct}%"]); vals.append(pct)
        rep_["chart"] = {"type": "bar", "labels": names, "values": vals, "opts": {"label": "Coverage %", "max": 100}}
        overall = round(sum(1 for a in animals if uptodate(a)) / total * 100, 1) if total else 0.0
        S("Overall coverage", f"{overall}%", "good"); S("Total animals", total)
        T(f"Coverage by {label.lower()}", [label, "Animals", "Vaccinated", "Not vaccinated", "Coverage"], rows)
        rep_["note"] = "Coverage = vaccinated animals \u00f7 animals in the group \u00d7 100. An animal counts once."
    elif key in ("inventory-value", "inventory-alerts", "vaccine-stock"):
        items = enriched_inventory()
        counts = inventory_counts(items)
        item_head = ["Item", "Category", "Quantity", "Minimum stock", "Unit cost", "Expiration", "Stock status", "Expiry status"]
        item_row = lambda i: [{"text": i["item_name"], "href": url_for("inventory_view", item_id=i["item_id"])}, i["category"],
                              f"{i['quantity']} {i['unit']}", i["min_stock"], money(i["unit_cost"]),
                              fmt_date(i["expiration_date"]) if i["expiration_date"] else "-", i["stock_status"], i["expiry_status"]]
        if key == "inventory-value":
            cats = {}
            for i in items:
                c = cats.setdefault(i["category"], {"n": 0, "v": Decimal("0")})
                c["n"] += 1; c["v"] += Decimal(str(i["value"]))
            rep_["chart"] = {"type": "bar", "labels": list(cats), "values": [float(c["v"]) for c in cats.values()], "opts": {"label": "Value"}}
            S("Total inventory value", money(counts["value"]), "good"); S("Items", counts["total"]); S("Categories", len(cats))
            tv = Decimal(str(counts["value"]))
            T("Value per category", ["Category", "Items", "Total value", "Share of value"],
              [[k, c["n"], money(c["v"]), f"{round(c['v'] / tv * 100, 1)}%" if tv else "0%"]
               for k, c in sorted(cats.items(), key=lambda kv: -kv[1]["v"])])
            T("All items", item_head + ["Total value"], [item_row(i) + [money(i["value"])] for i in items])
        elif key == "inventory-alerts":
            rep_["chart"] = {"type": "bar", "labels": ["Low stock", "Out of stock", "Expired", "Expiring soon"],
                             "values": [counts["low"], counts["out"], counts["expired"], counts["expiring"]],
                             "opts": {"label": "Items", "colors": ["#F5A04A", "#F26B6B", "#C94444", "#FFD2A1"]}}
            S("Low stock", counts["low"], "warn" if counts["low"] else ""); S("Out of stock", counts["out"], "bad" if counts["out"] else "")
            S("Expired", counts["expired"], "bad" if counts["expired"] else ""); S("Expiring soon", counts["expiring"], "warn" if counts["expiring"] else "")
            for title, test in (("Low stock", lambda i: i["stock_status"] == "Low Stock"),
                                ("Out of stock", lambda i: i["stock_status"] == "Out of Stock"),
                                ("Expired", lambda i: i["expiry_status"] == "Expired"),
                                ("Expiring soon", lambda i: i["expiry_status"] == "Expiring Soon")):
                T(title, item_head, [item_row(i) for i in items if test(i)])
        else:
            vac = [i for i in items if i["category"] == "Vaccines"]
            vc = inventory_counts(vac)
            usable = sum(i["quantity"] for i in vac if i["expiry_status"] != "Expired")
            rep_["chart"] = {"type": "bar", "labels": [i["item_name"] for i in vac], "values": [i["quantity"] for i in vac],
                             "opts": {"label": "In stock"}}
            S("Vaccine products", vc["total"]); S("Units in stock (not expired)", usable, "good")
            S("Low / out of stock", vc["low"] + vc["out"], "warn" if vc["low"] + vc["out"] else "")
            S("Expired", vc["expired"], "bad" if vc["expired"] else ""); S("Near expiration", vc["expiring"], "warn" if vc["expiring"] else "")
            T("Vaccine stock", item_head + ["Batch / lot", "Manufacturer / brand"],
              [item_row(i) + [i.get("batch_number") or "-", i.get("manufacturer") or "-"] for i in vac])
            T("Low-stock and out-of-stock vaccines", item_head, [item_row(i) for i in vac if i["stock_status"] != "In Stock"])
            T("Expired and near-expiration vaccines", item_head, [item_row(i) for i in vac if i["expiry_status"] != "Valid"])
    return rep_
