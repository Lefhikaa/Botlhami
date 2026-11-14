from django.db import migrations

CRITERIA = [
    ("Innovation and originality", "How new is the idea in Botswana, and how clearly does it differ from what exists?", 25),
    ("Strategic alignment", "Fit with CEDA's priorities, citizen economic empowerment and national development goals.", 20),
    ("Market potential", "Evidence of demand, size of the market and a credible route to revenue.", 20),
    ("Feasibility and readiness", "Can the team deliver it with realistic resources and timelines?", 15),
    ("Socio-economic impact", "Jobs, youth participation, inclusion and sustainability outcomes.", 20),
]


def create_defaults(apps, schema_editor):
    Criterion = apps.get_model("ideas", "Criterion")
    WorkflowSettings = apps.get_model("ideas", "WorkflowSettings")
    for i, (name, guidance, weight) in enumerate(CRITERIA):
        Criterion.objects.get_or_create(name=name, defaults={"guidance": guidance, "weight": weight, "order": i})
    WorkflowSettings.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("ideas", "0001_initial")]
    operations = [migrations.RunPython(create_defaults, migrations.RunPython.noop)]
