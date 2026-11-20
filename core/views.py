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


@login_required
def search(request):
    """The sidebar search: ideas this person may open, plus help content."""
    from django.db.models import Q as Q_

    from accounts.models import Role
    from ideas.models import Award, Idea, Status
    from support.models import FAQ, Resource

    q = request.GET.get("q", "").strip()[:100]
    ideas, faqs, docs = [], [], []
    if q:
        u = request.user
        found = Idea.objects.filter(Q_(title__icontains=q) | Q_(reference__icontains=q) | Q_(sector__icontains=q))
        if u.has_role(Role.ADMIN, Role.ADJUDICATOR):
            pass
        elif u.role == Role.OBSERVER:
            found = found.exclude(status=Status.DRAFT)
        elif u.role == Role.SUBMITTER:
            found = found.filter(submitter=u)
        elif u.role == Role.EVALUATOR:
            found = found.filter(assignments__evaluator=u)
        elif u.role == Role.CONSULTANT:
            found = found.filter(pk__in=Award.objects.filter(officer=u).values("idea"))
        else:
            found = found.none()
        ideas = list(found.distinct().order_by("-updated_at")[:20])
        faqs = list(FAQ.objects.filter(published=True).filter(Q_(question__icontains=q) | Q_(answer__icontains=q))[:10])
        docs = list(Resource.objects.filter(published=True).filter(Q_(title__icontains=q) | Q_(description__icontains=q))[:10])
    return render(request, "core/search.html", {"q": q, "ideas": ideas, "faqs": faqs, "docs": docs})
