from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def money(value):
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        return value
    return f"{settings.CURRENCY_SYMBOL}{amount:,.2f}"


@register.inclusion_tag("partials/field.html")
def field(bound_field, css=""):
    return {"field": bound_field, "css": css}
