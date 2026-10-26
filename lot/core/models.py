from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class SiteSettings(models.Model):
    store_enabled = models.BooleanField(
        "store enabled", default=True,
        help_text="Untick to hide the shop: products, cart, checkout, customer accounts, and FAQ disappear "
                  "and the site becomes a home page plus the journal. Products and orders are kept, "
                  "and you can still open the shop pages while logged in as staff.",
    )

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class FeaturedProduct(models.Model):
    product = models.OneToOneField("shop.Product", on_delete=models.CASCADE, related_name="feature")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "homepage featured product"
        verbose_name_plural = "homepage featured products"

    def __str__(self):
        return str(self.product)


class Review(models.Model):
    author_name = models.CharField(max_length=80)
    location = models.CharField(max_length=80, blank=True)
    body = models.CharField(max_length=240)
    rating = models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(5)])
    is_published = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "homepage review"

    def __str__(self):
        return f"{self.author_name}: {self.body[:40]}"

    @property
    def stars(self):
        return "★" * self.rating + "☆" * (5 - self.rating)


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    order_number = models.CharField(max_length=20, blank=True)
    message = models.TextField()
    handled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}>"
