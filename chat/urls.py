from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.client, name="client"),
    path("new/", views.new_chat, name="new"),
    path("<int:pk>/poll/", views.poll, name="poll"),
    path("<int:pk>/send/", views.send, name="send"),
    path("<int:pk>/close/", views.close, name="close"),
    path("<int:pk>/rate/", views.rate, name="rate"),
    path("<int:pk>/accept/", views.accept, name="accept"),
    path("agent/", views.console, name="console"),
    path("agent/state/", views.console_state, name="state"),
    path("agent/presence/", views.presence, name="presence"),
    path("reports/", views.reports, name="reports"),
]
