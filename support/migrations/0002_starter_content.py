"""Starter content: service levels, FAQs and regulator contacts.

Administrators can change all of it from Manage content. Regulator phone numbers and
emails are left blank on purpose: add them from each authority's official website.
"""

from django.db import migrations

LEVELS = [
    ("critical", "Critical", "The portal is down, or nobody can sign in or submit.", 1, 4),
    ("high", "High", "A key task fails for you, for example you can't submit before a deadline.", 4, 24),
    ("medium", "Medium", "Something works incorrectly but there is a workaround.", 8, 72),
    ("low", "Low", "A question, a cosmetic problem or a suggestion.", 24, 120),
]

FAQS = [
    ("applying", "Who can submit an idea?",
     "Individual innovators and businesses in Botswana, subject to the eligibility rules published for each call. Create an account, verify your email address and choose Submit an idea."),
    ("applying", "Can I save my idea and finish it later?",
     "Yes. Choose Save draft at any time. The completeness bar shows what is still missing, and you can only submit once every mandatory item is done."),
    ("applying", "Which documents do I need?",
     "See Application forms and documents in the Help centre. Documents marked as required must be uploaded with your idea. Files can be PDF, Word, Excel, PowerPoint or images, up to 10 MB each."),
    ("applying", "Can I change my idea after submitting it?",
     "Not while it is with the panel. If the evaluators ask for changes, the idea comes back to you as Revision requested and you can edit and resubmit it."),
    ("evaluation", "How are ideas evaluated?",
     "Ideas are screened for completeness, then scored by at least two independent evaluators against published, weighted criteria. Evaluators don't see your name. An adjudication panel makes the final decision."),
    ("evaluation", "How will I know where my idea is?",
     "Open My ideas to see the tracker: Submission, Review, Feedback, Approval and Award. You also get an in-app alert, and an email if alerts are switched on in your profile, every time the status changes."),
    ("evaluation", "How long does a decision take?",
     "By default, screening aims to finish within 5 days and evaluation within 14. The administrator sets these targets, and late items are flagged automatically."),
    ("awards", "What can a successful idea receive?",
     "Awards include seed funding referral, incubation and mentorship placement, Innovation Champion recognition or a pilot partnership with CEDA."),
    ("awards", "Who owns my idea?",
     "You keep ownership of your idea when you submit it. Read the terms of each funding or partnership offer carefully before you accept it."),
    ("account", "I forgot my password. What do I do?",
     "Choose Forgot password on the sign-in page. We email you a link to set a new one. You can also sign in with a one-time code sent to your email."),
    ("account", "How is my personal data protected?",
     "Your data is stored in Azure's South Africa North region, encrypted in transit and at rest, and only people with a role in your application can see it. We follow Botswana's Data Protection Act, 2024."),
    ("support", "How do I get help?",
     "Use Chat with CEDA during service hours (09:00–16:00 on working days), or raise a support ticket at any time. Each ticket gets a reference number and a response time based on how serious it is."),
]

REGULATORS = [
    ("Companies and Intellectual Property Authority", "CIPA", "Registering a company or business name, and protecting patents, trademarks and designs.", "https://www.cipa.co.bw"),
    ("Botswana Unified Revenue Service", "BURS", "Tax registration, tax clearance certificates and VAT.", "https://www.burs.org.bw"),
    ("Botswana Bureau of Standards", "BOBS", "Product standards, testing and certification.", "https://www.bobstandards.bw"),
    ("Botswana Communications Regulatory Authority", "BOCRA", "Licences for telecoms, broadcasting, postal and some online services.", "https://www.bocra.org.bw"),
    ("Bank of Botswana", "BoB", "Payment services and fintech, including the regulatory sandbox.", "https://www.bankofbotswana.bw"),
    ("Non-Bank Financial Institutions Regulatory Authority", "NBFIRA", "Micro-lending, insurance, investment and other non-bank financial services.", "https://www.nbfira.org.bw"),
    ("Botswana Medicines Regulatory Authority", "BoMRA", "Medicines, medical devices and health products.", "https://www.bomra.co.bw"),
    ("Information and Data Protection Commission", "IDPC", "Handling personal data and complying with the Data Protection Act, 2024.", ""),
    ("Competition and Consumer Authority", "CCA", "Fair competition and consumer protection.", "https://www.cca.co.bw"),
]


def seed(apps, schema_editor):
    ServiceLevel = apps.get_model("support", "ServiceLevel")
    FAQ = apps.get_model("support", "FAQ")
    RegulatorContact = apps.get_model("support", "RegulatorContact")
    for i, (sev, label, desc, resp, res) in enumerate(LEVELS):
        ServiceLevel.objects.get_or_create(severity=sev, defaults=dict(label=label, description=desc, response_hours=resp, resolution_hours=res, order=i))
    if not FAQ.objects.exists():
        FAQ.objects.bulk_create([FAQ(category=c, question=q, answer=a, order=i) for i, (c, q, a) in enumerate(FAQS)])
    if not RegulatorContact.objects.exists():
        RegulatorContact.objects.bulk_create([
            RegulatorContact(name=n, acronym=a, helps_with=h, website=w, order=i) for i, (n, a, h, w) in enumerate(REGULATORS)
        ])


class Migration(migrations.Migration):
    dependencies = [("support", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
