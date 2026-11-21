import os

from django import forms

from .models import SDGS, Award, Evaluation, IdeaDocument, Idea


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": ",".join(sorted(IdeaDocument.ALLOWED))}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        cleaned = [super(MultipleFileField, self).clean(f, initial) for f in files]
        for f in cleaned:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in IdeaDocument.ALLOWED:
                raise forms.ValidationError(f"{f.name}: this file type isn't allowed.")
            if f.size > IdeaDocument.MAX_BYTES:
                raise forms.ValidationError(f"{f.name}: files must be 10 MB or smaller.")
        return cleaned


class IdeaForm(forms.ModelForm):
    """Drafts can be saved with only a title; completeness is checked on submit."""

    sdgs = forms.TypedMultipleChoiceField(
        label="Sustainable Development Goals it supports", choices=[(k, f"SDG {k}: {v}") for k, v in SDGS.items()],
        coerce=int, widget=forms.CheckboxSelectMultiple, required=False,
    )
    documents = MultipleFileField(
        label="Supporting documents", required=False,
        help_text="PDF, Word, Excel, PowerPoint or images, up to 10 MB each.",
    )

    class Meta:
        model = Idea
        fields = [
            "title", "sector", "maturity", "location", "problem", "solution",
            "beneficiaries", "impact", "jobs", "budget", "sdgs", "team",
            "capacity_skills", "capacity_resources", "capacity_partners", "capacity_gaps", "capacity_governance", "ip_declared",
        ]
        labels = {
            "title": "Idea title", "problem": "What problem does it solve?", "solution": "Your solution",
            "ip_declared": "I confirm this idea is our original work, or we have the right to submit it. "
                           "Its content will be shared only with assigned evaluators, adjudicators and the Innovation Office.",
        }
        help_texts = {
            "title": "Up to 120 characters.",
            "problem": "At least 50 characters. Who has the problem, and how big is it?",
            "solution": "At least 50 characters. How does it work, and what makes it new?",
            "team": "One person per line, with their role.",
            "capacity_skills": "The skills, qualifications and track record that equip the team to deliver this. "
                               "Describe skills rather than naming people: evaluators review ideas without names.",
            "capacity_resources": "What you already have: premises, equipment, a working prototype, customers, or money you'll put in yourself.",
            "capacity_partners": "Optional. Suppliers, institutions, mentors or buyers you're working with, and whether it's agreed or still a plan.",
            "capacity_gaps": "Optional. What's still missing, such as a skill, licence or piece of equipment, and how you'll get it.",
            "capacity_governance": "Optional. Who makes decisions, how money is managed and records kept, and any board, advisers or mentors.",
        }
        widgets = {
            "problem": forms.Textarea(attrs={"rows": 4}), "solution": forms.Textarea(attrs={"rows": 4}),
            "impact": forms.Textarea(attrs={"rows": 3}), "team": forms.Textarea(attrs={"rows": 3}),
            "capacity_skills": forms.Textarea(attrs={"rows": 3}), "capacity_resources": forms.Textarea(attrs={"rows": 3}),
            "capacity_partners": forms.Textarea(attrs={"rows": 2}), "capacity_gaps": forms.Textarea(attrs={"rows": 2}),
            "capacity_governance": forms.Textarea(attrs={"rows": 2}),
        }

    MANDATORY = {"title", "sector", "maturity", "location", "problem", "solution", "beneficiaries", "impact", "jobs", "budget", "sdgs", "team",
                 "capacity_skills", "capacity_resources", "ip_declared"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = name == "title"
            field.mandatory = name in self.MANDATORY  # shown with an asterisk
        prompts = {"sector": "Choose a sector", "maturity": "Choose a stage", "location": "Choose a town"}
        for name, prompt in prompts.items():
            field = self.fields[name]
            field.choices = [("", prompt)] + [c for c in field.choices if c[0] != ""]


class EvaluationForm(forms.Form):
    coi_declared = forms.BooleanField(label="I declare that I have no conflict of interest with this applicant or idea.", required=False)
    comment = forms.CharField(label="Feedback for the applicant", widget=forms.Textarea(attrs={"rows": 4}), help_text="Shared with the applicant anonymously.")
    private_note = forms.CharField(label="Private note for adjudicators (optional)", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    recommendation = forms.ChoiceField(choices=[("", "Choose…")] + list(Evaluation.Recommendation.choices))

    LEVELS = [(1, "Poor"), (2, "Weak"), (3, "Fair"), (4, "Good"), (5, "Excellent")]

    def __init__(self, *args, criteria=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.criteria = list(criteria)
        for c in self.criteria:
            self.fields[f"score_{c.pk}"] = forms.TypedChoiceField(
                label=c.name, help_text=c.guidance, choices=self.LEVELS, coerce=int, widget=forms.RadioSelect,
            )
            self.fields[f"note_{c.pk}"] = forms.CharField(
                label=f"Comment on {c.name.lower()} (optional)", required=False, max_length=1000,
                widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Why this score? Shared with the applicant anonymously."}),
            )

    def score_fields(self):
        return [(c, self[f"score_{c.pk}"], self[f"note_{c.pk}"]) for c in self.criteria]

    def notes(self):
        return {str(c.pk): self.cleaned_data.get(f"note_{c.pk}", "").strip() for c in self.criteria
                if self.cleaned_data.get(f"note_{c.pk}", "").strip()}

    def scores(self):
        return {str(c.pk): self.cleaned_data.get(f"score_{c.pk}") for c in self.criteria}


class DecisionForm(forms.Form):
    reason = forms.CharField(label="Reason for the decision", widget=forms.Textarea(attrs={"rows": 3}), help_text="Shared with the applicant.")


class AwardForm(forms.ModelForm):
    class Meta:
        model = Award
        fields = ["category", "amount", "message", "officer"]
        widgets = {"message": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import Role, User
        self.fields["officer"].queryset = User.objects.filter(role__in=[Role.ADMIN, Role.CONSULTANT], is_active=True).order_by("first_name")
        self.fields["officer"].empty_label = "Choose later"


class MilestoneUpdateForm(forms.Form):
    status = forms.ChoiceField(choices=[])
    note = forms.CharField(label="Update", required=False, max_length=2000,
                           widget=forms.Textarea(attrs={"rows": 2, "placeholder": "What's happened, and anything you need from CEDA"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Milestone
        self.fields["status"].choices = Milestone.Status.choices


class MilestoneAddForm(forms.Form):
    title = forms.CharField(max_length=150)
    due_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(max_length=255, required=False)


class MessageForm(forms.Form):
    body = forms.CharField(label="Message", widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Write a question or reply…"}))


class ReturnForm(forms.Form):
    note = forms.CharField(label="What needs fixing?", widget=forms.Textarea(attrs={"rows": 2}))
