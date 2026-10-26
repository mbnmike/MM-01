from django import template
from django.conf import settings

from blog.models import Comment, Post
from core.models import ContactMessage, SiteSettings
from shop.models import Order, Variant

register = template.Library()


@register.inclusion_tag("admin/_dashboard.html")
def store_dashboard():
    return {
        "site_settings": SiteSettings.load(),
        "to_fulfill": Order.objects.filter(
            status=Order.Status.PAID,
            fulfillment_status__in=[Order.Fulfillment.UNFULFILLED, Order.Fulfillment.PACKING],
        ).count(),
        "awaiting_payment": Order.objects.filter(status=Order.Status.PENDING).count(),
        "low_stock": Variant.objects.filter(stock__lte=settings.LOW_STOCK_THRESHOLD)
        .select_related("product")
        .order_by("stock", "product__name")[:8],
        "low_threshold": settings.LOW_STOCK_THRESHOLD,
        "open_messages": ContactMessage.objects.filter(handled=False).count(),
        "pending_comments": Comment.objects.filter(status=Comment.Status.PENDING).count(),
        "draft_posts": Post.objects.filter(status=Post.Status.DRAFT).count(),
    }
