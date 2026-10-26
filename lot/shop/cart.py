from dataclasses import dataclass
from decimal import Decimal

from .models import Variant

CART_SESSION_KEY = "cart"
MAX_PER_LINE = 20


@dataclass
class CartLine:
    variant: Variant
    quantity: int

    @property
    def product(self):
        return self.variant.product

    @property
    def unit_price(self):
        return self.variant.price

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class Cart:
    """Session cart stored as {variant_id: quantity}."""

    def __init__(self, request):
        self.session = request.session
        self.data = {str(k): int(v) for k, v in self.session.get(CART_SESSION_KEY, {}).items()}
        self._lines = None
        self.adjusted = False

    def save(self):
        self.session[CART_SESSION_KEY] = self.data
        self.session.modified = True
        self._lines = None

    def add(self, variant, quantity=1):
        """Add up to the available stock. Returns the quantity actually added."""
        current = self.data.get(str(variant.pk), 0)
        target = min(current + max(quantity, 0), variant.stock, MAX_PER_LINE)
        if target <= 0:
            return 0
        self.data[str(variant.pk)] = target
        self.save()
        return target - current

    def set(self, variant, quantity):
        quantity = min(max(quantity, 0), variant.stock, MAX_PER_LINE)
        if quantity == 0:
            self.data.pop(str(variant.pk), None)
        else:
            self.data[str(variant.pk)] = quantity
        self.save()
        return quantity

    def remove(self, variant_id):
        self.data.pop(str(variant_id), None)
        self.save()

    def clear(self):
        self.data = {}
        self.save()

    @property
    def count(self):
        return sum(self.data.values())

    def lines(self):
        """Cart lines with quantities clamped to live stock; drops missing or hidden products."""
        if self._lines is not None:
            return self._lines
        variants = {
            str(v.pk): v
            for v in Variant.objects.filter(pk__in=self.data.keys(), product__is_active=True)
            .select_related("product", "product__category")
            .prefetch_related("product__images")
        }
        lines, changed = [], False
        for key, qty in list(self.data.items()):
            variant = variants.get(key)
            allowed = min(qty, variant.stock) if variant else 0
            if allowed != qty:
                changed = True
                if allowed:
                    self.data[key] = allowed
                else:
                    self.data.pop(key)
            if variant and allowed:
                lines.append(CartLine(variant, allowed))
        if changed:
            self.adjusted = True
            self.save()
        self._lines = lines
        return lines

    @property
    def subtotal(self):
        return sum((line.line_total for line in self.lines()), Decimal("0"))

    def __len__(self):
        return len(self.lines())
