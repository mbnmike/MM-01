import os

from django.conf import settings

from shop.cart import Cart
from shop.models import Category

from .middleware import is_store_page
from .models import SiteSettings, Subscriber


def _asset_version():
    """Changes whenever the built CSS/JS changes, so browsers never keep a stale copy."""
    stamps = []
    for rel in ("css/app.css", "js/app.js", "css/admin.css", "css/editor.css", "js/editor.js", "img/hero.jpg"):
        try:
            stamps.append(int(os.path.getmtime(settings.BASE_DIR / "static" / rel)))
        except OSError:
            pass
    return max(stamps, default=0)


def storefront(request):
    if request.path.startswith(f"/{settings.ADMIN_URL}") and not getattr(request, "storefront_page", False):
        return {"brand": settings.BRAND, "asset_version": _asset_version()}
    context = {
        "brand": settings.BRAND,
        "asset_version": _asset_version(),
        "store_enabled": SiteSettings.load().store_enabled,
        "in_store": request.resolver_match is not None and is_store_page(request.resolver_match),
        "subscribed": request.session.get("subscribed", False),
    }
    if not context["in_store"]:
        context["subscriber_count"] = Subscriber.objects.filter(is_active=True).count()
    if context["store_enabled"] and context["in_store"]:
        context.update(
            cart_count=Cart(request).count,
            nav_categories=Category.objects.all(),
            stripe_publishable_key=settings.STRIPE_PUBLISHABLE_KEY,
        )
    return context
