"""
PawTrack - filterable reports and CSV/PDF export
"""
import csv
import io
from datetime import datetime

from flask import Response, abort, flash, render_template, request

from ..config import CATEGORIES, SPECIES_CHOICES
from ..extensions import app
from ..helpers import _safe_cell, now_str
from ..security import permission_required
from ..services.reports import (FILTER_LABELS, REPORT_FILTER_HINTS,
                                REPORT_FILTERS, REPORT_GROUPS,
                                REPORT_TAB_LABELS, REPORTS, build_report,
                                pdf_report)
from ..storage import get_settings, load


def report_args(kind):
    return {k: request.args.get(k, "").strip() for k in REPORT_FILTERS[kind]}


@app.route("/reports")
@permission_required("reports.view")
def reports():
    kind = request.args.get("type", "vaccination")
    if kind not in REPORTS:
        kind = "vaccination"
    args = report_args(kind)
    if args.get("date_from") and args.get("date_to") and args["date_from"] > args["date_to"]:
        flash("The 'From' date is later than the 'To' date, so no records can match.", "warning")
    chips = [(FILTER_LABELS[k], v) for k, v in args.items() if v]
    animals = load("animals")
    return render_template("reports.html", kind=kind, reports=REPORTS, groups=REPORT_GROUPS, args=args, chips=chips,
                           tab_labels=REPORT_TAB_LABELS, hint=REPORT_FILTER_HINTS[kind],
                           generated=now_str(), report=build_report(kind, args),
                           filters=REPORT_FILTERS[kind], categories=CATEGORIES,
                           species=sorted({a["species"] for a in animals} | set(SPECIES_CHOICES)),
                           vaccines=sorted({v["vaccine_name"] for v in load("vaccinations")}))


@app.route("/reports/export")
@permission_required("reports.view")
def report_export():
    kind = request.args.get("type", "population")
    fmt = request.args.get("format", "csv")
    if kind not in REPORTS:
        abort(404)
    args = report_args(kind)
    report = build_report(kind, args)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    filters = ", ".join(f"{k}={v}" for k, v in args.items() if v) or "none"
    if fmt == "pdf":
        return pdf_report(report, filters, f"PawTrack-{kind}-{stamp}.pdf")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([get_settings()["clinic"]["name"], report["title"]])
    w.writerow(["Generated", now_str(), "Filters", filters])
    for sec in report["sections"]:
        w.writerow([])
        w.writerow([sec["title"]])
        w.writerow(sec["headers"])
        for row in sec["rows"]:
            w.writerow([_safe_cell(c) for c in row])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=PawTrack-{kind}-{stamp}.csv"})
