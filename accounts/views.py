from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.log import client_ip, record
from core.throttle import blocked, hit, reset

from .forms import CodeForm, EmailAuthenticationForm, EmailOnlyForm, ProfileForm, RegistrationForm
from .models import OneTimeCode
from .otp import check_code, send_code

User = get_user_model()
BACKEND = "django.contrib.auth.backends.ModelBackend"
PENDING_KEY = "pending_user_id"

LOGIN_LIMIT = 5          # failed password attempts per email+IP
LOGIN_WINDOW = 15 * 60   # seconds
RESEND_WINDOW = 60       # one code per minute


def register(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.set_password(form.cleaned_data["password1"])
        user.data_consent_at = timezone.now()
        user.save()
        record("account.registered", target=user.email, actor=user, request=request, detail="Self-registration")
        send_code(user, OneTimeCode.Purpose.VERIFY_EMAIL)
        request.session[PENDING_KEY] = user.pk
        messages.info(request, f"We sent a 6-digit code to {user.email}. Enter it below to verify your email.")
        return redirect("accounts:verify")
    return render(request, "accounts/register.html", {"form": form})


def _pending_user(request):
    pk = request.session.get(PENDING_KEY)
    return User.objects.filter(pk=pk).first() if pk else None


def verify_email(request):
    user = _pending_user(request)
    if not user:
        return redirect("accounts:login")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if check_code(user, OneTimeCode.Purpose.VERIFY_EMAIL, form.cleaned_data["code"]):
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            request.session.pop(PENDING_KEY, None)
            record("account.email_verified", target=user.email, actor=user, request=request)
            login(request, user, backend=BACKEND)
            messages.success(request, "Your email is verified. Welcome to Botlhami.")
            return redirect("core:dashboard")
        record("account.verify_failed", target=user.email, actor=user, request=request)
        form.add_error("code", "That code is wrong or has expired. Check the latest email, or send a new code.")
    return render(request, "accounts/verify.html", {"form": form, "email": user.email})


@require_POST
def resend_code(request):
    user = _pending_user(request)
    if not user:
        return redirect("accounts:login")
    if hit(f"resend:{user.pk}", 1, RESEND_WINDOW):
        messages.warning(request, "Please wait a minute before asking for another code.")
    else:
        send_code(user, OneTimeCode.Purpose.VERIFY_EMAIL)
        messages.info(request, f"A new code is on its way to {user.email}.")
    return redirect("accounts:verify")


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def _key(self):
        email = (self.request.POST.get("username") or "").strip().lower()
        return f"login:{email}:{client_ip(self.request)}"

    def post(self, request, *args, **kwargs):
        if blocked(self._key(), LOGIN_LIMIT):
            record("auth.locked_out", target=request.POST.get("username", "")[:120], request=request)
            form = self.get_form()
            form.is_bound = True
            form._errors = {"__all__": form.error_class(["Too many failed attempts. Wait 15 minutes, or reset your password."])}
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        hit(self._key(), LOGIN_LIMIT, LOGIN_WINDOW)
        return super().form_invalid(form)

    def form_valid(self, form):
        user = form.get_user()
        reset(self._key())
        if not user.email_verified:
            send_code(user, OneTimeCode.Purpose.VERIFY_EMAIL)
            self.request.session[PENDING_KEY] = user.pk
            messages.info(self.request, "Please verify your email first. We've sent you a new code.")
            return redirect("accounts:verify")
        return super().form_valid(form)


def code_request(request):
    """Passwordless sign-in, step 1: email a one-time code."""
    form = EmailOnlyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user and not hit(f"signin-code:{user.pk}", 1, RESEND_WINDOW):
            send_code(user, OneTimeCode.Purpose.SIGN_IN)
        request.session["code_email"] = email
        # Same message whether or not the account exists, so emails can't be probed.
        messages.info(request, f"If {email} has an account, a sign-in code is on its way.")
        return redirect("accounts:code_verify")
    return render(request, "accounts/code_request.html", {"form": form})


def code_verify(request):
    """Passwordless sign-in, step 2: check the code."""
    email = request.session.get("code_email")
    if not email:
        return redirect("accounts:code_request")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user and check_code(user, OneTimeCode.Purpose.SIGN_IN, form.cleaned_data["code"]):
            request.session.pop("code_email", None)
            if not user.email_verified:  # receiving the code proves the email works
                user.email_verified = True
                user.save(update_fields=["email_verified"])
            login(request, user, backend=BACKEND)
            return redirect("core:dashboard")
        record("auth.code_failed", target=email, request=request)
        form.add_error("code", "That code is wrong or has expired.")
    return render(request, "accounts/code_verify.html", {"form": form, "email": email})


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        response = super().form_valid(form)
        record("auth.password_changed", target=self.request.user.email)
        messages.success(self.request, "Your password has been changed.")
        return response


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "emails/password_reset.txt"
    html_email_template_name = "emails/password_reset.html"
    subject_template_name = "emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        record("auth.password_reset_requested", target=form.cleaned_data["email"])
        return super().form_valid(form)


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        response = super().form_valid(form)
        record("auth.password_reset_completed", target=self.user.email, actor=self.user)
        return response


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        record("account.profile_updated", target=request.user.email)
        messages.success(request, "Your details are saved.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})
