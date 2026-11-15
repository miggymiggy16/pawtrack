"""
PawTrack - analytics page and the per-card detail reports
"""
from flask import abort, render_template

from ..extensions import app
from ..security import permission_required
from ..services.analytics import (ANALYTICS_OPEN_IN_REPORTS, ANALYTICS_REPORTS,
                                  analytics_data, build_analytics_report)


@app.route("/analytics")
@permission_required("analytics.view")
def analytics():
    return render_template("analytics.html", d=analytics_data())


@app.route("/analytics/report/<key>")
@permission_required("analytics.view")
def analytics_report(key):
    if key not in ANALYTICS_REPORTS:
        abort(404)
    return render_template("analytics_report.html", r=build_analytics_report(key),
                           reports_kind=ANALYTICS_OPEN_IN_REPORTS[key])
