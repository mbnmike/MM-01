import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

ORDER_NUMBER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class Category(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    blurb = models.CharField(max_length=200, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:collection", args=[self.slug])


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def for_listing(self):
        return self.active().select_related("category").prefetch_related("images", "variants")


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    tagline = models.CharField(max_length=160, blank=True, help_text="One short line under the title.")
    description = models.TextField(blank=True)
    details = models.TextField(blank=True, help_text="Bullet points, one per line.")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Optional original price to show a sale."
    )
    is_active = models.BooleanField("visible in store", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:product", args=[self.slug])

    @property
    def gallery(self):
        return list(self.images.all())

    @property
    def primary_image(self):
        images = self.gallery
        return images[0] if images else None

    @property
    def secondary_image(self):
        images = self.gallery
        return images[1] if len(images) > 1 else None

    @property
    def total_stock(self):
        return sum(v.stock for v in self.variants.all())

    @property
    def in_stock(self):
        return self.total_stock > 0

    @property
    def on_sale(self):
        return bool(self.compare_at_price and self.compare_at_price > self.price)

    @property
    def detail_lines(self):
        return [line.strip("-• ").strip() for line in self.details.splitlines() if line.strip()]


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    alt = models.CharField(max_length=160, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.alt or f"Image for {self.product}"


class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=60, help_text="Size, color, or option shown to customers, e.g. M or Matte Black.")
    sku = models.CharField(max_length=50, unique=True, blank=True)
    price_override = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Leave blank to use the product price."
    )
    stock = models.PositiveIntegerField(default=0)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "variant / inventory"
        verbose_name_plural = "inventory"

    def __str__(self):
        return f"{self.product.name} / {self.name}"

    def save(self, *args, **kwargs):
        if not self.sku:
            base = slugify(f"{self.product.slug}-{self.name}").upper()[:40]
            sku, n = base, 1
            while Variant.objects.filter(sku=sku).exclude(pk=self.pk).exists():
                n += 1
                sku = f"{base}-{n}"
            self.sku = sku
        super().save(*args, **kwargs)

    @property
    def price(self):
        return self.price_override if self.price_override is not None else self.product.price

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def low_stock(self):
        return 0 < self.stock <= settings.LOW_STOCK_THRESHOLD


class ShippingMethod(models.Model):
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=160, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "price"]

    def __str__(self):
        return f"{self.name} ({self.price})"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class Fulfillment(models.TextChoices):
        UNFULFILLED = "unfulfilled", "Unfulfilled"
        PACKING = "packing", "Packing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"

    number = models.CharField(max_length=12, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    email = models.EmailField()
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=40, blank=True)
    address_line1 = models.CharField("address", max_length=200)
    address_line2 = models.CharField("apt / suite", max_length=200, blank=True)
    city = models.CharField(max_length=100)
    region = models.CharField("state / region", max_length=100, blank=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=2, default="US")

    shipping_method = models.ForeignKey(ShippingMethod, on_delete=models.SET_NULL, null=True, blank=True)
    shipping_name = models.CharField(max_length=80)
    shipping_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="usd")

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    fulfillment_status = models.CharField(
        "fulfillment", max_length=12, choices=Fulfillment.choices, default=Fulfillment.UNFULFILLED, db_index=True
    )
    tracking_number = models.CharField(max_length=80, blank=True)
    internal_notes = models.TextField(blank=True)

    stripe_session_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_payment_intent = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    stock_applied = models.BooleanField(
        default=False, editable=False, help_text="Inventory has been decremented for this order."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.number}"

    def save(self, *args, **kwargs):
        if not self.number:
            while True:
                candidate = "".join(secrets.choice(ORDER_NUMBER_ALPHABET) for _ in range(8))
                if not Order.objects.filter(number=candidate).exists():
                    self.number = candidate
                    break
        super().save(*args, **kwargs)

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(Variant, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    product_name = models.CharField(max_length=120)
    variant_name = models.CharField(max_length=60)
    sku = models.CharField(max_length=50, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} × {self.product_name} / {self.variant_name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity
