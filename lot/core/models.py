from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse

from blog.images import validate_image_upload

VIDEO_MAX_MB = 60


def validate_video_size(file):
    if file.size and file.size > VIDEO_MAX_MB * 1024 * 1024:
        raise ValidationError(f"Videos must be under {VIDEO_MAX_MB} MB. Shorten or compress it first.")


class SiteSettings(models.Model):
    store_enabled = models.BooleanField(
        "store enabled", default=True,
        help_text="Untick to hide the shop: products, cart, checkout, and FAQ disappear "
                  "and the site becomes a home page plus the journal. Products and orders are kept, "
                  "and you can still open the shop pages while logged in as staff.",
    )
    hero_video = models.FileField(
        "home video", upload_to="site/", blank=True,
        validators=[FileExtensionValidator(["mp4", "webm"]), validate_video_size],
        help_text=f"A short muted loop at the top of the home page. MP4 (H.264) works everywhere. "
                  f"Aim for 10–20 seconds at 1920×1080 or 1280×720, ideally under 15 MB "
                  f"(limit {VIDEO_MAX_MB} MB). Leave empty to show the still image instead.",
    )
    hero_poster = models.ImageField(
        "video still", upload_to="site/", blank=True, validators=[validate_image_upload],
        help_text="Shown while the video loads, and instead of it for visitors who turn off motion. "
                  "A frame from the video works best.",
    )
    hero_logo = models.ImageField(
        "logo over the video", upload_to="site/", blank=True, validators=[validate_image_upload],
        help_text="A white logo on a transparent background (PNG or WebP), about 1200 px wide. "
                  "Leave empty to show the site name as text.",
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


class Subscriber(models.Model):
    class Source(models.TextChoices):
        FOOTER = "footer", "Footer form"
        POPUP = "popup", "Subscribe button"
        CHECKOUT = "checkout", "Checkout"

    email = models.EmailField(unique=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.FOOTER)
    is_active = models.BooleanField("subscribed", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    @classmethod
    def add(cls, email, source):
        email = email.strip().lower()
        sub, created = cls.objects.get_or_create(email=email, defaults={"source": source})
        if not created and not sub.is_active:
            sub.is_active, sub.unsubscribed_at = True, None
            sub.save(update_fields=["is_active", "unsubscribed_at"])
        return sub

    def unsubscribe_token(self):
        return signing.dumps(self.email, salt="unsubscribe")

    def get_unsubscribe_url(self):
        return reverse("core:unsubscribe", args=[self.unsubscribe_token()])


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
