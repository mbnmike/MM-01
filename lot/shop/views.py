import json
import logging
from decimal import ROUND_HALF_UP, Decimal

import stripe
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import Subscriber
from core.utils import json_ld

from .cart import Cart
from .forms import CheckoutForm
from .models import Category, Order, OrderItem, Product, ShippingMethod, Variant
from .services import mark_order_cancelled, mark_order_paid

logger = logging.getLogger("shop")

SORTS = {
    "new": ("Newest", ["-created_at"]),
    "price-asc": ("Price: low to high", ["price"]),
    "price-desc": ("Price: high to low", ["-price"]),
}


def to_cents(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# --- Catalog -----------------------------------------------------------------


def collection(request, category_slug=None):
    category = get_object_or_404(Category, slug=category_slug) if category_slug else None
    products = Product.objects.for_listing()
    if category:
        products = products.filter(category=category)
    sort = request.GET.get("sort", "new")
    if sort not in SORTS:
        sort = "new"
    products = list(products.order_by(*SORTS[sort][1]))
    rows = []
    if not category:
        by_category = {}
        for product in products:
            by_category.setdefault(product.category_id, []).append(product)
        rows = [(c, by_category[c.pk]) for c in Category.objects.all() if c.pk in by_category]
    return render(request, "shop/collection.html", {"category": category, "products": products, "rows": rows})


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.for_listing(), slug=slug)
    variants = list(product.variants.all())
    selected = next((v for v in variants if v.in_stock), variants[0] if variants else None)
    related = (
        Product.objects.for_listing().filter(category=product.category).exclude(pk=product.pk).order_by("?")[:4]
    )
    image = product.primary_image
    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "description": product.tagline or product.description[:200],
        "sku": selected.sku if selected else "",
        "brand": {"@type": "Brand", "name": settings.BRAND["name"]},
        "image": [request.build_absolute_uri(img.image.url) for img in product.gallery],
        "offers": {
            "@type": "Offer",
            "url": request.build_absolute_uri(product.get_absolute_url()),
            "priceCurrency": settings.STORE_CURRENCY.upper(),
            "price": str(product.price),
            "availability": "https://schema.org/InStock" if product.in_stock else "https://schema.org/OutOfStock",
        },
    }
    return render(
        request,
        "shop/product_detail.html",
        {
            "product": product,
            "variants": variants,
            "selected": selected,
            "related": related,
            "og_image": request.build_absolute_uri(image.image.url) if image else "",
            "schema_json": json_ld(schema),
        },
    )


# --- Cart --------------------------------------------------------------------


def _quantity(value, default=1):
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _safe_next(request, fallback):
    nxt = request.POST.get("next", "")
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else fallback


def cart_detail(request):
    cart = Cart(request)
    lines = cart.lines()
    if cart.adjusted:
        messages.info(request, "Some quantities changed to match what's left in stock.")
    return render(request, "shop/cart.html", {"cart": cart, "lines": lines})


@require_POST
def cart_add(request):
    variant = get_object_or_404(
        Variant.objects.select_related("product"), pk=request.POST.get("variant"), product__is_active=True
    )
    qty = _quantity(request.POST.get("quantity"), 1) or 1
    cart = Cart(request)
    added = cart.add(variant, qty)
    if added == 0:
        if variant.stock == 0:
            messages.error(request, f"{variant} is sold out.")
        else:
            messages.warning(request, f"You already have all {variant.stock} available in your cart.")
    elif added < qty:
        messages.warning(request, f"Only {added} more available — added what we had.")
    else:
        messages.success(request, f"Added {variant.product.name} ({variant.name}) to your cart.")
    return redirect(_safe_next(request, reverse("shop:cart")))


@require_POST
def cart_update(request, variant_id):
    variant = get_object_or_404(Variant, pk=variant_id)
    cart = Cart(request)
    requested = _quantity(request.POST.get("quantity"), 0)
    applied = cart.set(variant, requested)
    if applied < requested:
        messages.warning(request, f"Only {variant.stock} of {variant} in stock.")
    return redirect("shop:cart")


@require_POST
def cart_remove(request, variant_id):
    Cart(request).remove(variant_id)
    messages.info(request, "Removed from cart.")
    return redirect("shop:cart")


# --- Checkout ----------------------------------------------------------------


def checkout(request):
    cart = Cart(request)
    lines = cart.lines()
    if not lines:
        messages.info(request, "Your cart is empty.")
        return redirect("shop:cart")

    stripe_ready = bool(settings.STRIPE_SECRET_KEY)
    form = CheckoutForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        if cart.adjusted:
            messages.warning(request, "Stock changed while you were shopping. Please review your cart.")
            return redirect("shop:cart")
        if form.cleaned_data["subscribe"]:
            Subscriber.add(form.cleaned_data["email"], Subscriber.Source.CHECKOUT)
            request.session["subscribed"] = True
        if not stripe_ready:
            messages.error(request, "Payments aren't configured yet. Add STRIPE_SECRET_KEY to your .env.")
        else:
            response = _start_stripe_checkout(request, cart, lines, form.cleaned_data)
            if response:
                return response

    shipping_methods = ShippingMethod.objects.filter(is_active=True)
    return render(
        request,
        "shop/checkout.html",
        {
            "form": form,
            "lines": lines,
            "cart": cart,
            "stripe_ready": stripe_ready,
            "shipping_methods": shipping_methods,
        },
    )


def _start_stripe_checkout(request, cart, lines, data):
    method = data["shipping_method"]
    currency = settings.STORE_CURRENCY
    with transaction.atomic():
        order = Order.objects.create(
            email=data["email"],
            full_name=data["full_name"],
            phone=data["phone"],
            address_line1=data["address_line1"],
            address_line2=data["address_line2"],
            city=data["city"],
            region=data["region"],
            postal_code=data["postal_code"],
            country=data["country"],
            shipping_method=method,
            shipping_name=method.name,
            shipping_cost=method.price,
            subtotal=cart.subtotal,
            total=cart.subtotal + method.price,
            currency=currency,
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    variant=line.variant,
                    product_name=line.product.name,
                    variant_name=line.variant.name,
                    sku=line.variant.sku,
                    unit_price=line.unit_price,
                    quantity=line.quantity,
                )
                for line in lines
            ]
        )

    success_url = request.build_absolute_uri(reverse("shop:checkout_success")) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = request.build_absolute_uri(reverse("shop:checkout_cancel")) + f"?order={order.number}"
    metadata = {"order_id": str(order.pk), "order_number": order.number}

    try:
        session = stripe.checkout.Session.create(
            api_key=settings.STRIPE_SECRET_KEY,
            mode="payment",
            customer_email=order.email,
            client_reference_id=order.number,
            line_items=[
                {
                    "quantity": line.quantity,
                    "price_data": {
                        "currency": currency,
                        "unit_amount": to_cents(line.unit_price),
                        "product_data": {"name": f"{line.product.name} — {line.variant.name}"},
                    },
                }
                for line in lines
            ],
            shipping_options=[
                {
                    "shipping_rate_data": {
                        "type": "fixed_amount",
                        "display_name": method.name,
                        "fixed_amount": {"amount": to_cents(method.price), "currency": currency},
                    }
                }
            ],
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except stripe.StripeError as exc:
        logger.exception("Stripe Checkout Session failed for order %s", order.number)
        order.status = Order.Status.CANCELLED
        order.internal_notes = f"Stripe error: {getattr(exc, 'user_message', None) or exc}"
        order.save(update_fields=["status", "internal_notes", "updated_at"])
        messages.error(request, "We couldn't reach the payment provider. Please try again in a moment.")
        return None

    order.stripe_session_id = session.id
    order.save(update_fields=["stripe_session_id", "updated_at"])
    request.session["last_order"] = order.number
    return redirect(session.url)


def checkout_success(request):
    session_id = request.GET.get("session_id", "")
    if not session_id:
        raise Http404
    order = get_object_or_404(Order.objects.prefetch_related("items"), stripe_session_id=session_id)
    if request.session.get("last_order") == order.number:
        Cart(request).clear()
    return render(request, "shop/success.html", {"order": order})


def checkout_cancel(request):
    messages.info(request, "Checkout cancelled — your cart is still here.")
    return redirect("shop:cart")


# --- Stripe webhook ------------------------------------------------------------


def _order_for_session(session_obj):
    order_id = (session_obj.get("metadata") or {}).get("order_id")
    if not order_id:
        return None
    order = Order.objects.filter(pk=order_id).first()
    if order and order.stripe_session_id and order.stripe_session_id != session_obj.get("id"):
        logger.warning("Session id mismatch for order %s", order.number)
        return None
    return order


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET is not set; rejecting webhook.")
        return HttpResponseBadRequest("Webhook secret not configured")

    payload = request.body
    signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponseBadRequest("Invalid signature")

    event = json.loads(payload)
    event_type = event.get("type", "")
    session_obj = event.get("data", {}).get("object", {})

    if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        if session_obj.get("payment_status") == "paid":
            order = _order_for_session(session_obj)
            if order:
                expected = to_cents(order.total)
                if session_obj.get("amount_total") not in (None, expected):
                    logger.warning(
                        "Order %s amount mismatch: stripe=%s expected=%s",
                        order.number,
                        session_obj.get("amount_total"),
                        expected,
                    )
                mark_order_paid(order.pk, session_obj.get("payment_intent") or "")
    elif event_type in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        order = _order_for_session(session_obj)
        if order:
            mark_order_cancelled(order.pk)

    return HttpResponse(status=200)
