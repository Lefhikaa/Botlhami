from django.conf import settings


def site(request):
    ctx = {"SITE_NAME": settings.SITE_NAME, "SUPPORT_EMAIL": settings.SUPPORT_EMAIL}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_count"] = user.notifications.filter(read_at__isnull=True).count()
        from .nav import mark_active, menu
        ctx["nav_sections"] = mark_active(menu(user), request.path)
    return ctx
