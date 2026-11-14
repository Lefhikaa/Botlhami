from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from audit.log import record


def role_required(*roles):
    """Allow only signed-in users holding one of the given roles. Denials are audited."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not request.user.has_role(*roles):
                record("access.denied", target=request.path, detail=f"Needs one of: {', '.join(roles)}")
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
