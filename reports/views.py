import csv

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.models import Role
from audit.log import record
from core.permissions import role_required
from ideas.models import Idea, Status

from . import services as svc

REPORT_ROLES = (Role.ADMIN, Role.ADJUDICATOR, Role.OBSERVER)


def _days(request):
    try:
        days = int(request.GET.get("days", 90))
    except ValueError:
        days = 90
    return days if days in svc.PERIODS else 90


@role_required(*REPORT_ROLES)
def dashboard(request):
    data = svc.dashboard(_days(request))
    return render(request, "reports/dashboard.html", {"r": data, "generated": timezone.localtime()})


@role_required(*REPORT_ROLES)
def export_ideas(request):
    """Idea-level data for analysis in Excel or Power BI. Applicant names are left out."""
    days = _days(request)
    ideas = Idea.objects.exclude(status=Status.DRAFT).filter(submitted_at__isnull=False).select_related("award")
    since = svc._since(days)
    if since:
        ideas = ideas.filter(submitted_at__gte=since)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="botlhami-ideas-{timezone.localdate():%Y%m%d}.csv"'
    response.write("﻿")  # so Excel reads the file as UTF-8
    w = csv.writer(response)
    w.writerow(["Reference", "Title", "Sector", "Stage of development", "Location", "Status", "Round", "Submitted",
                "Days in current status", "Combined score", "Jobs expected", "Budget (BWP)", "Award", "Award value (BWP)"])
    for i in ideas.order_by("submitted_at"):
        award = getattr(i, "award", None) if hasattr(i, "award") else None
        w.writerow([
            i.reference, i.title, i.sector, i.maturity, i.location, i.get_status_display(), i.round,
            timezone.localtime(i.submitted_at).strftime("%Y-%m-%d"), i.days_in_status(),
            i.combined_score() if i.status in svc.DECIDED or i.status == Status.ADJUDICATION else "",
            i.jobs if i.jobs is not None else "", i.budget if i.budget is not None else "",
            award.get_category_display() if award else "", award.amount if award and award.amount is not None else "",
        ])
    record("report.exported", target="ideas.csv", detail=svc.PERIODS[days])
    return response
