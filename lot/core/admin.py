from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from .models import ContactMessage, FeaturedProduct, Review, SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fields = ("store_enabled",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:core_sitesettings_change", args=[SiteSettings.load().pk]))


@admin.register(FeaturedProduct)
class FeaturedProductAdmin(admin.ModelAdmin):
    list_display = ("product", "position", "in_stock")
    list_editable = ("position",)
    autocomplete_fields = ("product",)

    @admin.display(boolean=True, description="In stock")
    def in_stock(self, obj):
        return obj.product.in_stock


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("author_name", "location", "body", "rating", "is_published", "position")
    list_editable = ("is_published", "position")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "order_number", "created_at", "handled")
    list_editable = ("handled",)
    list_filter = ("handled", "created_at")
    search_fields = ("name", "email", "order_number", "message")
    readonly_fields = ("name", "email", "order_number", "message", "created_at")
