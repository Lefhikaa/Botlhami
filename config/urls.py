from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Botlhami administration"
admin.site.site_title = "Botlhami admin"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("ideas/", include("ideas.urls")),
    path("chat/", include("chat.urls")),
    path("reports/", include("reports.urls")),
    path("", include("support.urls")),
    path("", include("core.urls")),
]

handler403 = "core.views.denied"
