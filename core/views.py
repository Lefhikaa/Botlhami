from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def home(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return render(request, "core/home.html", {"stats": platform_stats()})


def platform_stats():
    """Live counts for the home page. Drafts aren't counted: they haven't been submitted yet."""
    from django.db.models import Count, Q, Sum

    from ideas.models import Idea, Status

    under_review = (Status.SUBMITTED, Status.IN_REVIEW, Status.ADJUDICATION, Status.REVISION)
    approved = (Status.APPROVED, Status.AWARDED)
    agg = Idea.objects.exclude(status=Status.DRAFT).aggregate(
        submitted=Count("id"),
        review=Count("id", filter=Q(status__in=under_review)),
        approved=Count("id", filter=Q(status__in=approved)),
        awarded=Count("id", filter=Q(status=Status.AWARDED)),
        jobs=Sum("jobs", filter=Q(status__in=approved)),
    )
    agg["jobs"] = agg["jobs"] or 0
    return agg


HOME_BY_ROLE = {
    "submitter": "ideas:mine",
    "evaluator": "ideas:queue",
    "adjudicator": "ideas:adjudication",
    "admin": "ideas:screening",
    "observer": "ideas:pipeline",
    "consultant": "chat:console",
}


@login_required
def dashboard(request):
    target = HOME_BY_ROLE.get(request.user.role)
    if target:
        return redirect(target)
    return render(request, "core/dashboard.html")


def health(request):
    """Used by Azure's health check and the uptime monitor."""
    from django.db import connection
    from django.http import JsonResponse

    with connection.cursor() as cur:
        cur.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


def denied(request, exception=None):
    return render(request, "403.html", status=403)
