import csv

from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from .models import ContactMessage, SiteSettings, Subscriber


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Store", {"fields": ("store_enabled",)}),
        ("Home page video", {"fields": ("hero_video", "hero_poster", "hero_logo")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:core_sitesettings_change", args=[SiteSettings.load().pk]))


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "source", "is_active", "created_at", "unsubscribed_at")
    list_filter = ("is_active", "source", "created_at")
    search_fields = ("email",)
    readonly_fields = ("created_at", "unsubscribed_at")
    actions = ["export_csv"]

    @admin.action(description="Export selected to CSV (for your email tool)")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="subscribers.csv"'
        writer = csv.writer(response)
        writer.writerow(["email", "subscribed", "source", "joined", "unsubscribe_url"])
        for sub in queryset:
            writer.writerow([sub.email, sub.is_active, sub.source, sub.created_at.date().isoformat(),
                             request.build_absolute_uri(sub.get_unsubscribe_url())])
        return response


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "order_number", "created_at", "handled")
    list_editable = ("handled",)
    list_filter = ("handled", "created_at")
    search_fields = ("name", "email", "order_number", "message")
    readonly_fields = ("name", "email", "order_number", "message", "created_at")
