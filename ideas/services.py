"""Workflow rules for ideas. Views call these; tests exercise them directly.

Every state change records a StatusEvent, an audit entry and notifications,
so the tracker, the audit trail and users' alerts always agree.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from audit.log import record

from .models import Assignment, Award, Criterion, Evaluation, Idea, Message, Notification, Status, WorkflowSettings

User = get_user_model()


class WorkflowError(Exception):
    """Raised when an action isn't allowed in the idea's current state."""


# --- notifications ----------------------------------------------------------
def notify(users, text, idea=None):
    users = [u for u in {u.pk: u for u in users if u}.values()]
    Notification.objects.bulk_create([Notification(user=u, idea=idea, text=text[:255]) for u in users])
    link = f"\n\nOpen it in Botlhami: {settings.SITE_URL}{reverse('ideas:detail', args=[idea.pk])}" if idea else ""
    for u in users:
        if u.email_alerts:
            send_mail(f"Botlhami: {text[:70]}", f"{text}{link}\n\nYou can switch off email alerts in your profile.", None, [u.email], fail_silently=True)


def users_with_role(*roles):
    return list(User.objects.filter(role__in=roles, is_active=True))


# --- access -----------------------------------------------------------------
def can_view(user, idea):
    if not user.is_authenticated:
        return False
    if user.has_role(Role.ADMIN, Role.ADJUDICATOR):
        return True
    if user.role == Role.SUBMITTER:
        return idea.submitter_id == user.pk
    if user.role == Role.EVALUATOR:
        return idea.assignments.filter(evaluator=user).exists()
    if user.role == Role.OBSERVER:
        return idea.status != Status.DRAFT
    return False


def sees_full_content(user, idea):
    """Observers track progress only; idea content is the applicant's IP."""
    return can_view(user, idea) and user.role != Role.OBSERVER


def applicant_hidden(user):
    return user.role == Role.EVALUATOR and WorkflowSettings.get().blind_review


# --- submitter actions ------------------------------------------------------
def submit(idea, actor):
    if idea.submitter_id != actor.pk or idea.status not in (Status.DRAFT, Status.REVISION):
        raise WorkflowError("This idea can't be submitted now.")
    missing = idea.missing_items()
    if missing:
        raise WorkflowError("Complete these items first: " + ", ".join(missing))
    if idea.status == Status.REVISION:
        return _resubmit(idea, actor)
    idea.set_status(Status.SUBMITTED, actor)
    record("idea.submitted", target=idea.reference, actor=actor, detail=idea.title)
    notify([actor], f"We received {idea.reference} ({idea.title}). Screening usually takes up to {WorkflowSettings.get().screening_days} working days.", idea)
    notify(users_with_role(Role.ADMIN), f"New submission {idea.reference} is waiting for screening.", idea)
    return idea


def _resubmit(idea, actor):
    previously_screened = idea.assignments.exists()
    idea.round += 1
    idea.save(update_fields=["round"])
    if previously_screened:
        ws = WorkflowSettings.get()
        prior = Assignment.objects.filter(idea=idea, round=idea.round - 1, recused=False)
        for a in prior:
            Assignment.objects.create(idea=idea, evaluator=a.evaluator, round=idea.round, due_at=timezone.now() + timedelta(days=ws.evaluation_days))
        idea.set_status(Status.IN_REVIEW, actor, f"Resubmitted for review round {idea.round}.")
        notify([a.evaluator for a in prior], f"{idea.reference} was revised and is back in your queue (round {idea.round}).", idea)
    else:
        idea.set_status(Status.SUBMITTED, actor, "Resubmitted after screening.")
        notify(users_with_role(Role.ADMIN), f"{idea.reference} was resubmitted and needs screening.", idea)
    record("idea.resubmitted", target=idea.reference, actor=actor, detail=f"Round {idea.round}")
    notify([actor], f"We received your revised {idea.reference}.", idea)
    return idea


# --- administrator actions --------------------------------------------------
@transaction.atomic
def accept_and_assign(idea, actor, evaluators):
    ws = WorkflowSettings.get()
    if idea.status != Status.SUBMITTED:
        raise WorkflowError("Only ideas awaiting screening can be accepted.")
    if idea.missing_items():
        raise WorkflowError("This idea is incomplete. Return it to the applicant instead.")
    evaluators = [e for e in evaluators if e.role == Role.EVALUATOR]
    if len(evaluators) < ws.evaluators_per_idea:
        raise WorkflowError(f"Assign at least {ws.evaluators_per_idea} evaluators.")
    due = timezone.now() + timedelta(days=ws.evaluation_days)
    for ev in evaluators:
        Assignment.objects.get_or_create(idea=idea, evaluator=ev, round=idea.round, defaults={"due_at": due})
    idea.set_status(Status.IN_REVIEW, actor, f"Screened complete; {len(evaluators)} evaluators assigned.")
    record("idea.screened", target=idea.reference, actor=actor, detail="Assigned: " + ", ".join(str(e) for e in evaluators))
    notify(evaluators, f"You have been assigned {idea.reference} for evaluation.", idea)
    notify([idea.submitter], f"{idea.reference} passed screening and is now under evaluation.", idea)


def return_to_applicant(idea, actor, note):
    if idea.status != Status.SUBMITTED:
        raise WorkflowError("Only ideas awaiting screening can be returned.")
    if not note.strip():
        raise WorkflowError("Explain what the applicant needs to fix.")
    idea.set_status(Status.REVISION, actor, note)
    record("idea.returned", target=idea.reference, actor=actor, detail=note)
    notify([idea.submitter], f"{idea.reference} was returned for completion: {note}", idea)


def remind_evaluators(idea, actor):
    done = set(idea.round_evaluations().values_list("evaluator_id", flat=True))
    pending = [a.evaluator for a in idea.active_assignments() if a.evaluator_id not in done]
    notify(pending, f"Reminder: your evaluation of {idea.reference} is due.", idea)
    record("evaluation.reminder", target=idea.reference, actor=actor, detail=", ".join(str(p) for p in pending))
    return len(pending)


# --- evaluator actions ------------------------------------------------------
def active_criteria():
    return list(Criterion.objects.filter(active=True))


@transaction.atomic
def submit_evaluation(idea, evaluator, scores, comment, recommendation, private_note="", coi_declared=False):
    if idea.status != Status.IN_REVIEW or not idea.active_assignments().filter(evaluator=evaluator).exists():
        raise WorkflowError("You aren't assigned to this idea, or it isn't under evaluation.")
    if idea.round_evaluations().filter(evaluator=evaluator).exists():
        raise WorkflowError("You've already evaluated this round.")
    if not coi_declared:
        raise WorkflowError("Confirm you have no conflict of interest, or recuse yourself.")
    criteria = active_criteria()
    rubric = [{"id": c.pk, "name": c.name, "weight": c.weight} for c in criteria]
    clean = {}
    for c in criteria:
        v = int(scores.get(str(c.pk)) or scores.get(c.pk) or 0)
        if not 1 <= v <= 5:
            raise WorkflowError(f'Score "{c.name}" from 1 to 5.')
        clean[str(c.pk)] = v
    if len(comment.strip()) < 20:
        raise WorkflowError("Write at least 20 characters of feedback for the applicant.")
    ev = Evaluation.objects.create(
        idea=idea, evaluator=evaluator, round=idea.round, rubric=rubric, scores=clean,
        comment=comment.strip(), private_note=private_note.strip(), recommendation=recommendation, coi_declared=True,
    )
    record("evaluation.submitted", target=idea.reference, actor=evaluator, detail=f"Score {ev.total}; {ev.get_recommendation_display()}")
    notify(users_with_role(Role.ADMIN), f"{evaluator} submitted an evaluation for {idea.reference}.", idea)
    _advance_if_complete(idea)
    return ev


def recuse(idea, evaluator):
    a = idea.active_assignments().filter(evaluator=evaluator).first()
    if not a:
        raise WorkflowError("You aren't assigned to this idea.")
    a.recused = True
    a.save(update_fields=["recused"])
    record("evaluation.recused", target=idea.reference, actor=evaluator, detail="Conflict of interest declared")
    notify(users_with_role(Role.ADMIN), f"{evaluator} recused from {idea.reference}. Please assign a replacement.", idea)
    _advance_if_complete(idea)


def _advance_if_complete(idea):
    if idea.status == Status.IN_REVIEW and idea.all_evaluations_in():
        idea.set_status(Status.ADJUDICATION, None, "All evaluations received.")
        record("evaluation.round_completed", target=idea.reference, detail="Moved to adjudication automatically")
        notify(users_with_role(Role.ADJUDICATOR), f"{idea.reference} has finished evaluation and is ready for adjudication.", idea)
        notify([idea.submitter], f"{idea.reference} has finished evaluation and moved to adjudication.", idea)


def add_evaluator(idea, actor, evaluator):
    if idea.status != Status.IN_REVIEW or evaluator.role != Role.EVALUATOR:
        raise WorkflowError("Evaluators can only be added while an idea is under evaluation.")
    ws = WorkflowSettings.get()
    a, created = Assignment.objects.get_or_create(
        idea=idea, evaluator=evaluator, round=idea.round, defaults={"due_at": timezone.now() + timedelta(days=ws.evaluation_days)}
    )
    if not created and a.recused:
        raise WorkflowError("That evaluator recused from this idea.")
    record("idea.evaluator_added", target=idea.reference, actor=actor, detail=str(evaluator))
    notify([evaluator], f"You have been assigned {idea.reference} for evaluation.", idea)


def request_further_assessment(idea, actor, evaluator, note=""):
    """Send an idea in adjudication back for one more independent evaluation in the same round."""
    if not actor.has_role(Role.ADJUDICATOR, Role.ADMIN):
        raise WorkflowError("Only adjudicators and administrators can ask for a further assessment.")
    if idea.status != Status.ADJUDICATION:
        raise WorkflowError("Further assessment can only be requested while an idea is in adjudication.")
    if evaluator.role != Role.EVALUATOR:
        raise WorkflowError("Choose an evaluator.")
    if idea.assignments.filter(round=idea.round, evaluator=evaluator).exists():
        raise WorkflowError("That evaluator has already been assigned this idea in this round.")
    ws = WorkflowSettings.get()
    with transaction.atomic():
        Assignment.objects.create(idea=idea, evaluator=evaluator, round=idea.round,
                                  due_at=timezone.now() + timedelta(days=ws.evaluation_days))
        idea.set_status(Status.IN_REVIEW, actor, note or "Further assessment requested by the panel.")
    record("idea.further_assessment", target=idea.reference, actor=actor, detail=str(evaluator))
    notify([evaluator], f"You have been asked for an independent assessment of {idea.reference}.", idea)
    notify([idea.submitter], f"{idea.reference} is getting one more independent review before a decision.", idea)


# --- adjudicator actions ----------------------------------------------------
DECISIONS = {
    Status.APPROVED: ("decision.approved", "Good news: {ref} ({title}) has been approved."),
    Status.REVISION: ("decision.revision_requested", "Revision requested on {ref}. See the feedback and resubmit."),
    Status.REJECTED: ("decision.rejected", "A decision has been made on {ref}. Open it to read the panel's feedback."),
}


def decide(idea, adjudicator, outcome, reason):
    if not adjudicator.has_role(Role.ADJUDICATOR):
        raise WorkflowError("Only adjudicators can decide.")
    if idea.status != Status.ADJUDICATION:
        raise WorkflowError("This idea isn't waiting for a decision.")
    if outcome not in DECISIONS:
        raise WorkflowError("Unknown decision.")
    if len(reason.strip()) < 5:
        raise WorkflowError("Give a reason for the decision. The applicant will see it.")
    idea.set_status(outcome, adjudicator, reason.strip())
    action, msg = DECISIONS[outcome]
    record(action, target=idea.reference, actor=adjudicator, detail=reason)
    if outcome == Status.REVISION:
        Message.objects.create(idea=idea, author=adjudicator, body=reason.strip())
    notify([idea.submitter], msg.format(ref=idea.reference, title=idea.title), idea)
    notify([a.evaluator for a in idea.active_assignments()], f"Outcome for {idea.reference}: {idea.get_status_display()}.", idea)
    if outcome == Status.APPROVED:
        notify(users_with_role(Role.ADMIN), f"{idea.reference} is approved and waiting for an award.", idea)


def grant_award(idea, actor, category, message, amount=None):
    if not actor.has_role(Role.ADJUDICATOR, Role.ADMIN):
        raise WorkflowError("You can't grant awards.")
    if idea.status != Status.APPROVED:
        raise WorkflowError("Only approved ideas can receive an award.")
    if not message.strip():
        raise WorkflowError("Add a message to the applicant.")
    award = Award.objects.create(idea=idea, category=category, amount=amount, message=message.strip(), granted_by=actor)
    idea.set_status(Status.AWARDED, actor, award.get_category_display())
    record("award.granted", target=idea.reference, actor=actor, detail=f"{award.get_category_display()} {amount or ''}".strip())
    notify([idea.submitter], f"Congratulations! {idea.title} has been awarded: {award.get_category_display()}.", idea)
    return award


# --- conversation -----------------------------------------------------------
def post_message(idea, author, body):
    if not body.strip():
        raise WorkflowError("Write a message first.")
    if not sees_full_content(author, idea) or author.role in (Role.OBSERVER, Role.CONSULTANT):
        raise WorkflowError("You can't post on this idea.")
    m = Message.objects.create(idea=idea, author=author, body=body.strip())
    record("message.posted", target=idea.reference, actor=author)
    who = "an evaluator" if author.role == Role.EVALUATOR else str(author)
    recipients = [idea.submitter] + [a.evaluator for a in idea.active_assignments()] + users_with_role(Role.ADMIN)
    notify([u for u in recipients if u.pk != author.pk], f"New message on {idea.reference} from {who}.", idea)
    return m
