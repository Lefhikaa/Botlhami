from django.contrib import admin

from .models import FAQ, RegulatorContact, Resource, ServiceLevel, Ticket, TicketReply


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "mandatory", "published", "updated_at")
    list_filter = ("kind", "published")


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "published", "order")
    list_filter = ("category", "published")


@admin.register(RegulatorContact)
class RegulatorAdmin(admin.ModelAdmin):
    list_display = ("name", "acronym", "phone", "website", "published")


@admin.register(ServiceLevel)
class ServiceLevelAdmin(admin.ModelAdmin):
    list_display = ("label", "response_hours", "resolution_hours")


class ReplyInline(admin.TabularInline):
    model = TicketReply
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("reference", "subject", "level", "status", "raised_by", "assigned_to", "created_at")
    list_filter = ("status", "level")
    inlines = [ReplyInline]
