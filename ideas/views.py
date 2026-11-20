from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Role
from audit.log import record
from core.permissions import role_required

from . import engine
from . import services as svc
from .forms import AwardForm, DecisionForm, EvaluationForm, IdeaForm, MessageForm, MilestoneAddForm, MilestoneUpdateForm, ReturnForm
from .models import STAGES, Award, Idea, IdeaDocument, Milestone, Notification, Status, WorkflowSettings

User = get_user_model()


def _get_visible(request, pk):
    idea = get_object_or_404(Idea, pk=pk)
    if not svc.can_view(request.user, idea):
        record("access.denied", target=idea.reference, detail="Tried to open an idea")
        raise PermissionDenied
    return idea


def _flash_error(request, err):
    messages.error(request, str(err))


# --- submitter --------------------------------------------------------------
@role_required(Role.SUBMITTER)
def my_ideas(request):
    ideas = request.user.ideas.all()
    return render(request, "ideas/my_ideas.html", {"ideas": ideas, "stages": STAGES})


@role_required(Role.SUBMITTER)
def idea_edit(request, pk=None):
    idea = None
    if pk:
        idea = get_object_or_404(Idea, pk=pk, submitter=request.user)
        if not idea.editable_by_submitter:
            messages.warning(request, "This idea is with the panel and can't be edited right now.")
            return redirect("ideas:detail", pk=idea.pk)
    form = IdeaForm(request.POST or None, request.FILES or None, instance=idea)
    if request.method == "POST" and form.is_valid():
        is_new = idea is None
        idea = form.save(commit=False)
        if is_new:
            idea.submitter = request.user
        idea.save()
        for f in form.cleaned_data["documents"]:
            IdeaDocument.objects.create(idea=idea, file=f, original_name=f.name[:200], size=f.size, uploaded_by=request.user)
        record("idea.draft_saved" if is_new else "idea.updated", target=idea.reference)
        if request.POST.get("action") == "submit":
            try:
                svc.submit(idea, request.user)
            except svc.WorkflowError as e:
                _flash_error(request, e)
                return redirect("ideas:edit", pk=idea.pk)
            messages.success(request, f"Submitted. Your reference number is {idea.reference}.")
            return redirect("ideas:detail", pk=idea.pk)
        messages.success(request, "Draft saved.")
        return redirect("ideas:edit", pk=idea.pk)
    last_note = idea.history.filter(to_status=Status.REVISION).last() if idea else None
    return render(request, "ideas/form.html", {"form": form, "idea": idea, "revision_note": last_note, "missing": idea.missing_items() if idea else None})


@require_POST
@role_required(Role.SUBMITTER)
def delete_document(request, pk, doc_id):
    idea = get_object_or_404(Idea, pk=pk, submitter=request.user)
    if not idea.editable_by_submitter:
        raise PermissionDenied
    doc = get_object_or_404(IdeaDocument, pk=doc_id, idea=idea)
    record("idea.document_deleted", target=idea.reference, detail=doc.original_name)
    doc.file.delete(save=False)
    doc.delete()
    return redirect("ideas:edit", pk=idea.pk)


# --- shared -----------------------------------------------------------------
@login_required
def detail(request, pk):
    idea = _get_visible(request, pk)
    user = request.user
    ws = WorkflowSettings.get()
    full = svc.sees_full_content(user, idea)
    ctx = {
        "idea": idea, "stages": STAGES, "full": full, "ws": ws,
        "hide_applicant": svc.applicant_hidden(user),
        "history": idea.history.select_related("actor"),
        "messages_list": idea.messages.select_related("author") if full else [],
        "message_form": MessageForm(),
        "can_post": full and user.role not in (Role.OBSERVER, Role.CONSULTANT),
    }
    evals = idea.evaluations.select_related("evaluator")
    if user.has_role(Role.ADMIN, Role.ADJUDICATOR):
        ctx["evaluations"] = evals
    elif user.role == Role.EVALUATOR:
        ctx["evaluations"] = evals.filter(evaluator=user)
    elif user.role == Role.SUBMITTER:
        # Feedback appears once a review round is complete; evaluators stay anonymous.
        ctx["feedback"] = [e for e in evals if e.round < idea.round or idea.status not in (Status.SUBMITTED, Status.IN_REVIEW)]

    # action panels
    if user.has_role(Role.ADMIN) and idea.status == Status.SUBMITTED:
        ctx["evaluators"] = User.objects.filter(role=Role.EVALUATOR, is_active=True).annotate(
            open_reviews=Count("assignments", filter=Q(assignments__idea__status=Status.IN_REVIEW, assignments__recused=False))
        )
        ctx["return_form"] = ReturnForm()
    if user.has_role(Role.ADMIN) and idea.status == Status.IN_REVIEW:
        done = set(idea.round_evaluations().values_list("evaluator_id", flat=True))
        ctx["progress"] = [(a, a.evaluator_id in done) for a in idea.active_assignments()]
        assigned = idea.assignments.filter(round=idea.round).values_list("evaluator_id", flat=True)
        ctx["spare_evaluators"] = User.objects.filter(role=Role.EVALUATOR, is_active=True).exclude(pk__in=assigned)
    if (user.role == Role.EVALUATOR and idea.status == Status.IN_REVIEW
            and idea.active_assignments().filter(evaluator=user).exists()
            and not idea.round_evaluations().filter(evaluator=user).exists()):
        ctx["eval_form"] = EvaluationForm(criteria=svc.active_criteria())
    if user.has_role(Role.ADJUDICATOR) and idea.status == Status.ADJUDICATION:
        ctx["decision_form"] = DecisionForm()
    if user.has_role(Role.ADJUDICATOR, Role.ADMIN) and idea.status == Status.APPROVED:
        ctx["award_form"] = AwardForm()
    # Evaluators never see others' scores (it would anchor their own); applicants see the
    # combined score only once the round is finished.
    round_closed = idea.status not in (Status.SUBMITTED, Status.IN_REVIEW)
    if user.has_role(Role.ADMIN, Role.ADJUDICATOR) or user.role == Role.OBSERVER or (user.role == Role.SUBMITTER and round_closed):
        ctx["combined"] = idea.combined_score()
        ctx["gap"] = idea.score_gap()
    if user.has_role(*ENGINE_ROLES) and idea.status not in (Status.DRAFT, Status.SUBMITTED):
        ctx["engine"] = engine.analyse(idea)
    award = getattr(idea, "award", None) if idea.status == Status.AWARDED else None
    if award:
        ctx["award"] = award
        ctx["plan"] = award.milestones.select_related("updated_by", "confirmed_by")
        ctx["plan_progress"] = award.progress()
        ctx["plan_staff"] = svc.can_manage_implementation(user, award)
        ctx["plan_applicant"] = user.pk == idea.submitter_id
        ctx["milestone_statuses"] = Milestone.Status.choices
        if ctx["plan_staff"]:
            ctx["milestone_add_form"] = MilestoneAddForm()
    if full and user.pk != idea.submitter_id:
        record("idea.viewed", target=idea.reference)  # who opened whose IP, for the audit trail
    return render(request, "ideas/detail.html", ctx)


@login_required
def download_document(request, pk, doc_id):
    idea = _get_visible(request, pk)
    if not svc.sees_full_content(request.user, idea):
        raise PermissionDenied
    doc = get_object_or_404(IdeaDocument, pk=doc_id, idea=idea)
    if not doc.file:
        raise Http404
    record("idea.document_downloaded", target=idea.reference, detail=doc.original_name)
    return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.original_name)


@require_POST
@login_required
def post_message(request, pk):
    idea = _get_visible(request, pk)
    form = MessageForm(request.POST)
    if form.is_valid():
        try:
            svc.post_message(idea, request.user, form.cleaned_data["body"])
        except svc.WorkflowError as e:
            _flash_error(request, e)
    return redirect("ideas:detail", pk=idea.pk)


# --- administrator ----------------------------------------------------------
@role_required(Role.ADMIN)
def screening(request):
    ws = WorkflowSettings.get()
    new = Idea.objects.filter(status=Status.SUBMITTED).select_related("submitter")
    in_review = Idea.objects.filter(status=Status.IN_REVIEW).prefetch_related("assignments__evaluator", "evaluations")
    rows = []
    for idea in in_review:
        done = set(idea.round_evaluations().values_list("evaluator_id", flat=True))
        rows.append((idea, [(a, a.evaluator_id in done) for a in idea.active_assignments()]))
    return render(request, "ideas/screening.html", {"new": new, "rows": rows, "ws": ws})


@require_POST
@role_required(Role.ADMIN)
def screen(request, pk):
    idea = get_object_or_404(Idea, pk=pk)
    try:
        if request.POST.get("action") == "return":
            svc.return_to_applicant(idea, request.user, request.POST.get("note", ""))
            messages.success(request, f"{idea.reference} was returned to the applicant.")
        else:
            evaluators = list(User.objects.filter(pk__in=request.POST.getlist("evaluators"), role=Role.EVALUATOR))
            svc.accept_and_assign(idea, request.user, evaluators)
            messages.success(request, f"{idea.reference} accepted. The evaluators have been notified.")
    except svc.WorkflowError as e:
        _flash_error(request, e)
        return redirect("ideas:detail", pk=idea.pk)
    return redirect("ideas:screening")


@require_POST
@role_required(Role.ADMIN)
def remind(request, pk):
    idea = get_object_or_404(Idea, pk=pk)
    n = svc.remind_evaluators(idea, request.user)
    messages.success(request, f"Reminder sent to {n} evaluator{'s' if n != 1 else ''}.")
    return redirect(request.POST.get("next") or "ideas:screening")


@require_POST
@role_required(Role.ADMIN)
def add_evaluator(request, pk):
    idea = get_object_or_404(Idea, pk=pk)
    ev = get_object_or_404(User, pk=request.POST.get("evaluator"), role=Role.EVALUATOR)
    try:
        svc.add_evaluator(idea, request.user, ev)
        messages.success(request, f"{ev} has been added to {idea.reference}.")
    except svc.WorkflowError as e:
        _flash_error(request, e)
    return redirect("ideas:detail", pk=idea.pk)


# --- evaluator --------------------------------------------------------------
@role_required(Role.EVALUATOR)
def queue(request):
    pending = []
    for a in request.user.assignments.filter(recused=False, idea__status=Status.IN_REVIEW).select_related("idea"):
        if a.round == a.idea.round and not a.idea.round_evaluations().filter(evaluator=request.user).exists():
            pending.append(a)
    done = request.user.evaluations.select_related("idea").order_by("-submitted_at")
    return render(request, "ideas/queue.html", {"pending": pending, "done": done, "now": timezone.now()})


@require_POST
@role_required(Role.EVALUATOR)
def evaluate(request, pk):
    idea = _get_visible(request, pk)
    form = EvaluationForm(request.POST, criteria=svc.active_criteria())
    if not form.is_valid():
        messages.error(request, "Score every criterion, write feedback and choose a recommendation.")
        return redirect("ideas:detail", pk=idea.pk)
    try:
        svc.submit_evaluation(
            idea, request.user, form.scores(), form.cleaned_data["comment"], form.cleaned_data["recommendation"],
            form.cleaned_data["private_note"], form.cleaned_data["coi_declared"],
        )
    except svc.WorkflowError as e:
        _flash_error(request, e)
        return redirect("ideas:detail", pk=idea.pk)
    messages.success(request, "Evaluation submitted. Thank you.")
    return redirect("ideas:queue")


@require_POST
@role_required(Role.EVALUATOR)
def recuse(request, pk):
    idea = _get_visible(request, pk)
    try:
        svc.recuse(idea, request.user)
        messages.success(request, "You've recused yourself. The Innovation Office has been told.")
    except svc.WorkflowError as e:
        _flash_error(request, e)
    return redirect("ideas:queue")


# --- adjudicator ------------------------------------------------------------
@role_required(Role.ADJUDICATOR, Role.ADMIN)
def adjudication(request):
    ws = WorkflowSettings.get()
    pending = [(i, engine.analyse(i, ws)) for i in Idea.objects.filter(status=Status.ADJUDICATION)]
    approved = Idea.objects.filter(status=Status.APPROVED)
    return render(request, "ideas/adjudication.html", {"pending": pending, "approved": approved, "ws": ws})


ENGINE_ROLES = (Role.ADMIN, Role.ADJUDICATOR)


@role_required(*ENGINE_ROLES)
def score_report(request, pk):
    """The evaluation engine's full report on one idea: radar, criterion table, flags and recommendation."""
    idea = get_object_or_404(Idea, pk=pk)
    a = engine.analyse(idea)
    ctx = {"idea": idea, "a": a}
    if a:
        ctx["legend"] = [(f"Evaluator {l}", engine.SERIES[i % len(engine.SERIES)], False) for i, l in enumerate(a.letters)]
        if len(a.evaluations) > 1:
            ctx["legend"].append(("Average", engine.INK, True))
        ctx["rows"] = [(c, [e.scores.get(c.id) for e in a.evaluations]) for c in a.criteria]
    if idea.status == Status.ADJUDICATION:
        assigned = idea.assignments.filter(round=idea.round).values_list("evaluator_id", flat=True)
        ctx["spare_evaluators"] = User.objects.filter(role=Role.EVALUATOR, is_active=True).exclude(pk__in=assigned)
    record("report.score_viewed", target=idea.reference)
    return render(request, "ideas/score_report.html", ctx)


@require_POST
@role_required(*ENGINE_ROLES)
def further_assessment(request, pk):
    idea = get_object_or_404(Idea, pk=pk)
    ev = get_object_or_404(User, pk=request.POST.get("evaluator"), role=Role.EVALUATOR)
    try:
        svc.request_further_assessment(idea, request.user, ev)
        messages.success(request, f"{ev} has been asked for a further assessment of {idea.reference}.")
    except svc.WorkflowError as e:
        _flash_error(request, e)
    return redirect("ideas:score_report", pk=idea.pk)


@role_required(*ENGINE_ROLES)
def score_portfolio(request):
    """Every scored idea side by side, with a radar comparing up to five of them."""
    ws = WorkflowSettings.get()
    ideas = Idea.objects.exclude(status__in=(Status.DRAFT, Status.SUBMITTED))
    rows = [r for r in (engine.portfolio_row(i, ws) for i in ideas) if r]
    sort = request.GET.get("sort", "score")
    keys = {
        "score": lambda r: -r["a"].combined,
        "spread": lambda r: -r["a"].total_sd,
        "title": lambda r: r["idea"].title.lower(),
        "verdict": lambda r: [engine.FURTHER, engine.APPROVE, engine.DECLINE, engine.WAITING].index(r["a"].verdict),
    }
    rows.sort(key=keys.get(sort, keys["score"]))
    try:
        chosen = [int(x) for x in request.GET.getlist("compare")][:5]
    except ValueError:
        chosen = []
    if not chosen:  # by default, compare the ideas waiting for a decision
        waiting = [r["idea"].pk for r in rows if r["idea"].status == Status.ADJUDICATION]
        chosen = (waiting or [r["idea"].pk for r in sorted(rows, key=keys["score"])])[:3]
    compare = [r for r in rows if r["idea"].pk in chosen][:5]
    criteria = [c.name for c in svc.active_criteria()]
    series = []
    for n, r in enumerate(compare):
        by_name = {c.name: c.avg for c in r["a"].criteria}
        series.append((f"{r['idea'].reference} {r['idea'].title.split(':')[0]}", [by_name.get(name) for name in criteria],
                       engine.SERIES[n % len(engine.SERIES)], False))
        r["colour"] = engine.SERIES[n % len(engine.SERIES)]
    radar = engine.radar_svg(criteria, series, size=320, title="Average criterion scores of the compared ideas") if series else ""
    return render(request, "ideas/score_portfolio.html", {
        "rows": rows, "sort": sort, "chosen": [r["idea"].pk for r in compare], "compare": compare, "radar": radar,
        "ws": ws, "counts": {v: sum(1 for r in rows if r["a"].verdict == v) for v in engine.LABELS},
    })


@require_POST
@role_required(Role.ADJUDICATOR)
def decide(request, pk):
    idea = get_object_or_404(Idea, pk=pk)
    form = DecisionForm(request.POST)
    outcome = request.POST.get("outcome")
    try:
        if not form.is_valid():
            raise svc.WorkflowError("Give a reason for the decision.")
        svc.decide(idea, request.user, outcome, form.cleaned_data["reason"])
        messages.success(request, "Decision recorded and the applicant notified.")
    except svc.WorkflowError as e:
        _flash_error(request, e)
    return redirect("ideas:detail", pk=idea.pk)


@require_POST
@role_required(Role.ADJUDICATOR, Role.ADMIN)
def award(request, pk):
    idea = get_object_or_404(Idea, pk=pk)
    form = AwardForm(request.POST)
    try:
        if not form.is_valid():
            raise svc.WorkflowError("Choose an award type and write a message to the applicant.")
        d = form.cleaned_data
        svc.grant_award(idea, request.user, d["category"], d["message"], d.get("amount"), d.get("officer"))
        messages.success(request, "Award granted. A standard implementation plan has been set up; adjust it below if needed.")
    except svc.WorkflowError as e:
        _flash_error(request, e)
    return redirect("ideas:detail", pk=idea.pk)


@require_POST
@login_required
def milestone_update(request, pk, mid):
    idea = _get_visible(request, pk)
    m = get_object_or_404(Milestone, pk=mid, award__idea=idea)
    form = MilestoneUpdateForm(request.POST)
    try:
        if not form.is_valid():
            raise svc.WorkflowError("Choose a status.")
        if request.POST.get("action") == "confirm":
            svc.confirm_milestone(m, request.user)
            messages.success(request, f"Confirmed: {m.title}.")
        else:
            svc.update_milestone(m, request.user, form.cleaned_data["status"], form.cleaned_data["note"])
            messages.success(request, f"Updated: {m.title}.")
    except svc.WorkflowError as e:
        _flash_error(request, e)
    return redirect(f"{reverse('ideas:detail', args=[idea.pk])}#plan")


@require_POST
@login_required
def milestone_add(request, pk):
    idea = _get_visible(request, pk)
    award = get_object_or_404(Award, idea=idea)
    form = MilestoneAddForm(request.POST)
    try:
        if not form.is_valid():
            raise svc.WorkflowError("Give the milestone a title and a due date.")
        d = form.cleaned_data
        svc.add_milestone(award, request.user, d["title"], d["due_date"], d["description"])
        messages.success(request, "Milestone added.")
    except svc.WorkflowError as e:
        _flash_error(request, e)
    return redirect(f"{reverse('ideas:detail', args=[idea.pk])}#plan")


@role_required(Role.ADMIN, Role.ADJUDICATOR, Role.OBSERVER, Role.CONSULTANT)
def implementation(request):
    """Every awarded idea and how its implementation is going."""
    awards = Award.objects.select_related("idea", "officer").prefetch_related("milestones").order_by("-granted_at")
    if request.user.role == Role.CONSULTANT:
        awards = awards.filter(officer=request.user)
    rows = [(a, a.progress()) for a in awards]
    totals = {
        "awards": len(rows),
        "done": sum(p["done"] for _, p in rows), "total": sum(p["total"] for _, p in rows),
        "overdue": sum(p["overdue"] for _, p in rows), "at_risk": sum(p["at_risk"] for _, p in rows),
        "waiting": sum(1 for a, _ in rows for m in a.milestones.all() if m.awaiting_confirmation),
    }
    return render(request, "ideas/implementation.html", {"rows": rows, "totals": totals})


# --- pipeline and notifications --------------------------------------------
@role_required(Role.ADMIN, Role.ADJUDICATOR, Role.OBSERVER)
def pipeline(request):
    ws = WorkflowSettings.get()
    columns = []
    for status in [Status.SUBMITTED, Status.IN_REVIEW, Status.REVISION, Status.ADJUDICATION, Status.APPROVED, Status.AWARDED, Status.REJECTED]:
        ideas = list(Idea.objects.filter(status=status).order_by("status_changed_at"))
        for i in ideas:
            i.overdue = i.is_overdue(ws)
        columns.append((status.label, ideas))
    return render(request, "ideas/pipeline.html", {"columns": columns})


@login_required
def notifications(request):
    items = request.user.notifications.select_related("idea")[:100]
    if request.method == "POST":
        request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
        return redirect("ideas:notifications")
    return render(request, "ideas/notifications.html", {"items": items})
