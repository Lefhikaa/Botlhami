from django.urls import path

from . import views

app_name = "ideas"

urlpatterns = [
    path("mine/", views.my_ideas, name="mine"),
    path("new/", views.idea_edit, name="new"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/edit/", views.idea_edit, name="edit"),
    path("<int:pk>/documents/<int:doc_id>/", views.download_document, name="document"),
    path("<int:pk>/documents/<int:doc_id>/delete/", views.delete_document, name="delete_document"),
    path("<int:pk>/message/", views.post_message, name="message"),
    path("<int:pk>/screen/", views.screen, name="screen"),
    path("<int:pk>/remind/", views.remind, name="remind"),
    path("<int:pk>/add-evaluator/", views.add_evaluator, name="add_evaluator"),
    path("<int:pk>/evaluate/", views.evaluate, name="evaluate"),
    path("<int:pk>/recuse/", views.recuse, name="recuse"),
    path("<int:pk>/decide/", views.decide, name="decide"),
    path("<int:pk>/award/", views.award, name="award"),
    path("screening/", views.screening, name="screening"),
    path("queue/", views.queue, name="queue"),
    path("adjudication/", views.adjudication, name="adjudication"),
    path("pipeline/", views.pipeline, name="pipeline"),
    path("notifications/", views.notifications, name="notifications"),
]
