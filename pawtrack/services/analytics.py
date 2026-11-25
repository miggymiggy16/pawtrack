"""
PawTrack - analytics, dashboards and activity
=============================================
All numbers are counted from the saved records on every request. Nothing is
cached in a database or invented; a missing/unreadable block is reported on
the page instead of showing a stack trace.
"""
from datetime import date
from decimal import Decimal

from flask import current_app, url_for

from ..config import OWNERSHIP_CHOICES, UP_TO_DATE
from ..helpers import fmt_date, money, parse_date
from ..security import can
from ..storage import get_settings, load
from .inventory import enriched_inventory, inventory_counts
from .vaccinations import all_vax_rows, animal_vax_info, vax_counts


# ---------------------------------------------------------------------------
# Small counting helpers
# ---------------------------------------------------------------------------
def tally(values):
    out = {}
    for v in values:
        out[v or "Unspecified"] = out.get(v or "Unspecified", 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def month_labels(n=6):
    """The last n calendar months (oldest first) as [("YYYY-MM", "Mon YYYY"), ...]."""
    y, m = date.today().year, date.today().month
    out = []
    for _ in range(n):
        out.append((f"{y:04d}-{m:02d}", date(y, m, 1).strftime("%b %Y")))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def spark(values, w=132, h=44, pad=5):
    """Tiny inline-SVG sparkline geometry (no JavaScript needed)."""
    if not values:
        return None
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = (w - 2 * pad) / max(1, len(values) - 1)
    pts = [(pad + i * step, h - pad - (v - lo) / span * (h - 2 * pad)) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{h} {line} {pts[-1][0]:.1f},{h}"
    return {"w": w, "h": h, "line": line, "area": area, "x": round(pts[-1][0], 1), "y": round(pts[-1][1], 1)}


def animal_stats():
    animals = load("animals")
    statuses = [animal_vax_info(a["animal_id"])["status"] for a in animals]
    vaccinated = sum(1 for s in statuses if s in UP_TO_DATE)
    return {"total": len(animals),
            "owned": sum(1 for a in animals if a["ownership_status"] == "Owned"),
            "stray": sum(1 for a in animals if a["ownership_status"] == "Stray"),
            "vaccinated": vaccinated, "unvaccinated": len(animals) - vaccinated,
            "statuses": statuses}


def vaccine_rows(items):
    return [i for i in items if i.get("category") == "Vaccines"]


def vaccine_stock_totals(items):
    """Eligible vaccine stock = Vaccines category, not expired, quantity above zero. Returns {unit: quantity}."""
    totals = {}
    for i in items:
        if i.get("category") == "Vaccines" and i["expiry_status"] != "Expired" and i["quantity"] > 0:
            totals[i["unit"]] = totals.get(i["unit"], 0) + i["quantity"]
    return totals


# ---------------------------------------------------------------------------
# Shared dashboard context
# ---------------------------------------------------------------------------
def dashboard_context():
    """Shared dashboard numbers. Every number comes from the saved records on each request.
    Each block is loaded on its own so one unreadable data file cannot blank the whole page."""
    problems = []

    def safe(label, fn, default):
        try:
            return fn()
        except Exception:                                  # never show a stack trace on the Dashboard
            current_app.logger.exception("Dashboard: could not load %s", label)
            problems.append(label)
            return default

    a = safe("animal totals", animal_stats, {"total": 0, "owned": 0, "stray": 0, "vaccinated": 0,
                                              "unvaccinated": 0, "statuses": []})
    v = safe("vaccination counts", vax_counts, {"Upcoming": 0, "Due Today": 0, "Overdue": 0})
    items = safe("inventory", enriched_inventory, [])
    inv = safe("inventory counts", lambda: inventory_counts(items),
               {"total": 0, "low": 0, "out": 0, "expired": 0, "expiring": 0, "value": 0})

    # Vaccination monitoring: current records that are Overdue / Due Today / Upcoming (most urgent first)
    def monitor():
        order = {"Overdue": 0, "Due Today": 1, "Upcoming": 2}
        rows = [r for r in all_vax_rows() if r["is_current"] and r["status"] in order]
        rows.sort(key=lambda r: (order[r["status"]], r.get("next_due_date") or "", r["animal_id"]))
        return rows
    vax_rows = safe("vaccination monitoring", monitor, [])

    # Inventory alerts: each item appears once. Out of stock / expired first, then low stock / expiring soon.
    def inv_priority(i):
        if i["stock_status"] == "Out of Stock" or i["expiry_status"] == "Expired":
            return 0
        return 1

    alerts = [i for i in items if i["stock_status"] != "In Stock" or i["expiry_status"] != "Valid"]
    alerts.sort(key=lambda i: (inv_priority(i), 0 if i.get("category") == "Vaccines" else 1,
                               i.get("expiration_date") or "9999", i["item_name"]))
    low_vaccines = sum(1 for i in items if i.get("category") == "Vaccines" and i["stock_status"] == "Low Stock")
    out_vaccines = sum(1 for i in items if i.get("category") == "Vaccines" and i["stock_status"] == "Out of Stock")

    animals = safe("animals", lambda: load("animals"), [])
    recent_animals = sorted(animals, key=lambda x: x.get("created_at", ""), reverse=True)[:8]

    def activity_feed():
        feed = []
        for x in animals:
            feed.append((x.get("created_at", ""), f"Registered animal {x['animal_name']} ({x['animal_id']})",
                         url_for("animal_view", animal_id=x["animal_id"])))
        for x in load("vaccinations"):
            feed.append((x.get("created_at", ""), f"Vaccination recorded: {x['vaccine_name']} for {x['animal_id']}",
                         url_for("animal_view", animal_id=x["animal_id"])))
        for x in load("inventory_transactions"):
            feed.append((x["datetime"], f"{x['transaction_type']}: {x['item_name']} ({x['quantity']})",
                         url_for("inventory_view", item_id=x["item_id"])))
        for x in load("notifications"):
            feed.append((x["datetime"], f"Email {x['status'].lower()}: {x['type']} - {x['animal_name']}",
                         url_for("notifications")))
        feed.sort(key=lambda t: t[0], reverse=True)
        return feed[:8]
    activity = safe("recent activity", activity_feed, [])

    # Chart data (all calculated from the records)
    def chart_data():
        status_counts = tally(a["statuses"])
        status_order = ["Vaccinated", "Upcoming", "Due Today", "Overdue", "No Record"]
        monthly = {}
        for r in load("vaccinations"):
            monthly[r["date_administered"][:7]] = monthly.get(r["date_administered"][:7], 0) + 1
        months = month_labels(6)
        species = tally(x["species"] for x in animals)
        return {"ownership": [a["owned"], a["stray"]],
                "vaccination": [a["vaccinated"], a["unvaccinated"]],
                "status_labels": status_order,
                "status": [status_counts.get(s, 0) for s in status_order],
                "species_labels": list(species.keys()), "species": list(species.values()),
                "trend_labels": [lbl for _, lbl in months], "trend": [monthly.get(k, 0) for k, _ in months]}
    chart = safe("charts", chart_data, {"ownership": [0, 0], "vaccination": [0, 0], "status_labels": [], "status": [],
                                         "species_labels": [], "species": [], "trend_labels": [], "trend": []})
    coverage = round(a["vaccinated"] / a["total"] * 100) if a["total"] else 0
    return dict(a=a, v=v, inv=inv, coverage=coverage,
                vax_rows=vax_rows[:8], vax_more=max(0, len(vax_rows) - 8),
                inv_alerts=alerts[:6], inv_more=max(0, len(alerts) - 6),
                low_vaccines=low_vaccines, out_vaccines=out_vaccines,
                activity=activity, recent_animals=recent_animals, chart=chart,
                problems=problems, reminder_days=get_settings()["reminder_days"])


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------
def activity_entries():
    """Every recorded action as {when, user, action, subject, ref, url}. The user is shown only when the
    record stored one; older records show 'Not recorded' instead of an invented name."""
    out = []
    for x in load("animals"):
        out.append({"when": x.get("created_at", ""), "user": x.get("created_by", ""), "action": "Registered animal",
                    "subject": f"{x['animal_name']} ({x['animal_id']})", "ref": x["animal_id"],
                    "url": url_for("animal_view", animal_id=x["animal_id"])})
    for x in load("vaccinations"):
        out.append({"when": x.get("created_at", ""), "user": x.get("created_by", ""), "action": "Recorded vaccination",
                    "subject": f"{x['vaccine_name']} for {x['animal_id']}", "ref": x["vaccination_id"],
                    "url": url_for("animal_view", animal_id=x["animal_id"], _anchor="history")})
    for x in load("inventory_transactions"):
        out.append({"when": x["datetime"], "user": x.get("user", ""), "action": x["transaction_type"],
                    "subject": f"{x['item_name']} ({x['quantity']})", "ref": x["transaction_id"],
                    "url": url_for("inventory_view", item_id=x["item_id"]) if can("inventory.view") else ""})
    for x in load("pos_sales"):
        url = url_for("sale_receipt", sale_id=x["sale_id"])
        out.append({"when": x["datetime"], "user": x.get("cashier", ""), "action": "POS sale",
                    "subject": f"{x['sale_id']} ({money(x['total'])})", "ref": x["sale_id"], "url": url})
        if x.get("status") == "Voided":
            out.append({"when": x.get("voided_at", x["datetime"]), "user": x.get("voided_by", ""), "action": "POS sale voided",
                        "subject": f"{x['sale_id']} ({money(x['total'])})", "ref": x["sale_id"], "url": url})
    for x in load("notifications"):
        out.append({"when": x["datetime"], "user": x.get("by", ""), "action": f"Email {x['status'].lower()}: {x['type']}",
                    "subject": x.get("animal_name", ""), "ref": x["notification_id"], "url": ""})
    out.sort(key=lambda e: e["when"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Analytics page
# ---------------------------------------------------------------------------
def analytics_data():
    animals = load("animals")
    stats = animal_stats()
    status_of = {a["animal_id"]: s for a, s in zip(animals, stats["statuses"])}
    total = len(animals)
    # Coverage = animals with an up-to-date record / total animals x 100 (each animal counted once)
    coverage = round(stats["vaccinated"] / total * 100, 1) if total else 0.0
    species_cov = {}
    for sp in sorted({a["species"] for a in animals}):
        group = [a for a in animals if a["species"] == sp]
        ok = sum(1 for a in group if status_of[a["animal_id"]] in UP_TO_DATE)
        species_cov[sp] = round(ok / len(group) * 100, 1)
    monthly = {}
    for v in load("vaccinations"):
        monthly[v["date_administered"][:7]] = monthly.get(v["date_administered"][:7], 0) + 1
    monthly = dict(sorted(monthly.items()))
    items = enriched_inventory()
    counts = inventory_counts(items)
    by_cat = {}
    for i in items:
        by_cat[i["category"]] = round(by_cat.get(i["category"], 0) + i["value"], 2)
    return {
        "total": total, "coverage": coverage, "stats": stats, "vax": vax_counts(), "inv": counts,
        "species": tally(a["species"] for a in animals), "breeds": dict(list(tally(a["breed"] for a in animals).items())[:10]),
        "sex": tally(a["sex"] for a in animals), "ownership": tally(a["ownership_status"] for a in animals),
        "species_cov": species_cov, "monthly": monthly,
        "top_vaccines": dict(list(tally(v["vaccine_name"] for v in load("vaccinations")).items())[:8]),
        "value_by_cat": by_cat,
        "status_counts": tally(status_of.values()),
        "ownership_cov": {o: round(sum(1 for a in animals if a["ownership_status"] == o and
                                       status_of[a["animal_id"]] in UP_TO_DATE) /
                                   max(1, sum(1 for a in animals if a["ownership_status"] == o)) * 100, 1)
                          for o in OWNERSHIP_CHOICES},
    }
