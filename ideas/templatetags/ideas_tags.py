from django import template
from django.utils.html import format_html

from ideas.models import STAGES, Status, WorkflowSettings

register = template.Library()


@register.inclusion_tag("ideas/_stepper.html")
def stepper(idea):
    cur = idea.stage_index
    steps = []
    for i, name in enumerate(STAGES):
        state = "done" if i < cur else ("current" if i == cur else "")
        if idea.status == Status.REJECTED and i == 3:
            state = "stopped"
        steps.append({"n": i + 1, "name": name, "state": state})
    return {"steps": steps}


@register.simple_tag
def status_pill(idea):
    return format_html('<span class="pill s-{}">{}</span>', idea.status, idea.get_status_display())


@register.simple_tag
def score_badge(value):
    if value is None:
        return format_html('<span class="muted">—</span>')
    pm = WorkflowSettings.get().pass_mark
    cls = "hi" if value >= pm else ("mid" if value >= pm - 15 else "lo")
    return format_html('<span class="score {}">{}<small>/100</small></span>', cls, value)
