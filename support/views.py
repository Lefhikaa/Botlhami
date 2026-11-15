from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Role
from audit.log import record
from core.permissions import role_required
from ideas.services import notify

from .forms import FAQForm, RegulatorForm, ReplyForm, ResourceForm, ServiceLevelForm, StaffReplyForm, TicketForm
from .models import FAQ, RegulatorContact, Resource, ServiceLevel, Ticket

User = get_user_model()
SUPPORT_ROLES = (Role.ADMIN, Role.CONSULTANT)


def is_support(user):
    return user.is_authenticated and user.has_role(*SUPPORT_ROLES)


# --- public help centre ------------------------------------------------------
def help_centre(request):
    q = request.GET.get("q", "").strip()
    faqs = FAQ.objects.filter(published=True)
    if q:
        faqs = faqs.filter(Q(question__icontains=q) | Q(answer__icontains=q))
    groups = []
    for value, label in FAQ.Category.choices:
        items = [f for f in faqs if f.category == value]
        if items:
            groups.append((label, items))
    return render(request, "support/help.html", {
        "groups": groups, "q": q, "found": len(faqs),
        "regulators": RegulatorContact.objects.filter(published=True),
    })


def documents(request):
    groups = []
    published = Resource.objects.filter(published=True).exclude(file="")
    for value, label in Resource.Kind.choices:
        items = [r for r in published if r.kind == value]
        if items:
            groups.append((label, items))
    return render(request, "support/documents.html", {"groups": groups})


def download_resource(request, pk):
    res = get_object_or_404(Resource, pk=pk)
    if not res.file or (not res.published and not (request.user.is_authenticated and request.user.has_role(Role.ADMIN))):
        raise Http404
    try:
        handle = res.file.open("rb")
    except FileNotFoundError:
        raise Http404
    return FileResponse(handle, as_attachment=True, filename=res.original_name or res.file.name)


def service_levels(request):
    return render(request, "support/sla.html", {"levels": ServiceLevel.objects.all()})


# --- tickets -----------------------------------------------------------------
@login_required
def my_tickets(request):
    return render(request, "support/tickets.html", {"tickets": request.user.tickets.select_related("level")})


@login_required
def new_ticket(request):
    form = TicketForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        t = form.save(commit=False)
        t.raised_by = request.user
        t.save()
        record("support.ticket_raised", target=t.reference, detail=f"{t.level.label}: {t.subject}")
        staff = User.objects.filter(role__in=SUPPORT_ROLES, is_active=True)
        notify(staff, f"New {t.level.label.lower()} support ticket {t.reference}: {t.subject}")
        messages.success(request, f"Thanks. Your ticket reference is {t.reference}. We'll respond within {t.level.response_label}.")
        return redirect("support:ticket", pk=t.pk)
    return render(request, "support/ticket_form.html", {"form": form, "levels": ServiceLevel.objects.all()})


@login_required
def ticket_detail(request, pk):
    t = get_object_or_404(Ticket.objects.select_related("level", "raised_by", "assigned_to"), pk=pk)
    staff_view = is_support(request.user)
    if not staff_view and t.raised_by_id != request.user.pk:
        record("access.denied", target=t.reference, detail="Tried to open a support ticket")
        raise PermissionDenied
    staff = User.objects.filter(role__in=SUPPORT_ROLES, is_active=True).order_by("first_name")
    if staff_view:
        form = StaffReplyForm(request.POST or None, staff=staff, initial={"status": t.status, "assigned_to": t.assigned_to})
    else:
        form = ReplyForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        now = timezone.now()
        if staff_view:
            body, internal = form.cleaned_data["body"].strip(), form.cleaned_data["internal"]
            new_status, assignee = form.cleaned_data["status"], form.cleaned_data["assigned_to"]
            changes = []
            if body:
                t.replies.create(author=request.user, body=body, internal=internal)
                if not internal and not t.first_response_at:
                    t.first_response_at = now
            if new_status != t.status:
                changes.append(f"status {t.get_status_display()} → {Ticket.Status(new_status).label}")
                t.status = new_status
                if new_status in (Ticket.Status.RESOLVED, Ticket.Status.CLOSED) and not t.resolved_at:
                    t.resolved_at = now
                elif new_status in Ticket.ACTIVE:
                    t.resolved_at = None
                if new_status != Ticket.Status.OPEN and not t.first_response_at:
                    t.first_response_at = now
            if assignee != t.assigned_to:
                changes.append(f"assigned to {assignee or 'nobody'}")
                t.assigned_to = assignee
            if not body and not changes:
                messages.info(request, "Nothing to save.")
                return redirect("support:ticket", pk=t.pk)
            if t.status == Ticket.Status.OPEN and body and not internal:
                t.status = Ticket.Status.IN_PROGRESS
            t.save()
            record("support.ticket_updated", target=t.reference, detail="; ".join(changes) or ("internal note" if internal else "reply"))
            if (body and not internal) or new_status in (Ticket.Status.RESOLVED, Ticket.Status.WAITING):
                notify([t.raised_by], f"Update on your support ticket {t.reference}: {t.get_status_display()}")
        else:
            if not t.is_active and t.status == Ticket.Status.CLOSED:
                messages.error(request, "This ticket is closed. Please raise a new one.")
                return redirect("support:ticket", pk=t.pk)
            t.replies.create(author=request.user, body=form.cleaned_data["body"])
            if t.status in (Ticket.Status.WAITING, Ticket.Status.RESOLVED):
                t.status = Ticket.Status.IN_PROGRESS
                t.resolved_at = None
                t.save()
            record("support.ticket_reply", target=t.reference)
            notify([t.assigned_to] if t.assigned_to else User.objects.filter(role__in=SUPPORT_ROLES, is_active=True),
                   f"{request.user} replied on support ticket {t.reference}")
        messages.success(request, "Saved.")
        return redirect("support:ticket", pk=t.pk)

    replies = t.replies.select_related("author")
    if not staff_view:
        replies = replies.filter(internal=False)
    return render(request, "support/ticket_detail.html", {"t": t, "form": form, "replies": replies, "staff_view": staff_view})


@role_required(*SUPPORT_ROLES)
def queue(request):
    show = request.GET.get("show", "active")
    tickets = Ticket.objects.select_related("level", "raised_by", "assigned_to")
    if show == "active":
        tickets = tickets.filter(status__in=Ticket.ACTIVE)
    elif show == "mine":
        tickets = tickets.filter(status__in=Ticket.ACTIVE, assigned_to=request.user)
    tickets = sorted(tickets, key=lambda t: (not t.is_active, t.next_due or t.created_at))
    active = Ticket.objects.filter(status__in=Ticket.ACTIVE)
    return render(request, "support/queue.html", {
        "tickets": tickets, "show": show,
        "counts": {"active": active.count(), "overdue": sum(1 for t in active if t.overdue)},
    })


# --- administrator content management ---------------------------------------
MANAGED = {
    "documents": {"model": Resource, "form": ResourceForm, "title": "Application forms and documents", "noun": "document"},
    "faqs": {"model": FAQ, "form": FAQForm, "title": "FAQs", "noun": "FAQ"},
    "regulators": {"model": RegulatorContact, "form": RegulatorForm, "title": "Regulatory authorities", "noun": "contact"},
    "service-levels": {"model": ServiceLevel, "form": ServiceLevelForm, "title": "Service levels", "noun": "service level", "fixed": True},
}


def _section(kind):
    conf = MANAGED.get(kind)
    if not conf:
        raise Http404
    return conf


@role_required(Role.ADMIN)
def manage(request, kind="documents"):
    conf = _section(kind)
    return render(request, "support/manage_list.html", {
        "kind": kind, "conf": conf, "sections": MANAGED, "items": conf["model"].objects.all(),
    })


@role_required(Role.ADMIN)
def manage_edit(request, kind, pk=None):
    conf = _section(kind)
    obj = get_object_or_404(conf["model"], pk=pk) if pk else None
    if obj is None and conf.get("fixed"):
        raise Http404
    form = conf["form"](request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if isinstance(item, Resource):
            upload = form.cleaned_data.get("upload")
            if upload:
                old = item.file.name if item.file else None
                item.file = upload
                item.original_name = upload.name[:200]
                item.size = upload.size
            else:
                old = None
            item.updated_by = request.user
            item.save()
            if old and old != item.file.name:
                item.file.storage.delete(old)
        else:
            item.save()
        record(f"content.{'updated' if obj else 'created'}", target=f"{conf['noun']}: {item}"[:120])
        messages.success(request, f"{conf['noun'].capitalize()} saved.")
        return redirect("support:manage", kind=kind)
    return render(request, "support/manage_form.html", {"kind": kind, "conf": conf, "form": form, "obj": obj, "sections": MANAGED})


@require_POST
@role_required(Role.ADMIN)
def manage_delete(request, kind, pk):
    conf = _section(kind)
    if conf.get("fixed"):
        raise PermissionDenied
    obj = get_object_or_404(conf["model"], pk=pk)
    label = str(obj)
    if isinstance(obj, Resource) and obj.file:
        obj.file.storage.delete(obj.file.name)
    obj.delete()
    record("content.deleted", target=f"{conf['noun']}: {label}"[:120])
    messages.success(request, f"Deleted “{label}”.")
    return redirect("support:manage", kind=kind)
