"""One function every part of Botlhami calls to write to the audit trail."""
from .middleware import get_current_request
from .models import AuditEvent


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    # Azure's front end can append a port ("1.2.3.4:5678" or "[2001:db8::1]:5678").
    if ip and ip.count(":") == 1 and "." in ip:
        ip = ip.split(":")[0]
    elif ip and ip.startswith("[") and "]" in ip:
        ip = ip[1:ip.index("]")]
    return ip or None


def record(action, target="", detail="", actor=None, request=None):
    request = request or get_current_request()
    if actor is None and request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        actor = request.user
    return AuditEvent.objects.create(
        actor=actor,
        actor_label=(str(actor) if actor else ""),
        role=getattr(actor, "role", "") if actor else "",
        action=action,
        target=str(target)[:120],
        detail=str(detail),
        ip_address=client_ip(request) if request else None,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
    )
