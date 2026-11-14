from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User

PHONE_HELP = "Botswana mobile number, e.g. +267 71 234 567"


class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="At least 10 characters. Avoid common words and all-number passwords.",
    )
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    consent = forms.BooleanField(
        label=(
            "I consent to Botlhami processing my personal data to manage my account and evaluate my "
            "submissions, in line with Botswana's Data Protection Act, 2024."
        )
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "organisation"]
        labels = {"organisation": "Company or organisation (optional)"}
        help_texts = {"phone": PHONE_HELP}
        widgets = {"email": forms.EmailInput(attrs={"autocomplete": "email"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("first_name", "last_name", "email", "phone"):
            self.fields[name].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Sign in or reset your password.")
        return email

    def clean_phone(self):
        digits = "".join(ch for ch in self.cleaned_data["phone"] if ch.isdigit() or ch == "+")
        bare = digits.removeprefix("+267").removeprefix("267")
        if not (len(bare) == 8 and bare.startswith("7")):
            raise forms.ValidationError("Enter a valid Botswana mobile number (8 digits starting with 7).")
        return "+267" + bare

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        if p1:
            probe = User(email=cleaned.get("email", ""), first_name=cleaned.get("first_name", ""), last_name=cleaned.get("last_name", ""))
            try:
                password_validation.validate_password(p1, probe)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return cleaned


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))
    error_messages = {
        "invalid_login": "That email and password don't match an account. Check them and try again.",
        "inactive": "This account has been deactivated. Contact the Innovation Office.",
    }


class CodeForm(forms.Form):
    code = forms.CharField(
        label="6-digit code", max_length=6, min_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "pattern": "[0-9]{6}", "autofocus": True}),
    )


class EmailOnlyForm(forms.Form):
    email = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "organisation"]
        help_texts = {"phone": PHONE_HELP}

    def clean_phone(self):
        return RegistrationForm.clean_phone(self)
