from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Role
from core.permissions import role_required
from core.throttle import hit

from . import services as svc
from .models import AgentPresence, Conversation

TOPICS = ["Submitting an idea", "Status of my submission", "Technical problem", "CEDA financing", "Something else"]


class StartForm(forms.Form):
    name = forms.CharField(label="Your name", max_length=100, required=False)
    email = forms.EmailField(label="Email address", required=False, help_text="So we can reply if you leave the chat.")
    topic = forms.ChoiceField(label="What is it about?", choices=[(t, t) for t in TOPICS])
    message = forms.CharField(label="Your message", widget=forms.Textarea(attrs={"rows": 3}), max_length=2000)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            del self.fields["name"], self.fields["email"]
        else:
            self.fields["name"].required = self.fields["email"].required = True


def _session_ids(request):
    return request.session.setdefault("chat_ids", [])


def _can_access(request, conv):
    if svc.is_agent(request.user):
        return True
    if request.user.is_authenticated and conv.customer_id == request.user.pk:
        return True
    return conv.pk in request.session.get("chat_ids", [])


def _get(request, pk):
    conv = get_object_or_404(Conversation, pk=pk)
    if not _can_access(request, conv):
        raise PermissionDenied
    return conv


# --- client ------------------------------------------------------------------
def client(request):
    """The chat page clients see. Works for signed-in users and guests."""
    if svc.is_agent(request.user):
        return redirect("chat:console")
    current = None
    ids = request.session.get("chat_ids", [])
    if request.user.is_authenticated:
        current = request.user.chats.exclude(status=Conversation.Status.CLOSED).first()
    elif ids:
        current = Conversation.objects.filter(pk__in=ids).exclude(status=Conversation.Status.CLOSED).first()
    state, notice = svc.availability()
    form = StartForm(request.POST or None, user=request.user)
    if request.method == "POST" and not current and form.is_valid():
        key = f"chat-start:{request.session.session_key or request.META.get('REMOTE_ADDR')}"
        if hit(key, 5, 3600):
            form.add_error(None, "You've started several chats recently. Please continue in your existing chat.")
        else:
            d = form.cleaned_data
            user = request.user if request.user.is_authenticated else None
            conv, state, notice = svc.start(user, d.get("name", ""), d.get("email", ""), d["topic"], d["message"])
            _session_ids(request).append(conv.pk)
            request.session.modified = True
            return redirect("chat:client")
    return render(request, "chat/client.html", {"conv": current, "form": form, "state": state, "notice": notice})


@require_GET
def poll(request, pk):
    conv = _get(request, pk)
    after = int(request.GET.get("after") or 0)
    msgs = list(conv.messages.filter(id__gt=after).select_related("sender", "conversation__customer"))
    agent_view = svc.is_agent(request.user)
    if agent_view:
        svc.heartbeat(request.user)
    if msgs:
        field = "agent_seen_id" if agent_view else "customer_seen_id"
        Conversation.objects.filter(pk=conv.pk).update(**{field: msgs[-1].pk})
    return JsonResponse({"status": conv.status, "rating": conv.rating, "messages": [m.as_dict() for m in msgs]})


@require_POST
def send(request, pk):
    conv = _get(request, pk)
    as_agent = svc.is_agent(request.user)
    if as_agent and conv.agent_id not in (None, request.user.pk):
        raise PermissionDenied
    if hit(f"chat-send:{request.session.session_key}:{pk}", 30, 60):
        return JsonResponse({"ok": False, "error": "You're sending messages too quickly."}, status=429)
    msg = svc.send(conv, request.user, request.POST.get("body", ""), as_agent)
    return JsonResponse({"ok": bool(msg)})


@require_POST
def close(request, pk):
    conv = _get(request, pk)
    svc.close(conv, request.user)
    return JsonResponse({"ok": True})


@require_POST
def rate(request, pk):
    conv = _get(request, pk)
    if svc.is_agent(request.user) or conv.status != Conversation.Status.CLOSED:
        raise PermissionDenied
    try:
        rating = int(request.POST.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    if 1 <= rating <= 5:
        conv.rating = rating
        conv.save(update_fields=["rating"])
    return JsonResponse({"ok": True})


@require_POST
def new_chat(request):
    """Client finished with a closed chat and wants a fresh form."""
    request.session["chat_ids"] = []
    return redirect("chat:client")


# --- agent console ---------------------------------------------------------
@role_required(Role.CONSULTANT, Role.ADMIN)
def console(request):
    presence, _ = AgentPresence.objects.get_or_create(agent=request.user)
    return render(request, "chat/console.html", {"presence": presence})


@role_required(Role.CONSULTANT, Role.ADMIN)
def console_state(request):
    svc.heartbeat(request.user)
    me = request.user
    queue = Conversation.objects.filter(status__in=[Conversation.Status.WAITING, Conversation.Status.OFFLINE], agent__isnull=True).order_by("created_at")
    mine = Conversation.objects.filter(agent=me, status=Conversation.Status.ACTIVE).order_by("accepted_at")
    now = timezone.now()

    def row(c):
        last = c.messages.order_by("-id").first()
        return {
            "id": c.pk, "name": c.display_name, "topic": c.topic, "status": c.status, "started_as": c.started_as,
            "waiting_min": int((now - c.created_at).total_seconds() // 60),
            "unread": c.messages.filter(id__gt=c.agent_seen_id, kind="customer").count(),
            "last": (last.body[:60] if last else ""),
        }

    state, _ = svc.availability()
    p = AgentPresence.objects.filter(agent=me).first()
    return JsonResponse({
        "available": bool(p and p.available), "service": state,
        "agents_online": svc.online_agents().count(),
        "queue": [row(c) for c in queue], "mine": [row(c) for c in mine],
    })


@require_POST
@role_required(Role.CONSULTANT, Role.ADMIN)
def presence(request):
    svc.set_presence(request.user, request.POST.get("available") == "1")
    return JsonResponse({"ok": True})


@require_POST
@role_required(Role.CONSULTANT, Role.ADMIN)
def accept(request, pk):
    conv = get_object_or_404(Conversation, pk=pk)
    return JsonResponse({"ok": svc.accept(conv, request.user)})


@role_required(Role.CONSULTANT, Role.ADMIN)
def reports(request):
    days = int(request.GET.get("days") or 30)
    days = days if days in (7, 30, 90) else 30
    data = svc.analytics(days)
    peak = max([n for _, n in data["by_hour"]] + [1])
    return render(request, "chat/reports.html", {"a": data, "peak": peak, "peak_day": max([n for _, n in data["by_day"]] + [1])})
