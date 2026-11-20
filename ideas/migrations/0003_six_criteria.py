"""Move to the six evaluation criteria the team agreed on 20 November 2026.

Past evaluations keep the rubric they were scored against (each stores a snapshot),
so changing the criteria never changes a score that has already been given.
"""
from django.db import migrations

SIX = [
    ("Innovation and originality", ["Innovation and originality"], 20,
     "How new is the idea in Botswana, and how clearly does it differ from what already exists?"),
    ("Market potential", ["Market potential"], 20,
     "Evidence of demand, the size of the market and a credible route to revenue."),
    ("Feasibility", ["Feasibility and readiness"], 15,
     "Can the team deliver it with realistic resources, skills and timelines?"),
    ("Economic and social impact", ["Socio-economic impact"], 15,
     "Jobs, income, youth and women's participation, inclusion and sustainability."),
    ("Strategic alignment with CEDA", ["Strategic alignment"], 15,
     "Fit with CEDA's mandate, citizen economic empowerment and national development goals."),
    ("Scalability", [], 15,
     "Can it grow beyond the first site or customers, across Botswana or into the region?"),
]


def forwards(apps, schema_editor):
    Criterion = apps.get_model("ideas", "Criterion")
    keep = []
    for order, (name, old_names, weight, guidance) in enumerate(SIX):
        c = Criterion.objects.filter(name__in=[name] + old_names).first() or Criterion(name=name)
        c.name, c.weight, c.guidance, c.order, c.active = name, weight, guidance, order, True
        c.save()
        keep.append(c.pk)
    Criterion.objects.exclude(pk__in=keep).update(active=False)


class Migration(migrations.Migration):
    dependencies = [("ideas", "0002_default_criteria")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
