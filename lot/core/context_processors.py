import os

from django.conf import settings

from shop.cart import Cart
from shop.models import Category

from .models import SiteSettings


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
    }
    if context["store_enabled"]:
        context.update(
            cart_count=Cart(request).count,
            nav_categories=Category.objects.all(),
            stripe_publishable_key=settings.STRIPE_PUBLISHABLE_KEY,
        )
    return context
