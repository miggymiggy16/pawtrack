"""
PawTrack - in-app notification feed and manual email
"""
from flask import flash, redirect, render_template, request, url_for

from ..config import NOTIFY_TYPES
from ..extensions import app
from ..helpers import valid_email
from ..security import (admin_required, current_user, permission_required,
                        safe_next)
from ..services.email import build_message, mail_config, notify, run_notification_check
from ..services.notifications import (EMAIL_ALL_LIMIT, NOTE_CATS, NOTE_GROUPS,
                                      mark_notifications_read,
                                      notification_feed)
from ..services.vaccinations import animal_vax_info
from ..storage import get_settings
from .animals import get_animal_or_404


# ---------- notifications ----------
@app.route("/animals/<animal_id>/notify", methods=["GET", "POST"])
@permission_required("animals.edit")
def animal_notify(animal_id):
    animal = get_animal_or_404(animal_id)
    info = animal_vax_info(animal_id)
    form = {"recipient": "owner", "custom_email": "", "type": "Upcoming Vaccination",
            "vaccination_id": info["records"][0]["vaccination_id"] if info["records"] else "",
            "subject": "", "message": ""}
    if request.method == "POST":
        form.update({k: request.form.get(k, "").strip() for k in ("recipient", "custom_email", "type", "vaccination_id")})
        form["subject"] = request.form.get("subject", "").strip()
        form["message"] = request.form.get("message", "").strip()
        vacc = next((r for r in info["records"] if r["vaccination_id"] == form["vaccination_id"]), None)
        action = request.form.get("action")
        if form["type"] not in NOTIFY_TYPES:
            flash("Please choose a valid notification type.", "error")
        elif action == "preview" or not form["message"]:
            form["subject"], form["message"] = build_message(form["type"], animal, vacc)
            if action == "send":
                flash("Message prepared. Review it, then press Send.", "warning")
        else:
            to = animal.get("owner_email", "") if form["recipient"] == "owner" else form["custom_email"]
            if not valid_email(to):
                flash("Please choose a recipient with a valid email address.", "error")
            elif not form["subject"]:
                flash("Subject is required.", "error")
            else:
                ok, err = notify(animal, to, form["type"], "Manual email", form["subject"], form["message"],
                                 vacc, by=current_user()["username"])
                flash(f"Email sent to {to}." if ok else f"Email failed: {err}", "success" if ok else "error")
                return redirect(url_for("animal_notify", animal_id=animal_id)) if not ok else \
                    redirect(url_for("animal_view", animal_id=animal_id))
    return render_template("notify_form.html", a=animal, info=info, form=form, types=NOTIFY_TYPES,
                           mail_ok=mail_config()["configured"])


@app.route("/notifications")
@permission_required("notifications.view")
def notifications():
    cat = request.args.get("cat", "all")
    cat = cat if cat in NOTE_CATS else "all"
    args = {k: request.args.get(k, "").strip() for k in ("date_from", "date_to", "type", "status", "animal")}
    feed = notification_feed()
    unread = {c: sum(1 for x in feed if x["unread"] and x["cat"] == c) for c in ("vaccination", "inventory", "email")}
    counts = {"all": len(feed), "unread": sum(unread.values()), **{c: sum(1 for x in feed if x["cat"] == c)
              for c in unread}}

    def keep(x):
        if cat == "unread":
            return x["unread"]
        if cat != "all" and x["cat"] != cat:
            return False
        if x["cat"] != "email" or cat != "email":
            return True
        n = x["raw"]
        day = n["datetime"][:10]
        return not ((args["date_from"] and day < args["date_from"]) or (args["date_to"] and day > args["date_to"])
                    or (args["type"] and n["type"] != args["type"]) or (args["status"] and n["status"] != args["status"])
                    or (args["animal"] and args["animal"].lower() not in x["animal"]))
    shown = [x for x in feed if keep(x)]
    hidden_email = 0
    if cat == "all":                         # preview only the newest emails here
        emails = [x for x in shown if x["group"] == "email"]
        hidden_email = max(0, len(emails) - EMAIL_ALL_LIMIT)
        drop = {x["key"] for x in emails[EMAIL_ALL_LIMIT:]}
        shown = [x for x in shown if x["key"] not in drop]
    groups = [{"id": gid, "label": label, "items": [x for x in shown if x["group"] == gid]} for gid, label in NOTE_GROUPS]
    return render_template("notifications.html", groups=[g_ for g_ in groups if g_["items"]], cat=cat, cats=NOTE_CATS,
                           counts=counts, unread=unread, args=args, types=NOTIFY_TYPES, shown=len(shown),
                           hidden_email=hidden_email, mail=mail_config(), enabled=get_settings()["email_enabled"],
                           email_filtered=cat == "email" and any(args.values()))


@app.route("/notifications/read", methods=["POST"])
@permission_required("notifications.view")
def notification_read():
    mark_notifications_read([request.form.get("key", "")])
    return redirect(safe_next(request.form.get("back")) if request.form.get("back") else url_for("notifications"))


@app.route("/notifications/read-all", methods=["POST"])
@permission_required("notifications.view")
def notification_read_all():
    mark_notifications_read([x["key"] for x in notification_feed() if x["unread"]])
    flash("All notifications marked as read.", "success")
    return redirect(safe_next(request.form.get("back")) if request.form.get("back") else url_for("notifications"))


@app.route("/notifications/open", methods=["POST"])
@permission_required("notifications.view")
def notification_open():
    """'View Record': mark the notification read, then go to its animal / inventory record."""
    key = request.form.get("key", "")
    item = next((x for x in notification_feed() if x["key"] == key), None)
    if not item:
        flash("That notification is no longer active.", "warning")
        return redirect(url_for("notifications"))
    mark_notifications_read([key])
    return redirect(item["url"] or url_for("notifications"))


@app.route("/notifications/check", methods=["POST"])
@admin_required
def notification_check():
    if not get_settings()["email_enabled"]:
        flash("Email reminders are turned off. Enable them in Settings first.", "warning")
    elif not mail_config()["configured"]:
        flash("Email is not configured, so no reminders were attempted. Set the MAIL_* values in .env.", "error")
    else:
        s = run_notification_check(current_user()["username"])
        flash(f"Checked {s['checked']} vaccination(s): {s['sent']} sent, {s['failed']} failed, "
              f"{s['duplicate']} already sent earlier, {s['no_email']} skipped (no owner email).",
              "success" if s["failed"] == 0 else "warning")
    return redirect(safe_next(request.form.get("back")) if request.form.get("back") else url_for("notifications"))
