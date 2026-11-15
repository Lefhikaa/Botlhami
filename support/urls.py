from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("help/", views.help_centre, name="help"),
    path("help/documents/", views.documents, name="documents"),
    path("help/documents/<int:pk>/", views.download_resource, name="download"),
    path("help/service-levels/", views.service_levels, name="sla"),
    path("support/", views.my_tickets, name="tickets"),
    path("support/new/", views.new_ticket, name="new"),
    path("support/queue/", views.queue, name="queue"),
    path("support/<int:pk>/", views.ticket_detail, name="ticket"),
    path("manage/", views.manage, name="manage_home"),
    path("manage/<slug:kind>/", views.manage, name="manage"),
    path("manage/<slug:kind>/new/", views.manage_edit, name="manage_new"),
    path("manage/<slug:kind>/<int:pk>/", views.manage_edit, name="manage_edit"),
    path("manage/<slug:kind>/<int:pk>/delete/", views.manage_delete, name="manage_delete"),
]
