from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

import os

from .models import User, omang_hash, omang_problem

PHONE_HELP = "Botswana mobile number, e.g. +267 71 234 567"
ID_TYPES = {".pdf", ".jpg", ".jpeg", ".png"}
ID_MAX = 5 * 1024 * 1024


def clean_omang_number(value, user=None):
    value = (value or "").strip()
    problem = omang_problem(value)
    if problem:
        raise forms.ValidationError(problem)
    taken = User.objects.filter(omang_hash=omang_hash(value))
    if user is not None and user.pk:
        taken = taken.exclude(pk=user.pk)
    if taken.exists():
        raise forms.ValidationError("This Omang number is already registered. Each citizen can have one account: "
                                    "sign in, or contact CEDA if you think this is a mistake.")
    return "".join(ch for ch in value if ch.isdigit())


def clean_id_copy(f):
    if not f:
        return f
    if os.path.splitext(f.name)[1].lower() not in ID_TYPES:
        raise forms.ValidationError("Upload a photo or scan of your Omang as PDF, JPG or PNG.")
    if f.size > ID_MAX:
        raise forms.ValidationError("The file must be 5 MB or smaller.")
    return f


OMANG_HELP = "Nine digits, as on your Omang card. We only ever show the last 4 digits."


class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="At least 10 characters. Avoid common words and all-number passwords.",
    )
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    omang = forms.CharField(label="Omang number", max_length=11, help_text=OMANG_HELP,
                            widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}))
    id_copy = forms.FileField(label="Copy of your Omang (optional now)", required=False,
                              help_text="A photo or scan of the front, as PDF, JPG or PNG up to 5 MB. "
                                        "You'll need it before you submit an idea; you can add it later in your profile.")
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

    def clean_omang(self):
        return clean_omang_number(self.cleaned_data.get("omang"))

    def clean_id_copy(self):
        return clean_id_copy(self.cleaned_data.get("id_copy"))

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
        fields = ["first_name", "last_name", "phone", "organisation", "email_alerts"]
        help_texts = {"phone": PHONE_HELP}

    def clean_phone(self):
        return RegistrationForm.clean_phone(self)


class IdentityForm(forms.Form):
    """Add or correct an Omang number and upload the card for CEDA to check."""
    omang = forms.CharField(label="Omang number", max_length=11, required=False, help_text=OMANG_HELP,
                            widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}))
    id_copy = forms.FileField(label="Copy of your Omang", required=False,
                              help_text="A photo or scan of the front, as PDF, JPG or PNG up to 5 MB.")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_omang(self):
        value = self.cleaned_data.get("omang", "").strip()
        if not value:
            if not self.user.omang_hash:
                raise forms.ValidationError("Enter your Omang number.")
            return ""
        return clean_omang_number(value, self.user)

    def clean_id_copy(self):
        f = clean_id_copy(self.cleaned_data.get("id_copy"))
        if not f and not self.user.id_document:
            raise forms.ValidationError("Upload a copy of your Omang.")
        return f


class IdCheckForm(forms.Form):
    decision = forms.ChoiceField(choices=[("verified", "Verified: the card matches"), ("rejected", "Not accepted")])
    note = forms.CharField(label="Note to the applicant", max_length=255, required=False,
                           help_text="Required if not accepted, e.g. the photo is unclear or the name doesn't match.")

    def clean(self):
        data = super().clean()
        if data.get("decision") == "rejected" and not data.get("note", "").strip():
            self.add_error("note", "Tell the applicant why, so they can fix it.")
        return data
