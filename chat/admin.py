from django.contrib import admin

from .models import ChatMessage, ChatSettings, Conversation, PublicHoliday


@admin.register(ChatSettings)
class ChatSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ChatSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name")


class MessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("kind", "sender", "body", "created_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "topic", "agent", "status", "started_as", "created_at", "rating")
    list_filter = ("status", "started_as", "topic")
    inlines = [MessageInline]
    readonly_fields = ("customer", "guest_name", "guest_email", "agent", "status", "started_as", "created_at", "accepted_at", "closed_at", "rating")
