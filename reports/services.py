"""Figures for the reports dashboard: participation, outcomes and timelines."""

from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.utils import timezone

from accounts.models import Role
from ideas.models import LOCATIONS, SECTORS, Assignment, Award, Evaluation, Idea, StatusEvent, Status, WorkflowSettings
from support.models import Ticket

User = get_user_model()

PERIODS = {30: "Last 30 days", 90: "Last 90 days", 365: "Last 12 months", 0: "All time"}
DECIDED = (Status.APPROVED, Status.AWARDED, Status.REJECTED)
# Stages whose time is measured, with the WorkflowSettings field holding each target.
TIMED_STAGES = [
    (Status.SUBMITTED, "Screening", "screening_days"),
    (Status.IN_REVIEW, "Evaluation", "evaluation_days"),
    (Status.ADJUDICATION, "Adjudication", "adjudication_days"),
    (Status.REVISION, "Applicant revising", None),
]


def _since(days):
    return timezone.now() - timedelta(days=days) if days else None


def _months(n=12):
    """First day of each of the last n months, oldest first."""
    today = timezone.localdate().replace(day=1)
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _pct(part, whole):
    return round(part * 100 / whole) if whole else None


def _avg(xs):
    return round(sum(xs) / len(xs), 1) if xs else None


def stage_durations(ideas):
    """Average days spent in each timed stage, from the status history of completed stages."""
    ids = list(ideas.values_list("pk", flat=True))
    events = defaultdict(list)
    for e in StatusEvent.objects.filter(idea_id__in=ids).order_by("idea_id", "at", "id").values("idea_id", "to_status", "at"):
        events[e["idea_id"]].append(e)
    spans = defaultdict(list)
    to_decision = []
    for evs in events.values():
        submitted = None
        for a, b in zip(evs, evs[1:]):
            spans[a["to_status"]].append((b["at"] - a["at"]).total_seconds() / 86400)
        for e in evs:
            if e["to_status"] == Status.SUBMITTED and submitted is None:
                submitted = e["at"]
            if e["to_status"] in (Status.APPROVED, Status.REJECTED) and submitted:
                to_decision.append((e["at"] - submitted).total_seconds() / 86400)
                break
    ws = WorkflowSettings.get()
    rows = []
    for status, label, field in TIMED_STAGES:
        target = getattr(ws, field) if field else None
        avg = _avg(spans.get(status, []))
        rows.append({"label": label, "avg": avg, "n": len(spans.get(status, [])), "target": target,
                     "late": bool(target and avg is not None and avg > target)})
    scale = max([r["avg"] or 0 for r in rows] + [r["target"] or 0 for r in rows] + [1])
    for r in rows:
        r["bar"] = round((r["avg"] or 0) * 100 / scale)
        r["mark"] = round(r["target"] * 100 / scale) if r["target"] else None
    return rows, _avg(to_decision)


def dashboard(days=90):
    since = _since(days)
    submitted = Idea.objects.exclude(status=Status.DRAFT).filter(submitted_at__isnull=False)
    in_period = submitted.filter(submitted_at__gte=since) if since else submitted
    applicants = User.objects.filter(role=Role.SUBMITTER)
    new_applicants = applicants.filter(date_joined__gte=since) if since else applicants

    decided = in_period.filter(status__in=DECIDED)
    approved = decided.filter(status__in=(Status.APPROVED, Status.AWARDED)).count()
    awards = Award.objects.filter(idea__in=in_period)
    award_value = awards.aggregate(v=Sum("amount"))["v"]

    # Participation
    month_counts = Counter((d.year, d.month) for d in (timezone.localtime(x) for x in submitted.values_list("submitted_at", flat=True)))
    months = [{"label": f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1]} {str(y)[2:]}", "n": month_counts.get((y, m), 0)} for y, m in _months(12)]
    peak_m = max([x["n"] for x in months] + [1])
    for x in months:
        x["h"] = round(x["n"] * 100 / peak_m)
    by_sector = _ranked(in_period, "sector", SECTORS)
    by_location = _ranked(in_period, "location", LOCATIONS)
    ideas_per_applicant = in_period.values("submitter").distinct().count()

    # Outcomes
    order = [Status.SUBMITTED, Status.IN_REVIEW, Status.REVISION, Status.ADJUDICATION, Status.APPROVED, Status.AWARDED, Status.REJECTED]
    status_counts = dict(in_period.values_list("status").annotate(n=Count("id")))
    peak_s = max(list(status_counts.values()) + [1])
    by_status = [{"status": s, "label": Status(s).label, "n": status_counts.get(s, 0), "w": round(status_counts.get(s, 0) * 100 / peak_s)} for s in order]
    scores = [i.combined_score() for i in decided]
    scores = [s for s in scores if s is not None]
    revised = in_period.filter(history__to_status=Status.REVISION).distinct().count()

    # Timelines
    stages, avg_to_decision = stage_durations(in_period)
    ws = WorkflowSettings.get()
    overdue = [i for i in submitted.filter(status__in=(Status.SUBMITTED, Status.IN_REVIEW, Status.ADJUDICATION)) if i.is_overdue(ws)]
    workload = evaluator_workload(timezone.now())

    # Support
    tickets = Ticket.objects.filter(created_at__gte=since) if since else Ticket.objects.all()
    responded = [t for t in tickets if t.response_met is not None]
    resolved = [t for t in tickets if t.resolution_met is not None]
    support = {
        "total": tickets.count(),
        "open": Ticket.objects.filter(status__in=Ticket.ACTIVE).count(),
        "response_pct": _pct(sum(1 for t in responded if t.response_met), len(responded)),
        "resolution_pct": _pct(sum(1 for t in resolved if t.resolution_met), len(resolved)),
        "by_level": list(tickets.values("level__label").annotate(n=Count("id")).order_by("level__order")),
    }

    return {
        "days": days, "period_label": PERIODS.get(days, PERIODS[90]), "periods": PERIODS,
        "kpi": {
            "new_applicants": new_applicants.count(), "applicants_total": applicants.count(),
            "submitted": in_period.count(), "submitting_applicants": ideas_per_applicant,
            "decided": decided.count(), "approval_rate": _pct(approved, decided.count()),
            "awards": awards.count(), "award_value": award_value,
            "avg_to_decision": avg_to_decision, "avg_score": _avg(scores), "revised": revised,
        },
        "months": months, "by_sector": by_sector, "by_location": by_location, "by_status": by_status,
        "stages": stages, "overdue": overdue, "workload": workload, "support": support,
    }


def _ranked(qs, field, known):
    counts = dict(qs.exclude(**{field: ""}).values_list(field).annotate(n=Count("id")))
    rows = sorted(({"label": k, "n": v} for k, v in counts.items() if v), key=lambda r: -r["n"])
    peak = max([r["n"] for r in rows] + [1])
    for r in rows:
        r["w"] = round(r["n"] * 100 / peak)
    return rows


def evaluator_workload(now):
    rows = []
    for u in User.objects.filter(role=Role.EVALUATOR, is_active=True).order_by("first_name"):
        active = Assignment.objects.filter(evaluator=u, recused=False, idea__status=Status.IN_REVIEW).select_related("idea")
        pending = [a for a in active if a.round == a.idea.round and not Evaluation.objects.filter(idea=a.idea, evaluator=u, round=a.round).exists()]
        rows.append({
            "name": f"{u.first_name} {u.last_name}".strip() or u.email,
            "pending": len(pending),
            "late": sum(1 for a in pending if a.due_at < now),
            "done": Evaluation.objects.filter(evaluator=u).count(),
            "recused": Assignment.objects.filter(evaluator=u, recused=True).count(),
        })
    return rows
