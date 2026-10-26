import logging

from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest
from django.utils import timezone

from .models import Order, Variant

logger = logging.getLogger("shop")


@transaction.atomic
def mark_order_paid(order_id, payment_intent=""):
    """Mark an order paid and decrement inventory exactly once. Safe to call repeatedly."""
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == Order.Status.PAID and order.stock_applied:
        return order, False

    order.status = Order.Status.PAID
    order.paid_at = order.paid_at or timezone.now()
    if payment_intent:
        order.stripe_payment_intent = payment_intent

    if not order.stock_applied:
        for item in order.items.all():
            if item.variant_id:
                Variant.objects.filter(pk=item.variant_id).update(stock=Greatest(F("stock") - item.quantity, 0))
        order.stock_applied = True

    order.save()
    logger.info("Order %s paid; inventory updated", order.number)
    return order, True


@transaction.atomic
def mark_order_cancelled(order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == Order.Status.PENDING:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        return True
    return False
