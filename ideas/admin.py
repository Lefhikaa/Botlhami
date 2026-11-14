from django.contrib import admin

from .models import Award, Criterion, Idea, IdeaDocument, StatusEvent, WorkflowSettings


@admin.register(Criterion)
class CriterionAdmin(admin.ModelAdmin):
    list_display = ("name", "weight", "active", "order")
    list_editable = ("weight", "active", "order")


@admin.register(WorkflowSettings)
class WorkflowSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not WorkflowSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class DocumentInline(admin.TabularInline):
    model = IdeaDocument
    extra = 0
    readonly_fields = ("original_name", "size", "uploaded_by", "uploaded_at")


class HistoryInline(admin.TabularInline):
    model = StatusEvent
    extra = 0
    readonly_fields = ("from_status", "to_status", "actor", "note", "at")
    can_delete = False


@admin.register(Idea)
class IdeaAdmin(admin.ModelAdmin):
    list_display = ("reference", "title", "submitter", "status", "round", "submitted_at")
    list_filter = ("status", "sector")
    search_fields = ("reference", "title", "submitter__email")
    readonly_fields = ("reference", "status", "round", "submitted_at", "status_changed_at")
    inlines = [DocumentInline, HistoryInline]


admin.site.register(Award)
