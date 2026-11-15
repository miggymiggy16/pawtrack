"""
PawTrack - email and notification history
=========================================
send_email() talks to the SMTP server configured in .env. notify() sends and
always writes a history row (Sent or Failed with the real error), so the
history never lies. run_notification_check() emails owners whose current
vaccination records need attention, once per (record, type, due date).
"""
import os
import smtplib
from email.message import EmailMessage

from ..helpers import fmt_date, now_str, valid_email
from ..storage import edit, get_settings, load, next_id
from .vaccinations import all_vax_rows


def mail_config():
    cfg = {
        "server": os.getenv("MAIL_SERVER", "").strip(),
        "port": int(os.getenv("MAIL_PORT", "587") or 587),
        "username": os.getenv("MAIL_USERNAME", "").strip(),
        "password": os.getenv("MAIL_PASSWORD", ""),
        "use_tls": os.getenv("MAIL_USE_TLS", "True").strip().lower() in ("1", "true", "yes", "on"),
    }
    placeholders = {"your_email@gmail.com", "your_google_app_password", ""}
    cfg["configured"] = bool(cfg["server"] and cfg["username"] not in placeholders
                             and cfg["password"] not in placeholders)
    return cfg


def send_email(to_addr, subject, body):
    """Send one real email over SMTP. Returns (True, '') or (False, 'reason')."""
    cfg = mail_config()
    if not cfg["configured"]:
        return False, "Email is not configured. Fill in MAIL_* values in your .env file and restart PawTrack."
    clinic = get_settings()["clinic"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{clinic['name']} <{cfg['username']}>"
    msg["To"] = to_addr
    if clinic.get("email"):
        msg["Reply-To"] = clinic["email"]
    msg.set_content(body)
    try:
        if cfg["port"] == 465:
            server = smtplib.SMTP_SSL(cfg["server"], cfg["port"], timeout=15)
        else:
            server = smtplib.SMTP(cfg["server"], cfg["port"], timeout=15)
            if cfg["use_tls"]:
                server.starttls()
        with server:
            server.login(cfg["username"], cfg["password"])
            server.send_message(msg)
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP login failed. Use a Google App Password (not your normal Gmail password)."
    except Exception as exc:                                   # network, DNS, TLS...
        return False, f"{type(exc).__name__}: {exc}"


def build_message(ntype, animal, vacc=None):
    """Default subject + body for each notification type."""
    c = get_settings()["clinic"]
    owner = animal.get("owner_name") or "Pet Owner"
    sign = f"\n\nThank you,\n{c['name']}"
    if c.get("phone"):
        sign += f"\nPhone: {c['phone']}"
    if c.get("address"):
        sign += f"\nAddress: {c['address']}"
    if c.get("email"):
        sign += f"\nEmail: {c['email']}"
    name = animal["animal_name"]
    vname = vacc["vaccine_name"] if vacc else "vaccination"
    due = fmt_date(vacc.get("next_due_date")) if vacc and vacc.get("next_due_date") else "to be scheduled"
    given = fmt_date(vacc["date_administered"]) if vacc else "-"
    if ntype == "Upcoming Vaccination":
        return (f"Upcoming vaccination for {name}",
                f"Hello {owner},\n\nThis is a friendly reminder that {name}'s {vname} vaccination is "
                f"due on {due}. Please visit the clinic on or before that date to keep {name} protected.{sign}")
    if ntype == "Due Today":
        return (f"{name}'s vaccination is due today",
                f"Hello {owner},\n\n{name}'s {vname} vaccination is due today ({due}). "
                f"Please visit the clinic today if possible.{sign}")
    if ntype == "Overdue Vaccination":
        return (f"Overdue vaccination for {name}",
                f"Hello {owner},\n\n{name}'s {vname} vaccination was due on {due} and is now overdue. "
                f"Please schedule a visit as soon as you can.{sign}")
    if ntype == "Vaccination Updated":
        return (f"Vaccination record updated for {name}",
                f"Hello {owner},\n\nWe updated {name}'s vaccination record.\nVaccine: {vname}\n"
                f"Date administered: {given}\nNext due date: {due}{sign}")
    return (f"{c['name']} - test email",
            f"This is a test email from PawTrack.\n\nIf you can read this, your email settings work.{sign}")


def log_notification(animal, to_addr, ntype, purpose, message, ok, error, vacc=None, key="", by=""):
    with edit("notifications") as notes:
        notes.append({
            "notification_id": next_id("NTF", notes, "notification_id", 5),
            "datetime": now_str(),
            "animal_id": animal["animal_id"] if animal else "",
            "animal_name": animal["animal_name"] if animal else "-",
            "owner_name": (animal or {}).get("owner_name", "") or "-",
            "email": to_addr, "type": ntype, "purpose": purpose, "message": message,
            "status": "Sent" if ok else "Failed", "error": error,
            "vaccination_id": vacc["vaccination_id"] if vacc else "",
            "reminder_key": key, "sent_by": by})


def notify(animal, to_addr, ntype, purpose, subject, body, vacc=None, key="", by=""):
    """Send + record. The history always tells the truth about success/failure."""
    ok, err = send_email(to_addr, subject, body)
    log_notification(animal, to_addr, ntype, purpose, body, ok, err, vacc, key, by)
    return ok, err


def run_notification_check(by="system"):
    """Look at all CURRENT vaccination records and email owners who are eligible.
    Each (record, type, due date) is emailed only once - duplicates are skipped."""
    summary = {"sent": 0, "failed": 0, "duplicate": 0, "no_email": 0, "checked": 0}
    type_for = {"Upcoming": "Upcoming Vaccination", "Due Today": "Due Today",
                "Overdue": "Overdue Vaccination"}
    done = {n.get("reminder_key") for n in load("notifications")
            if n.get("status") == "Sent" and n.get("reminder_key")}
    for r in all_vax_rows():
        if not r["is_current"] or r["status"] not in type_for:
            continue
        summary["checked"] += 1
        a, ntype = r["animal"], type_for[r["status"]]
        key = f"{r['vaccination_id']}|{ntype}|{r.get('next_due_date')}"
        if key in done:
            summary["duplicate"] += 1
            continue
        if not valid_email(a.get("owner_email", "")):
            summary["no_email"] += 1
            continue
        subject, body = build_message(ntype, a, r)
        ok, _ = notify(a, a["owner_email"], ntype, "Automatic reminder check", subject, body, r, key, by)
        summary["sent" if ok else "failed"] += 1
    return summary
