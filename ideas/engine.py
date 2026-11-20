"""The evaluation engine: turns independent evaluations into an explained recommendation.

Everything here is plain statistics and published rules, so every flag and every
recommendation can be explained to an applicant or an auditor. The engine advises;
the adjudication panel decides.
"""
from dataclasses import dataclass, field
from math import cos, pi, sin, sqrt
from statistics import mean, pstdev

from django.utils.html import escape

from .models import Status, WorkflowSettings

DISAGREE_POINTS = 2      # scores on one criterion this far apart (1–5 scale) count as disagreement
STRENGTH_AT = 4.0        # criterion average at or above this is a strength
WEAKNESS_AT = 2.5        # at or below this is a weakness
NEAR_PASS = 5            # combined score this close to the pass mark needs a closer look

APPROVE, FURTHER, DECLINE, WAITING = "approve", "further", "decline", "waiting"
LABELS = {
    APPROVE: "Recommend approval",
    FURTHER: "Needs further assessment",
    DECLINE: "Recommend decline",
    WAITING: "Waiting for evaluations",
}
# Validated categorical palette (dataviz skill), in fixed order. Evaluators and compared
# ideas take slots in order; the average is drawn in ink so it never competes with a slot.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK = "#1c2329"


@dataclass
class CriterionResult:
    id: str
    name: str
    weight: int
    scores: list
    avg: float = None
    low: int = None
    high: int = None
    spread: int = 0
    disagree: bool = False


@dataclass
class Analysis:
    idea: object
    evaluations: list
    letters: list
    criteria: list
    totals: list
    combined: int = None
    total_sd: float = 0
    pass_mark: int = 65
    strengths: list = field(default_factory=list)
    weaknesses: list = field(default_factory=list)
    disagreements: list = field(default_factory=list)
    advance_votes: int = 0
    decline_votes: int = 0
    revise_votes: int = 0
    expected: int = 0
    verdict: str = WAITING
    reasons: list = field(default_factory=list)
    summary: list = field(default_factory=list)

    @property
    def label(self):
        return LABELS[self.verdict]

    @property
    def complete(self):
        return len(self.evaluations) >= self.expected

    def radar(self, size=340):
        series = [(f"Evaluator {letter}", [e.scores.get(c.id) for c in self.criteria], SERIES[i % len(SERIES)], False)
                  for i, (letter, e) in enumerate(zip(self.letters, self.evaluations))]
        if len(self.evaluations) > 1:
            series.append(("Average", [c.avg for c in self.criteria], INK, True))
        return radar_svg([c.name for c in self.criteria], series, size=size, title=f"Scores for {self.idea.reference} by criterion")


def analyse(idea, ws=None):
    """Analyse the current round's evaluations of one idea. Returns None if nobody has scored yet."""
    ws = ws or WorkflowSettings.get()
    evals = sorted(idea.round_evaluations(), key=lambda e: e.submitted_at)
    if not evals:
        return None
    rubric = evals[0].rubric
    criteria = []
    for c in rubric:
        cid = str(c["id"])
        scores = [e.scores.get(cid) for e in evals if e.scores.get(cid)]
        r = CriterionResult(cid, c["name"], c["weight"], scores)
        if scores:
            r.avg = round(mean(scores), 1)
            r.low, r.high = min(scores), max(scores)
            r.spread = r.high - r.low
            r.disagree = len(scores) > 1 and r.spread >= DISAGREE_POINTS
        criteria.append(r)

    totals = [e.total for e in evals]
    a = Analysis(
        idea=idea, evaluations=evals, letters=[chr(65 + i) for i in range(len(evals))], criteria=criteria, totals=totals,
        combined=round(mean(totals)), total_sd=round(pstdev(totals), 1) if len(totals) > 1 else 0,
        pass_mark=ws.pass_mark, expected=max(ws.evaluators_per_idea, idea.active_assignments().count()),
    )
    scored = [c for c in criteria if c.avg is not None]
    a.strengths = sorted([c for c in scored if c.avg >= STRENGTH_AT], key=lambda c: (-c.avg, -c.weight))
    a.weaknesses = sorted([c for c in scored if c.avg <= WEAKNESS_AT], key=lambda c: (c.avg, -c.weight))
    a.disagreements = sorted([c for c in criteria if c.disagree], key=lambda c: (-c.spread, -c.weight))
    recs = [e.recommendation for e in evals]
    a.advance_votes, a.revise_votes, a.decline_votes = recs.count("advance"), recs.count("revise"), recs.count("decline")
    _decide(a, ws)
    _summarise(a)
    return a


def _decide(a, ws):
    gap = max(a.totals) - min(a.totals) if len(a.totals) > 1 else 0
    if not a.complete and a.idea.status in (Status.SUBMITTED, Status.IN_REVIEW):
        a.verdict = WAITING
        missing = a.expected - len(a.evaluations)
        a.reasons.append(f"{missing} more evaluation{'s' if missing != 1 else ''} expected before a recommendation.")
        return
    concerns = []
    if gap >= ws.score_gap_flag:
        concerns.append(f"Evaluators' totals differ by {gap} points (the flag is set at {ws.score_gap_flag}).")
    heavy = [c for c in a.disagreements if c.weight >= 20]
    if heavy:
        concerns.append("Evaluators disagree on " + _join([f"{_lc(c.name)} ({c.weight}% of the score)" for c in heavy]) + ".")
    elif len(a.disagreements) >= 2:
        concerns.append(f"Evaluators disagree on {len(a.disagreements)} criteria.")
    if a.advance_votes and a.decline_votes:
        concerns.append("One evaluator recommends advancing and another recommends declining.")
    if abs(a.combined - a.pass_mark) <= NEAR_PASS:
        concerns.append(f"The combined score of {a.combined} is within {NEAR_PASS} points of the pass mark ({a.pass_mark}).")

    if concerns:
        a.verdict = FURTHER
        a.reasons = concerns + ["A further opinion, or a discussion between the evaluators, would make the decision safer."]
    elif a.combined >= a.pass_mark:
        a.verdict = APPROVE
        a.reasons.append(f"The combined score of {a.combined} is above the pass mark of {a.pass_mark}, and the evaluators broadly agree.")
        if a.advance_votes == len(a.evaluations):
            a.reasons.append("Every evaluator recommends advancing.")
    else:
        a.verdict = DECLINE
        a.reasons.append(f"The combined score of {a.combined} is below the pass mark of {a.pass_mark}, and the evaluators broadly agree.")
        if a.revise_votes:
            a.reasons.append("An evaluator suggests revising rather than declining, so the panel may prefer to request a revision.")


def _summarise(a):
    n = len(a.evaluations)
    side = "above" if a.combined >= a.pass_mark else "below"
    a.summary.append(f"Scored {a.combined}/100 by {n} evaluator{'s' if n != 1 else ''}, {side} the pass mark of {a.pass_mark}.")
    if a.strengths:
        a.summary.append("Strongest on " + _join([f"{_lc(c.name)} ({c.avg:g}/5)" for c in a.strengths[:2]]) + ".")
    if a.weaknesses:
        a.summary.append("Weakest on " + _join([f"{_lc(c.name)} ({c.avg:g}/5)" for c in a.weaknesses[:2]]) + ".")
    if not a.strengths and not a.weaknesses:
        best = max((c for c in a.criteria if c.avg is not None), key=lambda c: c.avg)
        worst = min((c for c in a.criteria if c.avg is not None), key=lambda c: c.avg)
        a.summary.append(f"No criterion stands out strongly; the best is {_lc(best.name)} ({best.avg:g}/5) and the weakest {_lc(worst.name)} ({worst.avg:g}/5).")
    for c in a.disagreements[:2]:
        a.summary.append(f"Evaluators disagree on {_lc(c.name)}: scores range from {c.low} to {c.high}.")
    if n > 1:
        votes = [(v, what) for v, what in [(a.advance_votes, "advancing"), (a.revise_votes, "a revision"), (a.decline_votes, "declining")] if v]
        if len(votes) == 1:
            who = "Both evaluators" if n == 2 else f"All {n} evaluators"
            a.summary.append(f"{who} recommend {votes[0][1]}.")
        else:
            parts = [f"{WORDS.get(v, v)} recommend{'s' if v == 1 else ''} {what}" for v, what in votes]
            a.summary.append(_join(parts)[0].upper() + _join(parts)[1:] + ".")


WORDS = {1: "one", 2: "two", 3: "three", 4: "four"}


def _lc(name):
    """Lower-case a criterion name for use mid-sentence, keeping acronyms such as CEDA."""
    return name[:1].lower() + name[1:]


def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def portfolio_row(idea, ws):
    a = analyse(idea, ws)
    if not a:
        return None
    return {"idea": idea, "a": a, "avg": round(mean([c.avg for c in a.criteria if c.avg is not None]), 2)}


# --- radar chart ---------------------------------------------------------------
def radar_svg(axes, series, size=340, title="Radar chart"):
    """A server-drawn radar (spider) chart on a 1–5 scale, as an inline SVG string.

    series: [(label, [value or None per axis], colour, is_average)].
    Every point has a <title> so hovering shows its value; a table beside the chart
    gives the same numbers for anyone who can't read the colours.
    """
    pad_x, pad_y = 120, 46
    w, h = size + 2 * pad_x, size + 2 * pad_y
    cx, cy, r = w / 2, h / 2, size / 2
    n = len(axes)

    def pt(i, v):
        ang = -pi / 2 + 2 * pi * i / n
        return cx + r * (v / 5) * cos(ang), cy + r * (v / 5) * sin(ang)

    out = [f'<svg class="radar" viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="{escape(title)}" xmlns="http://www.w3.org/2000/svg">']
    for ring in range(1, 6):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, ring) for i in range(n)))
        out.append(f'<polygon points="{pts}" fill="none" stroke="#dde2e6" stroke-width="{1.2 if ring == 5 else 0.8}"/>')
    for i, name in enumerate(axes):
        x, y = pt(i, 5)
        out.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="#dde2e6" stroke-width="0.8"/>')
        lx, ly = pt(i, 5.55)
        anchor = "middle" if abs(lx - cx) < 8 else ("start" if lx > cx else "end")
        words, lines, cur = name.split(), [], ""
        for word in words:
            if len(cur) + len(word) > 16 and cur:
                lines.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        lines.append(cur)
        dy0 = -(len(lines) - 1) * 7 + (4 if ly > cy + 4 else (-4 if ly < cy - 4 else 4))
        tspans = "".join(f'<tspan x="{lx:.1f}" dy="{dy0 if k == 0 else 14}">{escape(t)}</tspan>' for k, t in enumerate(lines))
        out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" class="radar-axis">{tspans}</text>')
    for ring in (1, 3, 5):
        x, y = pt(0, ring)
        out.append(f'<text x="{x + 5:.1f}" y="{y + 4:.1f}" class="radar-tick">{ring}</text>')
    for label, values, colour, is_avg in series:
        pts = [(pt(i, v), v, axes[i]) for i, v in enumerate(values) if v]
        if len(pts) < 2:
            continue
        poly = " ".join(f"{x:.1f},{y:.1f}" for (x, y), _, _ in pts)
        dash = ' stroke-dasharray="5 4"' if is_avg else ""
        fill = f'fill="{colour}" fill-opacity="0.06"' if is_avg else 'fill="none"'
        out.append(f'<g class="radar-series"><title>{escape(label)}</title>'
                   f'<polygon points="{poly}" {fill} stroke="{colour}" stroke-width="{2.5 if is_avg else 2}"{dash} stroke-linejoin="round"/>')
        for (x, y), v, axis in pts:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{colour}" stroke="#fff" stroke-width="2">'
                       f'<title>{escape(label)}: {escape(axis)} {v:g}/5</title></circle>')
        out.append("</g>")
    out.append("</svg>")
    return "".join(out)


def legend(series_labels):
    """[(label, colour, dashed)] -> list of dicts for the template."""
    return [{"label": lab, "colour": col, "dashed": d} for lab, col, d in series_labels]


def spread_sd(values):
    return round(sqrt(sum((v - mean(values)) ** 2 for v in values) / len(values)), 2) if len(values) > 1 else 0
