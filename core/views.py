from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def home(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return render(request, "core/home.html")


HOME_BY_ROLE = {
    "submitter": "ideas:mine",
    "evaluator": "ideas:queue",
    "adjudicator": "ideas:adjudication",
    "admin": "ideas:screening",
    "observer": "ideas:pipeline",
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
