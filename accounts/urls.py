from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("verify/", views.verify_email, name="verify"),
    path("verify/resend/", views.resend_code, name="resend"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("login/code/", views.code_request, name="code_request"),
    path("login/code/verify/", views.code_verify, name="code_verify"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("identity/", views.identity, name="identity"),
    path("identity/checks/", views.id_queue, name="id_queue"),
    path("identity/checks/<int:pk>/", views.id_check, name="id_check"),
    path("identity/checks/<int:pk>/document/", views.id_document, name="id_document"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password_change"),
    path("password/reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password/reset/sent/", auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password/reset/complete/", auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
]
