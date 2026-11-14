from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .log import record


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record("auth.login", target=user.email, actor=user, request=request)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user:
        record("auth.logout", target=user.email, actor=user, request=request)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    # Never store the attempted password: only the email that was tried.
    record("auth.login_failed", target=(credentials or {}).get("username", "")[:120], request=request)
