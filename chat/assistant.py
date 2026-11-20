"""Botlhami Assistant: instant answers from Botlhami's own help content.

It searches what administrators already maintain (FAQs, documents, regulator contacts,
service levels, chat hours, evaluation categories) plus a short guide to the platform,
and answers with the best match and a link. When nothing matches well it says so and
offers a human consultant. Nothing is invented: every answer comes from a known source.

If AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY and AZURE_OPENAI_DEPLOYMENT are set, the
top matches are passed to an Azure OpenAI model to phrase a reply, grounded only in
those sources. Without them, or if the call fails, the plain search answer is used.
"""
import json
import logging
import math
import re
import urllib.request
from collections import Counter

from django.conf import settings
from django.urls import reverse

log = logging.getLogger(__name__)

STOP = set("""a an and are as at be but by can could do does for from get has have how i if in into is it its me my no not
of on or our please should so than that the their them then there these they this to us was we what when which who
why will with would you your yours about any need want know tell much many""".split())

# Words people use for the same thing. Each group is expanded so any one finds the others.
SYNONYMS = [
    {"omang", "id", "identity", "identification", "national"},
    {"password", "login", "signin", "sign", "log", "locked", "forgot", "reset"},
    {"register", "registration", "account", "signup", "create"},
    {"idea", "application", "submission", "proposal", "innovation", "apply", "submit"},
    {"score", "scoring", "evaluation", "evaluate", "criteria", "criterion", "category", "categories", "judge", "assessed"},
    {"money", "funding", "fund", "finance", "financing", "grant", "loan", "seed", "award", "prize"},
    {"document", "documents", "form", "forms", "template", "upload", "file", "files", "checklist"},
    {"track", "status", "progress", "where", "stage", "tracker"},
    {"chat", "consultant", "talk", "person", "human", "agent", "contact", "call", "phone"},
    {"problem", "fault", "error", "broken", "ticket", "support", "help", "bug"},
    {"regulator", "licence", "license", "permit", "cipa", "burs", "bobs", "bocra", "compliance", "register_company"},
    {"decline", "declined", "rejected", "reject", "unsuccessful", "fail", "failed"},
    {"trademark", "patent", "copyright", "intellectual", "ip", "protect", "cipa", "design"},
    {"company", "business", "registration", "cipa", "register"},
    {"hours", "open", "time", "times", "available", "holiday"},
    {"email", "code", "otp", "verification", "verify", "spam"},
    {"data", "privacy", "protect", "protection", "personal", "secure", "security"},
]
def _stem(w):
    for suf in ("ings", "ing", "ies", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            w = w[: -len(suf)] + ("y" if suf == "ies" else "")
            break
    if len(w) > 4 and w.endswith("e"):  # score / scored / scoring all become "scor"
        w = w[:-1]
    return w


SYN = {}
for group in SYNONYMS:
    for w in group:
        SYN.setdefault(_stem(w), set()).update(group)


def tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [_stem(w) for w in words if w not in STOP and len(w) > 1]


def expand(words):
    """{term: weight}: the words asked count fully, their synonyms less, so a synonym never outranks the real word."""
    out = {}
    for w in words:
        out[w] = 1.0
    for w in words:
        for s in SYN.get(w, ()):
            s = _stem(s)
            out.setdefault(s, 0.35)
    return out


# A short guide to the platform itself, kept here because it describes how the code works.
GUIDE = [
    ("How do I submit an idea?",
     "Create an account and verify your email, then choose Submit an idea. Fill in the idea, impact, team and implementation "
     "capacity sections and upload your documents. You can save a draft at any time; the completeness bar shows what's "
     "still missing. You'll also need to add your Omang before you submit.", "ideas:new"),
    ("Why do you need my Omang, and how is it protected?",
     "CEDA supports citizen-owned businesses, so applicants confirm their identity with their Omang. We check the number's "
     "format, allow one account per Omang, and a CEDA officer checks the copy you upload. The number itself is never stored "
     "in readable form: only a protected fingerprint and the last 4 digits. You can submit while the check is pending; an "
     "award needs a verified Omang.", "accounts:identity"),
    ("How will my idea be scored?",
     "At least two independent evaluators score it from 1 (Poor) to 5 (Excellent) on CEDA's six categories: strategic "
     "alignment, innovation and originality, impact potential, feasibility and viability, scalability and sustainability, "
     "and implementation capacity, team capability and governance. They don't see your name. The adjudication panel then "
     "decides, guided by an explained recommendation.", "core:home"),
    ("How do I know where my idea is?",
     "Open My ideas. Each idea has a tracker: Submission, Review, Feedback, Approval and Award. You get an alert, and an "
     "email if alerts are on, every time the status changes.", "ideas:mine"),
    ("What happens if my idea isn't awarded or is declined?",
     "If your idea is declined or rejected, you still get a personal development report: your scores and the evaluators' comments by category, next steps matched to "
     "your weakest areas, support such as a feedback session or mentorship, and a certificate of participation. You can "
     "start a new version and submit it in the next call.", "core:home"),
    ("What happens after an award?",
     "Your idea gets an implementation plan with dated steps and a CEDA officer. You report progress on each step and CEDA "
     "confirms it.", "core:home"),
    ("I didn't receive my code or reset email",
     "Check your spam or junk folder. If it's there, mark it as 'Not spam' first, because email providers switch off links in "
     "spam. The reset email also shows the full link as text that you can copy into your browser.", "accounts:password_reset"),
    ("How do I report a problem with the portal?",
     "Raise a support ticket. Choose how serious it is and you'll get a reference number and a response time: critical "
     "faults are answered within 1 hour.", "support:new"),
]


def knowledge():
    """Everything the assistant can answer from, as (title, text, url, source) records."""
    from support.models import FAQ, RegulatorContact, Resource, ServiceLevel

    from .models import ChatSettings

    items = [(q, a, reverse(u), "Botlhami guide") for q, a, u in GUIDE]
    items += [(f.question, f.answer, reverse("support:help"), "FAQ") for f in FAQ.objects.filter(published=True)]
    for r in Resource.objects.filter(published=True).exclude(file=""):
        items.append((f"{r.title} ({r.get_kind_display().lower()})",
                      f"{r.description} You can download it from Application forms and documents."
                      + (" Applicants must include it with their idea." if r.mandatory else ""),
                      reverse("support:download", args=[r.pk]), "Document"))
    for c in RegulatorContact.objects.filter(published=True):
        contact = " ".join(x for x in [c.phone and f"Phone {c.phone}.", c.email and f"Email {c.email}.", c.website and f"Website {c.website}."] if x)
        items.append((f"{c.name} ({c.acronym})", f"Contact {c.acronym or c.name} for: {c.helps_with}. {contact}".strip(),
                      reverse("support:help"), "Regulator contact"))
    levels = "; ".join(f"{lvl.label}: response within {lvl.response_label}, fixed within {lvl.resolution_label}" for lvl in ServiceLevel.objects.all())
    if levels:
        items.append(("How quickly will a problem be fixed?", f"Support tickets have target times by severity. {levels}.",
                      reverse("support:sla"), "Service levels"))
    cs = ChatSettings.get()
    items.append(("When can I chat with a CEDA consultant?",
                  f"Live chat is open from {str(cs.opens_at)[:5]} to {str(cs.closes_at)[:5]} on working days, except public holidays. "
                  "Outside those hours you can leave a message and we'll reply by email.", reverse("chat:client"), "Live chat"))
    return items


def search(question, items=None, limit=3):
    items = items if items is not None else knowledge()
    docs = [(tokens(t) * 3 + tokens(body)) for t, body, _, _ in items]  # titles count more
    n = len(docs)
    df = Counter(w for d in docs for w in set(d))
    q = expand(tokens(question))
    if not q:
        return []
    scored = []
    for (title, body, url, source), d in zip(items, docs):
        tf = Counter(d)
        length = len(d) or 1
        s = sum(wt * math.log(1 + n / (1 + df[w])) * tf[w] / (tf[w] + 1.2 * (0.25 + 0.75 * length / 40))
                for w, wt in q.items() if w in tf)
        core = [w for w, wt in q.items() if wt == 1.0]
        title_words = set(tokens(title))
        if core and sum(w in title_words for w in core) >= max(1, len(core) - 1):
            s += 1.5  # the question's own words are in the title: the most reliable sign of a match
        if s:
            scored.append((s, title, body, url, source))
    scored.sort(reverse=True)
    return scored[:limit]


THRESHOLD = 1.6


def answer(question):
    """Returns a dict the chat page shows: the answer, where it came from, and other suggestions."""
    question = (question or "").strip()[:500]
    hits = search(question)
    if not hits or hits[0][0] < THRESHOLD:
        return {
            "answered": False,
            "text": "I'm not sure about that one. A CEDA consultant can help: start a chat below, or raise a support ticket.",
            "suggestions": [h[1] for h in hits[:3]],
        }
    best = hits[0]
    text = _llm_reply(question, hits) or best[2]
    return {"answered": True, "title": best[1], "text": text, "url": best[3], "source": best[4],
            "suggestions": [h[1] for h in hits[1:3]]}


def _llm_reply(question, hits):
    endpoint = getattr(settings, "AZURE_OPENAI_ENDPOINT", "")
    key = getattr(settings, "AZURE_OPENAI_KEY", "")
    deployment = getattr(settings, "AZURE_OPENAI_DEPLOYMENT", "")
    if not (endpoint and key and deployment):
        return None
    sources = "\n\n".join(f"[{i + 1}] {h[1]}\n{h[2]}" for i, h in enumerate(hits))
    body = {
        "messages": [
            {"role": "system", "content": "You are Botlhami Assistant for CEDA's innovation portal in Botswana. Answer in at most "
                                          "three short sentences, in plain English, using only the sources given. If they don't "
                                          "answer the question, say so and suggest talking to a CEDA consultant."},
            {"role": "user", "content": f"Sources:\n{sources}\n\nQuestion: {question}"},
        ],
        "max_tokens": 180, "temperature": 0.2,
    }
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version=2024-06-01"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        log.warning("Azure OpenAI reply failed; using the search answer", exc_info=True)
        return None
