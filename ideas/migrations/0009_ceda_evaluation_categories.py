"""Use CEDA's six evaluation categories from the 16 November 2026 briefing.

CEDA gave the categories and the 1–5 scale (1 Poor, 5 Excellent) but no weights, so
these weights are ours and administrators can change them. Past evaluations keep the
rubric they were scored against.
"""
from django.db import migrations

CEDA = [
    # name, earlier names this replaces, weight, guidance
    ("Strategic alignment", ["Strategic alignment with CEDA", "Strategic alignment"], 15,
     "Supports CEDA's mission and Botswana's Vision 2036."),
    ("Innovation and originality", ["Innovation and originality"], 20,
     "A significant improvement or a new concept, for example one using emerging technology."),
    ("Impact potential", ["Economic and social impact", "Socio-economic impact"], 20,
     "Job creation, youth and women's empowerment, and environmental sustainability."),
    ("Feasibility and viability", ["Feasibility and implementation capacity", "Feasibility", "Feasibility and readiness"], 15,
     "Technically sound, with the resources it needs available."),
    ("Scalability and sustainability", ["Scalability"], 15,
     "Can be replicated, is financially sustainable and has clear plans to grow."),
    ("Implementation capacity, team capability and governance", [], 15,
     "Relevant experience and leadership: the team's skills, the resources in place, partners, "
     "plans for any gaps, and how the business is governed."),
]


def forwards(apps, schema_editor):
    Criterion = apps.get_model("ideas", "Criterion")
    keep = []
    for order, (name, old, weight, guidance) in enumerate(CEDA):
        c = (Criterion.objects.filter(name=name).first()
             or Criterion.objects.filter(name__in=old).exclude(pk__in=keep).first()
             or Criterion(name=name))
        c.name, c.weight, c.guidance, c.order, c.active = name, weight, guidance, order, True
        c.save()
        keep.append(c.pk)
    Criterion.objects.exclude(pk__in=keep).update(active=False)  # e.g. Market potential


class Migration(migrations.Migration):
    dependencies = [("ideas", "0008_criterion_comments_and_governance")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
