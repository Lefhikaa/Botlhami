"""The signed-in sidebar: menu sections per role, with live counts.

Each count is one small query, and only the counts a role can see are run.
"""
from django.urls import NoReverseMatch, reverse

from accounts.models import Role


def _item(label, url_name, icon, count=None, match=None, args=None):
    try:
        url = reverse(url_name, args=args or [])
    except NoReverseMatch:
        return None
    return {"label": label, "url": url, "icon": icon, "count": count or None, "match": match or url}


def _counts(user):
    from accounts.models import User
    from chat.models import Conversation
    from ideas.models import Idea, Status
    from support.models import Ticket

    role, c = user.role, {}
    if role == Role.EVALUATOR:
        n = 0
        for a in user.assignments.filter(recused=False, idea__status=Status.IN_REVIEW).select_related("idea"):
            if a.round == a.idea.round and not a.idea.evaluations.filter(round=a.round, evaluator=user).exists():
                n += 1
        c["queue"] = n
    if role == Role.ADMIN:
        c["screening"] = Idea.objects.filter(status=Status.SUBMITTED).count()
    if role in (Role.ADMIN, Role.ADJUDICATOR):
        c["adjudication"] = Idea.objects.filter(status__in=[Status.ADJUDICATION, Status.APPROVED]).count()
    if role in (Role.ADMIN, Role.CONSULTANT):
        c["chat"] = Conversation.objects.filter(status=Conversation.Status.WAITING).count()
        c["support"] = Ticket.objects.filter(status__in=Ticket.ACTIVE).count()
        c["ids"] = User.objects.filter(id_status=User.IdStatus.PENDING).count()
    if role == Role.SUBMITTER:
        c["tickets"] = user.tickets.filter(status=Ticket.Status.WAITING).count()
    return c


def menu(user):
    role = user.role
    c = _counts(user)
    main, service, manage = [], [], []

    if role == Role.SUBMITTER:
        main += [_item("My ideas", "ideas:mine", "ideas", match="/ideas/"),
                 _item("Submit an idea", "ideas:new", "plus")]
        service += [_item("Chat with CEDA", "chat:client", "chat"),
                    _item("Help centre", "support:help", "help", match="/help/"),
                    _item("Forms and documents", "support:documents", "file"),
                    _item("My support tickets", "support:tickets", "lifebuoy", c.get("tickets"), match="/support/")]
    if role == Role.EVALUATOR:
        main += [_item("Evaluation queue", "ideas:queue", "clipboard", c.get("queue"), match="/ideas/")]
        service += [_item("Help centre", "support:help", "help", match="/help/")]
    if role == Role.ADMIN:
        main += [_item("Screening", "ideas:screening", "filter", c.get("screening"))]
    if role in (Role.ADMIN, Role.ADJUDICATOR):
        main += [_item("Adjudication", "ideas:adjudication", "scale", c.get("adjudication")),
                 _item("Score comparison", "ideas:scores", "radar")]
    if role in (Role.ADMIN, Role.ADJUDICATOR, Role.OBSERVER):
        main += [_item("Pipeline", "ideas:pipeline", "columns"),
                 _item("Reports", "reports:dashboard", "chart", match="/reports/")]
    if role in (Role.ADMIN, Role.ADJUDICATOR, Role.CONSULTANT):
        label = "My awards" if role == Role.CONSULTANT else "After the award"
        main += [_item(label, "ideas:implementation", "flag")]
    if role in (Role.ADMIN, Role.CONSULTANT):
        service += [_item("Live chat", "chat:console", "chat", c.get("chat"), match="/chat/agent/"),
                    _item("Chat reports", "chat:reports", "chart", match="/chat/reports/"),
                    _item("Support desk", "support:queue", "lifebuoy", c.get("support"), match="/support/"),
                    _item("ID checks", "accounts:id_queue", "idcard", c.get("ids"), match="/accounts/identity/checks/")]
    if role == Role.ADMIN:
        manage += [_item("Content", "support:manage_home", "file", match="/manage/"),
                   _item("Admin site", "admin:index", "settings", match="/admin/")]

    sections = [("Main menu", main), ("Service", service), ("Manage", manage)]
    return [(title, [i for i in items if i]) for title, items in sections if any(items)]


def mark_active(sections, path):
    """Highlight the single best match: the longest matching prefix."""
    best, best_len = None, -1
    for _, items in sections:
        for i in items:
            if path == i["url"] or path.startswith(i["match"]):
                n = len(i["url"]) if path == i["url"] else len(i["match"])
                if n > best_len:
                    best, best_len = i, n
    if best:
        best["active"] = True
    return sections
