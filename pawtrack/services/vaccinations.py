"""
PawTrack - vaccination status logic
===================================
Record status (based on Next Due Date and the reminder window):
  Overdue    -> due date has passed
  Due Today  -> due date is today
  Upcoming   -> due within the reminder days (default 7)
  Completed  -> administered, and nothing is due soon (or no due date)

Only the LATEST record for each animal + vaccine is "current". Older records
are history and always show "Completed" (the newer shot replaced them).
"""
from datetime import date

from flask import g

from ..helpers import parse_date
from ..storage import get_settings, load


def record_status(next_due, reminder_days, today=None):
    today = today or date.today()
    d = parse_date(next_due)
    if not d:
        return "Completed"
    if d < today:
        return "Overdue"
    if d == today:
        return "Due Today"
    if (d - today).days <= reminder_days:
        return "Upcoming"
    return "Completed"


def vax_index():
    """Return {animal_id: [vaccination records with computed fields]} (cached per request)."""
    if "vax_index" in g:
        return g.vax_index
    reminder = int(get_settings()["reminder_days"])
    records = load("vaccinations")
    latest = {}
    for r in records:
        key = (r["animal_id"], r["vaccine_name"].strip().lower())
        rank = (r["date_administered"], r["vaccination_id"])
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, r["vaccination_id"])
    current_ids = {v[1] for v in latest.values()}
    index = {}
    for r in records:
        r = dict(r)
        r["is_current"] = r["vaccination_id"] in current_ids
        r["status"] = record_status(r.get("next_due_date"), reminder) if r["is_current"] else "Completed"
        index.setdefault(r["animal_id"], []).append(r)
    g.vax_index = index
    return index


def animal_vax_info(animal_id):
    """Summary used on lists, profile and public page."""
    recs = vax_index().get(animal_id, [])
    if not recs:
        return {"status": "No Record", "latest": None, "next_due": None, "records": []}
    current = [r for r in recs if r["is_current"]]
    statuses = {r["status"] for r in current}
    for s in ("Overdue", "Due Today", "Upcoming"):
        if s in statuses:
            status = s
            break
    else:
        status = "Vaccinated"
    dues = sorted(r["next_due_date"] for r in current if r.get("next_due_date"))
    latest = max(recs, key=lambda r: (r["date_administered"], r["vaccination_id"]))
    return {"status": status, "latest": latest, "next_due": dues[0] if dues else None,
            "records": sorted(recs, key=lambda r: r["date_administered"], reverse=True)}


def all_vax_rows():
    """Every vaccination record joined with its animal (dict)."""
    animals = {a["animal_id"]: a for a in load("animals")}
    rows = []
    for recs in vax_index().values():
        for r in recs:
            if r["animal_id"] in animals:
                rows.append({**r, "animal": animals[r["animal_id"]]})
    rows.sort(key=lambda r: (r["date_administered"], r["vaccination_id"]), reverse=True)
    return rows


def vax_counts():
    cur = [r for r in all_vax_rows() if r["is_current"]]
    return {s: sum(1 for r in cur if r["status"] == s) for s in ("Upcoming", "Due Today", "Overdue")}
