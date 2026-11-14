from django.db import connection
from django.http import JsonResponse


class HealthCheckMiddleware:
    """Answer /health/ before host validation and HTTPS redirects.

    Azure's internal health probe calls the app by its private IP over plain HTTP,
    which Django would otherwise reject. The check still proves the database is reachable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT 1")
                return JsonResponse({"status": "ok"})
            except Exception:
                return JsonResponse({"status": "database unavailable"}, status=503)
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Headers Django doesn't set by default: CSP and permissions policy."""

    CSP = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self' wss: ws:; font-src 'self' data:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response
