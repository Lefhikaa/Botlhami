import os

from django import forms

from .models import FAQ, RegulatorContact, Resource, ServiceLevel, Ticket, TicketReply


class ResourceForm(forms.ModelForm):
    upload = forms.FileField(
        label="File", required=False,
        help_text="PDF, Word, Excel, PowerPoint or text. Up to 10 MB. Leave empty to keep the current file.",
    )

    class Meta:
        model = Resource
        fields = ["title", "kind", "description", "mandatory", "published", "order"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_upload(self):
        f = self.cleaned_data.get("upload")
        if not f:
            if not (self.instance and self.instance.file):
                raise forms.ValidationError("Choose a file to upload.")
            return f
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in Resource.ALLOWED:
            raise forms.ValidationError(f"{ext or 'This file type'} isn't allowed. Use PDF, Word, Excel, PowerPoint or text.")
        if f.size > Resource.MAX_BYTES:
            raise forms.ValidationError("Files must be 10 MB or smaller.")
        return f


class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ["category", "question", "answer", "published", "order"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 5})}


class RegulatorForm(forms.ModelForm):
    class Meta:
        model = RegulatorContact
        fields = ["name", "acronym", "helps_with", "phone", "email", "website", "published", "order"]


class ServiceLevelForm(forms.ModelForm):
    class Meta:
        model = ServiceLevel
        fields = ["label", "description", "response_hours", "resolution_hours"]

    def clean(self):
        data = super().clean()
        r, s = data.get("response_hours"), data.get("resolution_hours")
        if r and s and s < r:
            raise forms.ValidationError("The resolution time can't be shorter than the response time.")
        return data


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["subject", "area", "level", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6, "placeholder": "What were you trying to do, what happened, and any error message you saw."}),
            "level": forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["level"].queryset = ServiceLevel.objects.all()
        self.fields["level"].empty_label = None
        self.fields["level"].label_from_instance = lambda lvl: f"{lvl.label}: {lvl.description}"


class ReplyForm(forms.ModelForm):
    class Meta:
        model = TicketReply
        fields = ["body"]
        labels = {"body": "Reply"}
        widgets = {"body": forms.Textarea(attrs={"rows": 3})}


class StaffReplyForm(forms.Form):
    body = forms.CharField(label="Reply", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    internal = forms.BooleanField(label="Internal note (the user won't see it)", required=False)
    status = forms.ChoiceField(choices=Ticket.Status.choices)
    assigned_to = forms.ModelChoiceField(queryset=None, required=False, empty_label="Unassigned", label="Assigned to")

    def __init__(self, *args, staff=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = staff
