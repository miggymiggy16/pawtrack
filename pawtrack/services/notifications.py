"""
PawTrack - in-app notification feed
===================================
The feed is CALCULATED from the real vaccination schedule, the inventory and
the email history every time it is needed, so it can never drift from the data
and a repeated check can never create duplicates. Only "which keys did this
user read" is stored; reading never touches a vaccination.
"""
from datetime import date, datetime, timedelta

from flask import g, url_for

from ..helpers import fmt_date, now_str, parse_date
from ..security import current_user
from ..storage import edit, get_settings, load
from .inventory import enriched_inventory
from .vaccinations import all_vax_rows

NOTE_GROUPS = [("overdue", "Overdue vaccinations"), ("due-today", "Due today"),
               ("upcoming", "Upcoming vaccinations"), ("inventory", "Inventory alerts"),
               ("email", "Email history")]
NOTE_CATS = {"all": "All", "unread": "Unread", "vaccination": "Vaccination",
             "inventory": "Inventory", "email": "Email"}
EMAIL_ALL_LIMIT = 8        # the "All" view only previews the newest email entries


def relative_when(value):
    """'Today', '2 days ago', '3 hours ago' for a date or a 'YYYY-MM-DD HH:MM:SS' string."""
    if value is None or value == "":
        return ""
    now = datetime.now()
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        days = (date.today() - value).days
        return "Today" if days == 0 else "Yesterday" if days == 1 else f"{days} days ago" if days > 0 else f"In {-days} days"
    else:
        try:
            dt = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return str(value)
    secs = int((now - dt).total_seconds())
    if secs < 60:
        return "Just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if dt.date() == date.today():
        return f"{secs // 3600} hr ago"
    days = (date.today() - dt.date()).days
    return "Yesterday" if days == 1 else f"{days} days ago" if days < 30 else dt.strftime("%b %d, %Y")


def notification_feed():
    """Every current notification as a dict, most urgent first inside each group."""
    if "note_feed" in g:
        return g.note_feed
    today, items = date.today(), []
    reminder = int(get_settings()["reminder_days"])
    # 1) vaccinations that need attention (only the CURRENT record of each vaccine)
    for r in all_vax_rows():
        if not r["is_current"] or r["status"] not in ("Overdue", "Due Today", "Upcoming"):
            continue
        due, a = parse_date(r.get("next_due_date")), r["animal"]
        if not due:
            continue
        vname, name = r["vaccine_name"], a["animal_name"]
        if r["status"] == "Overdue":
            grp, sev, icon_, title = "overdue", "bad", "alertc", f"{name} — Vaccination Overdue"
            msg, when = f"{vname} vaccine was due on {fmt_date(due)}.", due + timedelta(days=1)
        elif r["status"] == "Due Today":
            grp, sev, icon_, title = "due-today", "warn", "clock", f"{name} — Vaccination Due Today"
            msg, when = f"{vname} vaccine is due today.", due
        else:
            left = (due - today).days
            grp, sev, icon_, title = "upcoming", "info", "calclock", f"{name} — Upcoming Vaccination"
            msg = f"{vname} vaccine is due on {fmt_date(due)} ({'tomorrow' if left == 1 else f'in {left} days'})."
            when = min(today, due - timedelta(days=reminder))
        items.append({"key": f"vax|{r['vaccination_id']}|{r['status']}|{due.isoformat()}", "cat": "vaccination",
                      "group": grp, "severity": sev, "icon": icon_, "title": title, "message": msg,
                      "meta": f"{r['animal_id']} · {relative_when(when)}", "sort": (due.isoformat(), r["animal_id"]),
                      "url": url_for("animal_view", animal_id=r["animal_id"], _anchor="history"),
                      "trackable": True, "animal": f"{name} {r['animal_id']}".lower()})
    # 2) inventory alerts (one card per item and condition)
    last_tx = {}
    for t in load("inventory_transactions"):
        if t.get("item_id") and t.get("datetime", "") > last_tx.get(t["item_id"], ""):
            last_tx[t["item_id"]] = t["datetime"]
    warn_days = get_settings()["expiry_warning_days"]
    for i in enriched_inventory():
        conds = []
        if i["stock_status"] == "Out of Stock":
            conds.append(("Out of Stock", "bad", "No units left. Restock before the next use.", last_tx.get(i["item_id"])))
        elif i["stock_status"] == "Low Stock":
            conds.append(("Low Stock", "warn", f"{i['quantity']} {i['unit']} left (minimum {i['min_stock']}).", last_tx.get(i["item_id"])))
        exp = parse_date(i.get("expiration_date"))
        if i["expiry_status"] == "Expired":
            conds.append(("Expired", "bad", f"Expired on {fmt_date(exp)}. Do not use.", exp))
        elif i["expiry_status"] == "Expiring Soon":
            conds.append(("Expiring Soon", "warn", f"Expires on {fmt_date(exp)} ({(exp - today).days} day(s) left).",
                          min(today, exp - timedelta(days=warn_days))))
        for cond, sev, msg, when in conds:
            items.append({"key": f"inv|{i['item_id']}|{cond}", "cat": "inventory", "group": "inventory",
                          "severity": sev, "icon": "alertc" if sev == "bad" else "box",
                          "title": f"{i['item_name']} — {cond}", "message": msg,
                          "meta": f"{i['item_id']} · {i.get('category', '')}" + (f" · {relative_when(when)}" if when else ""),
                          "sort": (0 if sev == "bad" else 1, i["item_name"].lower()),
                          "url": url_for("inventory_view", item_id=i["item_id"]), "trackable": True, "animal": ""})
    # 3) email history (newest first). Failed attempts are alerts; sent ones are plain history.
    for n in sorted(load("notifications"), key=lambda n: n.get("datetime", ""), reverse=True):
        failed = n.get("status") == "Failed"
        who = n.get("animal_name") if n.get("animal_id") else "PawTrack"
        items.append({"key": f"email|{n['notification_id']}", "cat": "email", "group": "email",
                      "severity": "bad" if failed else "ok", "icon": "alertc" if failed else "mail",
                      "title": f"{who} — {n['type']}" + (" (not sent)" if failed else ""),
                      "message": (n.get("error") or "The email could not be sent.") if failed
                                 else f"Email sent to {n.get('email') or 'the owner'}.",
                      "meta": f"{n.get('animal_id') or n.get('purpose', '')} · {relative_when(n.get('datetime'))}".strip(" ·"),
                      "sort": "", "raw": n, "body": n.get("message", ""), "trackable": failed,
                      "url": url_for("animal_view", animal_id=n["animal_id"]) if n.get("animal_id") else "",
                      "animal": f"{n.get('animal_name', '')} {n.get('animal_id', '')}".lower()})
    order = {k: n for n, (k, _) in enumerate(NOTE_GROUPS)}
    items.sort(key=lambda x: (order[x["group"]], x["sort"] if x["group"] != "email" else ""))
    read = load("notification_reads").get(str((current_user() or {}).get("user_id", "")), {})
    for x in items:
        x["unread"] = bool(x["trackable"] and x["key"] not in read)
    g.note_feed = items
    return items


def unread_notification_count():
    try:
        return sum(1 for x in notification_feed() if x["unread"]) if current_user() else 0
    except Exception:                       # the badge must never break a page
        return 0


def mark_notifications_read(keys):
    uid = str(current_user()["user_id"])
    live = {x["key"] for x in notification_feed() if x["trackable"]}
    with edit("notification_reads") as reads:
        mine = {k: v for k, v in reads.get(uid, {}).items() if k in live}   # forget keys that no longer exist
        for k in keys:
            if k in live:
                mine.setdefault(k, now_str())
        reads[uid] = mine
    g.pop("note_feed", None)


def register_notification_globals(app):
    app.jinja_env.globals["unread_count"] = unread_notification_count
    app.jinja_env.globals["notification_feed"] = notification_feed
