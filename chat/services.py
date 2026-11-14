"""Chat availability rules and analytics."""
from collections import Counter
from datetime import timedelta

from django.core.mail import send_mail
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import Role
from audit.log import record

from .models import AgentPresence, ChatMessage, ChatSettings, Conversation, PublicHoliday

AGENT_ROLES = (Role.CONSULTANT, Role.ADMIN)


def is_agent(user):
    return user.is_authenticated and user.has_role(*AGENT_ROLES)


def is_working_time(now=None):
    now = timezone.localtime(now or timezone.now())
    cs = ChatSettings.get()
    if now.weekday() >= 5 or PublicHoliday.objects.filter(date=now.date()).exists():
        return False
    return cs.opens_at <= now.time() < cs.closes_at


def online_agents():
    cutoff = timezone.now() - AgentPresence.STALE_AFTER
    return AgentPresence.objects.filter(available=True, last_seen__gte=cutoff).select_related("agent")


def availability(now=None):
    """Return (state, message): state is 'open', 'busy', 'closed' or 'offline'."""
    cs = ChatSettings.get()
    if not is_working_time(now):
        return "closed", cs.closed_message
    agents = list(online_agents())
    if not agents:
        return "offline", cs.offline_message
    loads = Counter(
        Conversation.objects.filter(status=Conversation.Status.ACTIVE, agent__in=[p.agent for p in agents]).values_list("agent_id", flat=True)
    )
    if all(loads[p.agent_id] >= cs.max_chats_per_agent for p in agents):
        return "busy", cs.busy_message
    return "open", ""


def start(customer=None, guest_name="", guest_email="", topic="", first_message=""):
    state, notice = availability()
    status = Conversation.Status.WAITING if state in ("open", "busy") else Conversation.Status.OFFLINE
    conv = Conversation.objects.create(customer=customer, guest_name=guest_name, guest_email=guest_email, topic=topic, status=status, started_as=state)
    if first_message.strip():
        ChatMessage.objects.create(conversation=conv, kind=ChatMessage.Kind.CUSTOMER, sender=customer, body=first_message.strip())
    if state == "open":
        ChatMessage.objects.create(conversation=conv, kind=ChatMessage.Kind.SYSTEM, body="Thanks. A CEDA consultant will join you shortly.")
    else:
        ChatMessage.objects.create(conversation=conv, kind=ChatMessage.Kind.SYSTEM, body=notice)
    record("chat.started", target=f"chat:{conv.pk}", actor=customer, detail=f"{state}; topic: {topic}")
    return conv, state, notice


def accept(conv, agent):
    if conv.status not in (Conversation.Status.WAITING, Conversation.Status.OFFLINE) or conv.agent_id:
        return False
    was_offline = conv.status == Conversation.Status.OFFLINE
    conv.agent = agent
    conv.accepted_at = timezone.now()
    conv.status = Conversation.Status.ACTIVE
    conv.save(update_fields=["agent", "accepted_at", "status"])
    ChatMessage.objects.create(conversation=conv, kind=ChatMessage.Kind.SYSTEM, body=f"{agent.first_name or agent} from CEDA has joined the chat.")
    record("chat.accepted", target=f"chat:{conv.pk}", actor=agent, detail="offline message picked up" if was_offline else "")
    return True


def send(conv, sender, body, as_agent):
    body = body.strip()[:2000]
    if not body or conv.status == Conversation.Status.CLOSED:
        return None
    msg = ChatMessage.objects.create(
        conversation=conv, kind=ChatMessage.Kind.AGENT if as_agent else ChatMessage.Kind.CUSTOMER,
        sender=sender if sender and sender.is_authenticated else None, body=body,
    )
    # Replies to messages left out of hours also go by email, since the client may not be online.
    if as_agent and conv.contact_email and conv.started_as in ("closed", "offline"):
        send_mail("Reply from CEDA via Botlhami", f"{body}\n\nReply by opening your chat in Botlhami.", None, [conv.contact_email], fail_silently=True)
    return msg


def close(conv, by):
    if conv.status == Conversation.Status.CLOSED:
        return
    conv.status = Conversation.Status.CLOSED
    conv.closed_at = timezone.now()
    conv.save(update_fields=["status", "closed_at"])
    ChatMessage.objects.create(conversation=conv, kind=ChatMessage.Kind.SYSTEM, body="This chat has ended. Thank you for contacting CEDA.")
    record("chat.closed", target=f"chat:{conv.pk}", actor=by if by and by.is_authenticated else None)


def set_presence(agent, available):
    p, _ = AgentPresence.objects.get_or_create(agent=agent)
    p.available = available
    p.last_seen = timezone.now()
    p.save()
    record("chat.agent_available" if available else "chat.agent_away", target=str(agent), actor=agent)


def heartbeat(agent):
    AgentPresence.objects.filter(agent=agent).update(last_seen=timezone.now())


# --- analytics ---------------------------------------------------------------
def analytics(days=30):
    since = timezone.now() - timedelta(days=days)
    qs = Conversation.objects.filter(created_at__gte=since)
    total = qs.count()
    answered = [c for c in qs.filter(accepted_at__isnull=False)]
    waits = [c.wait_seconds for c in answered if c.wait_seconds is not None]
    durations = [c.duration_seconds for c in answered if c.duration_seconds is not None]
    rated = [c.rating for c in qs.filter(rating__isnull=False)]
    by_hour = Counter(timezone.localtime(c.created_at).hour for c in qs.only("created_at"))
    by_day = Counter(timezone.localtime(c.created_at).strftime("%a") for c in qs.only("created_at"))
    per_agent = (
        qs.filter(agent__isnull=False).values("agent__first_name", "agent__last_name")
        .annotate(chats=Count("id"), closed=Count("id", filter=Q(status=Conversation.Status.CLOSED))).order_by("-chats")
    )
    avg = lambda xs: round(sum(xs) / len(xs)) if xs else None  # noqa: E731
    return {
        "days": days,
        "total": total,
        "answered": len(answered),
        "offline": qs.filter(started_as__in=["closed", "offline"]).count(),
        "busy": qs.filter(started_as="busy").count(),
        "unanswered": qs.filter(accepted_at__isnull=True).count(),
        "avg_wait": avg(waits),
        "avg_duration": avg(durations),
        "avg_rating": round(sum(rated) / len(rated), 1) if rated else None,
        "ratings": len(rated),
        "by_hour": [(f"{h:02d}:00", by_hour.get(h, 0)) for h in range(7, 19)],
        "by_day": [(d, by_day.get(d, 0)) for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]],
        "per_agent": list(per_agent),
        "topics": Counter(qs.exclude(topic="").values_list("topic", flat=True)).most_common(6),
    }
