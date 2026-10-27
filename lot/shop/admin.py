from django.conf import settings
from django.contrib import admin, messages
from django.db.models import Sum
from django.utils import timezone
from django.utils.html import format_html

from .models import Category, Order, OrderItem, Product, ProductImage, ShippingMethod, Variant


def money(value):
    return f"{settings.CURRENCY_SYMBOL}{value:,.2f}"


def thumb(image, size=56):
    if not image:
        return "—"
    return format_html(
        '<img src="{}" style="width:{}px;height:{}px;object-fit:cover;border-radius:4px;border:1px solid #ddd">',
        image.url,
        size,
        size,
    )


def stock_badge(stock):
    if stock <= 0:
        color, label = "#b91c1c", "Sold out"
    elif stock <= settings.LOW_STOCK_THRESHOLD:
        color, label = "#b45309", f"Low · {stock}"
    else:
        color, label = "#15803d", str(stock)
    return format_html(
        '<span style="display:inline-block;padding:2px 8px;border-radius:999px;background:{};color:#fff;'
        'font-weight:600;font-size:11px">{}</span>',
        color,
        label,
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "product_count", "position")
    list_editable = ("position",)
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()


class VariantInline(admin.TabularInline):
    model = Variant
    extra = 0
    fields = ("name", "sku", "price_override", "stock", "position")


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("preview", "image", "alt", "position")
    readonly_fields = ("preview",)

    @admin.display(description="")
    def preview(self, obj):
        return thumb(obj.image if obj.pk else None, 72)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("image_thumb", "name", "category", "price", "stock_total", "is_active", "updated_at")
    list_display_links = ("image_thumb", "name")
    list_editable = ("price", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "slug", "variants__sku")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [VariantInline, ProductImageInline]
    actions = ["make_visible", "make_hidden"]
    fieldsets = (
        (None, {"fields": ("name", "slug", "category", "is_active")}),
        ("Pricing", {"fields": ("price", "compare_at_price")}),
        ("Copy", {"fields": ("tagline", "description", "details")}),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("category")
            .prefetch_related("images")
            .annotate(_stock=Sum("variants__stock"))
        )

    @admin.display(description="")
    def image_thumb(self, obj):
        image = obj.primary_image
        return thumb(image.image if image else None)

    @admin.display(description="Stock", ordering="_stock")
    def stock_total(self, obj):
        return stock_badge(obj._stock or 0)

    @admin.action(description="Show selected products in store")
    def make_visible(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Hide selected products from store")
    def make_hidden(self, request, queryset):
        queryset.update(is_active=False)


class StockLevelFilter(admin.SimpleListFilter):
    title = "stock level"
    parameter_name = "level"

    def lookups(self, request, model_admin):
        return [("out", "Sold out"), ("low", "Low stock"), ("ok", "In stock")]

    def queryset(self, request, queryset):
        low = settings.LOW_STOCK_THRESHOLD
        if self.value() == "out":
            return queryset.filter(stock=0)
        if self.value() == "low":
            return queryset.filter(stock__gt=0, stock__lte=low)
        if self.value() == "ok":
            return queryset.filter(stock__gt=low)
        return queryset


@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    """Inventory screen: adjust stock by hand from the list view."""

    list_display = ("product", "name", "sku", "price_display", "status", "stock")
    list_editable = ("stock",)
    list_filter = (StockLevelFilter, "product__category")
    search_fields = ("product__name", "name", "sku")
    list_select_related = ("product",)
    ordering = ("stock", "product__name")
    autocomplete_fields = ("product",)
    list_per_page = 100

    @admin.display(description="Price")
    def price_display(self, obj):
        return money(obj.price)

    @admin.display(description="Status", ordering="stock")
    def status(self, obj):
        return stock_badge(obj.stock)


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "price", "is_active", "position")
    list_editable = ("price", "is_active", "position")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product_name", "variant_name", "sku", "unit_price", "quantity", "line_total_display")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Line total")
    def line_total_display(self, obj):
        return money(obj.line_total)


STATUS_COLORS = {
    Order.Status.PENDING: "#6b7280",
    Order.Status.PAID: "#15803d",
    Order.Status.CANCELLED: "#b91c1c",
    Order.Status.REFUNDED: "#7c3aed",
}


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "created_at",
        "full_name",
        "email",
        "total_display",
        "status_badge",
        "fulfillment_status",
        "tracking_number",
    )
    list_editable = ("fulfillment_status", "tracking_number")
    list_filter = ("status", "fulfillment_status", "shipping_name", "created_at")
    search_fields = ("number", "email", "full_name", "stripe_session_id", "stripe_payment_intent")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    actions = ["mark_packing", "mark_shipped", "mark_delivered"]
    readonly_fields = (
        "number",
        "status",
        "subtotal",
        "shipping_name",
        "shipping_cost",
        "total",
        "currency",
        "stripe_session_id",
        "stripe_payment_intent",
        "paid_at",
        "stock_applied",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        ("Order", {"fields": ("number", "status", "paid_at", "created_at", "updated_at")}),
        ("Fulfillment", {"fields": ("fulfillment_status", "tracking_number", "internal_notes")}),
        (
            "Customer & shipping address",
            {
                "fields": (
                    "full_name",
                    "email",
                    "phone",
                    "address_line1",
                    "address_line2",
                    ("city", "region"),
                    ("postal_code", "country"),
                )
            },
        ),
        ("Totals", {"fields": ("subtotal", "shipping_name", "shipping_cost", "total", "currency")}),
        (
            "Stripe",
            {
                "classes": ("collapse",),
                "fields": ("stripe_session_id", "stripe_payment_intent", "stock_applied"),
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    @admin.display(description="Total", ordering="total")
    def total_display(self, obj):
        return money(obj.total)

    @admin.display(description="Payment", ordering="status")
    def status_badge(self, obj):
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:999px;background:{};color:#fff;'
            'font-weight:600;font-size:11px">{}</span>',
            STATUS_COLORS.get(obj.status, "#6b7280"),
            obj.get_status_display(),
        )

    def _set_fulfillment(self, request, queryset, value):
        unpaid = queryset.exclude(status=Order.Status.PAID).count()
        updated = queryset.filter(status=Order.Status.PAID).update(fulfillment_status=value, updated_at=timezone.now())
        self.message_user(request, f"Updated {updated} order(s).", messages.SUCCESS)
        if unpaid:
            self.message_user(request, f"Skipped {unpaid} unpaid order(s).", messages.WARNING)

    @admin.action(description="Mark selected as packing")
    def mark_packing(self, request, queryset):
        self._set_fulfillment(request, queryset, Order.Fulfillment.PACKING)

    @admin.action(description="Mark selected as shipped")
    def mark_shipped(self, request, queryset):
        self._set_fulfillment(request, queryset, Order.Fulfillment.SHIPPED)

    @admin.action(description="Mark selected as delivered")
    def mark_delivered(self, request, queryset):
        self._set_fulfillment(request, queryset, Order.Fulfillment.DELIVERED)
