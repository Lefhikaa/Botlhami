"""What an applicant who isn't awarded still gets: a development report and next steps.

The advice is matched to the categories where the idea scored lowest, so every
applicant leaves with something specific to work on, not just a "no".
"""
from django.urls import reverse

from . import engine

# Advice by evaluation category, matched on a keyword in the category name.
ADVICE = {
    "strategic": {
        "title": "Show how it fits CEDA's priorities",
        "tips": ["Name the CEDA priority sector your idea serves and the Vision 2036 goal it supports.",
                 "Explain how it builds citizen-owned businesses or local value chains."],
        "links": [("Frequently asked questions", "support:help")],
    },
    "innovation": {
        "title": "Make what's new unmistakable",
        "tips": ["Research what already exists in Botswana and the region, and say clearly how yours is better.",
                 "If you have something new, talk to CIPA about protecting it before you share it widely."],
        "links": [("Regulator contacts, including CIPA", "support:help")],
    },
    "impact": {
        "title": "Put numbers on the impact",
        "tips": ["Estimate jobs created in the first two years, and how many go to young people and women.",
                 "Describe any environmental benefit, and how you'll measure it."],
        "links": [("Business plan template", "support:documents")],
    },
    "feasibility": {
        "title": "Prove it can work",
        "tips": ["Build a small prototype or pilot and record the results.",
                 "Cost every item, and show the resources, permits or standards you'll need (for example from BOBS)."],
        "links": [("Business plan template", "support:documents"), ("Regulator contacts", "support:help")],
    },
    "scalab": {
        "title": "Show how it grows and pays for itself",
        "tips": ["Add three-year financial projections and a clear way to earn revenue.",
                 "Explain how it could be repeated in other districts or countries."],
        "links": [("Business plan template", "support:documents")],
    },
    "capacity": {
        "title": "Strengthen the team",
        "tips": ["Fill skill gaps with a partner, adviser or mentor, and name the role they'll play.",
                 "Set up simple governance: who decides, how money is managed and records kept."],
        "links": [("Talk to a CEDA consultant", "chat:client")],
    },
}
GENERAL = {
    "title": "Keep building",
    "tips": ["Read the evaluators' comments carefully: they say what would change their score.",
             "Test your idea with real customers and keep a record of what you learn."],
    "links": [("Help centre", "support:help")],
}


def _advice_for(name):
    low = name.lower()
    for key, advice in ADVICE.items():
        if key in low:
            return advice
    return GENERAL


def development_report(idea):
    a = engine.analyse(idea)
    if not a:
        return None
    ranked = sorted((c for c in a.criteria if c.avg is not None), key=lambda c: (c.avg, -c.weight))
    focus = [c for c in ranked if c.avg < 3.5][:3] or ranked[:2]
    steps = []
    for c in focus:
        adv = _advice_for(c.name)
        steps.append({"criterion": c, "title": adv["title"], "tips": adv["tips"],
                      "links": [(label, reverse(url)) for label, url in adv["links"]]})
    comments = []
    for c in a.criteria:
        notes = [(e.notes or {}).get(c.id) for e in a.evaluations if (e.notes or {}).get(c.id)]
        comments.append((c, notes))
    decision = idea.history.filter(to_status=idea.status).order_by("-at").first()
    return {
        "a": a,
        "rows": [(c, round((c.avg or 0) * 20)) for c in a.criteria],
        "strengths": a.strengths[:3] or ranked[-1:],
        "focus": focus,
        "steps": steps,
        "comments": comments,
        "general_comments": [e.comment for e in a.evaluations],
        "decision": decision,
    }
