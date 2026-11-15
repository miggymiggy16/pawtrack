"""
PawTrack - role dashboards and the activity log
"""
from datetime import date, timedelta

from flask import redirect, render_template, request

from ..extensions import app
from ..helpers import parse_date
from ..security import (admin_required, current_user, login_required,
                        permission_required, role_home)
from ..services.analytics import (activity_entries, analytics_data,
                                  dashboard_context, month_labels, spark,
                                  vaccine_rows, vaccine_stock_totals)
from ..services.inventory import enriched_inventory
from ..services.notifications import notification_feed
from ..services.vaccinations import all_vax_rows, animal_vax_info
from ..storage import get_settings, load

# ---------- role dashboards: helpers (everything is read from the saved records) ----------
PERIOD_CHOICES = [(7, "Last 7 days"), (30, "Last 30 days"), (90, "Last 90 days"), (365, "Last 12 months")]


def _period_days():
    try:
        days = int(request.args.get("days", "30"))
    except ValueError:
        days = 30
    return days if days in dict(PERIOD_CHOICES) else 30


def _in_range(value, start, end):
    d = parse_date(str(value or "")[:10])
    return bool(d) and start <= d <= end


def _pct_change(now, before):
    """Trend only when the previous period has data to compare with (never invented)."""
    return round((now - before) / before * 100) if before > 0 else None


@app.route("/")
@login_required
def dashboard():
    """One entry point: send each signed-in user to the dashboard for their stored role."""
    return redirect(role_home())


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    ctx = dashboard_context()
    days = _period_days()
    today = date.today()
    start, end = today - timedelta(days=days - 1), today
    prev_start, prev_end = start - timedelta(days=days), start - timedelta(days=1)
    items = enriched_inventory()
    vaccines = vaccine_rows(items)
    records = load("vaccinations")
    tx = load("inventory_transactions")

    in_period = sum(1 for r in records if _in_range(r["date_administered"], start, end))
    before = sum(1 for r in records if _in_range(r["date_administered"], prev_start, prev_end))
    overdue_animals = len({r["animal_id"] for r in all_vax_rows() if r["is_current"] and r["status"] == "Overdue"})
    total_animals = ctx["a"]["total"]
    cards = {"animals": total_animals, "vax_period": in_period, "vax_trend": _pct_change(in_period, before),
             "vaccinated": ctx["a"]["vaccinated"], "owned": ctx["a"]["owned"], "stray": ctx["a"]["stray"],
             "coverage": round(ctx["a"]["vaccinated"] / total_animals * 100) if total_animals else 0,
             "overdue": overdue_animals}

    received = [t for t in tx if t["transaction_type"] == "Stock In" and t.get("source") != "vaccination"]
    received.sort(key=lambda t: t["datetime"], reverse=True)
    low_items = [i for i in vaccines if i["stock_status"] in ("Low Stock", "Out of Stock")]

    # analytics overview
    n_months = 12 if days == 365 else 6
    months = month_labels(n_months)
    monthly = {}
    for r in records:
        monthly[r["date_administered"][:7]] = monthly.get(r["date_administered"][:7], 0) + 1
    used, returned = {}, {}
    for t in tx:
        if t.get("source") == "vaccination":
            bucket = used if t["transaction_type"] == "Stock Out" else returned if t["transaction_type"] == "Stock In" else None
            if bucket is not None:
                bucket[t["datetime"][:7]] = bucket.get(t["datetime"][:7], 0) + t["quantity"]
    period_tx = [t for t in tx if _in_range(t["datetime"], start, end)]
    p_in = [t for t in period_tx if t["transaction_type"] == "Stock In" and t.get("source") != "vaccination"]
    p_out = [t for t in period_tx if t["transaction_type"] == "Stock Out"]
    p_adj = [t for t in period_tx if t["transaction_type"] == "Adjustment"]
    restocked_ids = {t["item_id"] for t in p_in}
    stats = {"in_units": sum(t["quantity"] for t in p_in), "in_n": len(p_in),
             "out_units": sum(t["quantity"] for t in p_out), "out_n": len(p_out),
             "adj_n": len(p_adj), "adj_net": sum(t["quantity"] for t in p_adj),
             "adj_lost": -sum(t["quantity"] for t in p_adj if t["quantity"] < 0),
             "last_received": received[0] if received else None,
             "needs_restock": [i for i in low_items if i["item_id"] not in restocked_ids][:5]}
    charts = {"labels": [lbl for _, lbl in months],
              "vaccinations": [monthly.get(k, 0) for k, _ in months],
              "consumption": [max(0, used.get(k, 0) - returned.get(k, 0)) for k, _ in months]}
    try:
        an = analytics_data()
    except Exception:
        from flask import current_app
        current_app.logger.exception("Dashboard: could not load analytics")
        ctx["problems"].append("analytics")
        an = {"species_cov": {}, "top_vaccines": {}, "status_counts": {}}
    species_cov = sorted(an["species_cov"].items(), key=lambda kv: -kv[1])[:8]
    top_vaccines = list(an["top_vaccines"].items())[:6]
    return render_template("admin_dashboard.html", cards=cards, stats=stats, charts=charts, days=days,
                           spark=spark(charts["vaccinations"]), species_cov=species_cov, top_vaccines=top_vaccines,
                           status_counts=an["status_counts"], low_items=low_items[:4], periods=PERIOD_CHOICES,
                           period_label=dict(PERIOD_CHOICES)[days], start=start.isoformat(), end=end.isoformat(),
                           problems=ctx["problems"], reminder_days=ctx["reminder_days"],
                           expiry_days=get_settings()["expiry_warning_days"])


@app.route("/staff/dashboard")
@login_required
def staff_dashboard():
    me = current_user()
    if me["role"] != "staff":
        return redirect(role_home())          # administrators use their own dashboard
    ctx = dashboard_context()
    today = date.today()
    items = enriched_inventory()
    vaccines = vaccine_rows(items)
    rows = [r for r in all_vax_rows() if r["is_current"]]
    overdue = sorted((r for r in rows if r["status"] == "Overdue"), key=lambda r: (r.get("next_due_date") or "", r["animal_id"]))
    upcoming = sorted((r for r in rows if r["status"] in ("Due Today", "Upcoming")),
                      key=lambda r: (r.get("next_due_date") or "", r["animal_id"]))
    def with_days(r):
        d = parse_date(str(r.get("next_due_date") or "")[:10])
        return {**r, "days": (d - today).days if d else 0}
    overdue, upcoming = [with_days(r) for r in overdue[:6]] + overdue[6:], [with_days(r) for r in upcoming[:6]] + upcoming[6:]
    animals = load("animals")
    no_record = [a for a in animals if animal_vax_info(a["animal_id"])["status"] == "No Record"]
    recorded_today = sum(1 for r in load("vaccinations") if str(r.get("created_at", ""))[:10] == today.isoformat())
    cards = {"animals": len(animals),
             "due": len({r["animal_id"] for r in upcoming}),
             "overdue": len({r["animal_id"] for r in overdue}),
             "due_today": len({r["animal_id"] for r in upcoming if r["status"] == "Due Today"}),
             "today": recorded_today, "stock": vaccine_stock_totals(items)}
    stock_rows = sorted(vaccines, key=lambda i: (i["stock_status"] == "In Stock" and i["expiry_status"] == "Valid", i["item_name"]))
    stock_alerts = sum(1 for i in vaccines if i["stock_status"] != "In Stock" or i["expiry_status"] != "Valid")
    feed = [n for n in notification_feed() if n["group"] != "email"][:5]
    mine = [e for e in activity_entries() if e["user"] == me["username"]][:6]
    recent_animals = sorted(animals, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
    return render_template("staff_dashboard.html", cards=cards, overdue=overdue[:6], overdue_more=max(0, len(overdue) - 6),
                           upcoming=upcoming[:6], upcoming_more=max(0, len(upcoming) - 6),
                           no_record=no_record[:5], no_record_total=len(no_record), stock_rows=stock_rows,
                           stock_alerts=stock_alerts, feed=feed, mine=mine, recent_animals=recent_animals,
                           problems=ctx["problems"], reminder_days=ctx["reminder_days"])


@app.route("/activity")
@permission_required("activity.view")
def activity_log():
    q = request.args.get("q", "").strip().lower()
    rows = [e for e in activity_entries()
            if not q or q in " ".join((e["user"], e["action"], e["subject"], e["ref"])).lower()]
    return render_template("activity.html", rows=rows[:300], total=len(rows), q=q)
