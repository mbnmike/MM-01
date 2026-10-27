import math

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.text import Truncator, slugify

from .images import store_optimized, upload_to, validate_image_upload
from .rendering import plain_text, render_markdown

RESERVED_SLUGS = {"feed", "tag", "comment", "preview"}


def unique_slug(model, value, instance_pk=None, max_length=180):
    base = (slugify(value) or "post")[: max_length - 5].strip("-")
    slug, n = base, 2
    while model.objects.filter(slug=slug).exclude(pk=instance_pk).exists() or slug in RESERVED_SLUGS:
        slug = f"{base}-{n}"
        n += 1
    return slug


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("blog:tag", args=[self.slug])


class PostCategory(models.Model):
    """Shown before a post's title, e.g. "Feature: …", "Local: …", "Event: …"."""

    name = models.CharField(max_length=30, unique=True)
    position = models.PositiveIntegerField(default=0, help_text="Order in the post editor's dropdown.")

    class Meta:
        ordering = ["position", "name"]
        verbose_name = "post category"
        verbose_name_plural = "post categories"

    def __str__(self):
        return self.name


class PostQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Post.Status.PUBLISHED, published_at__lte=timezone.now())


class Post(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class SchemaType(models.TextChoices):
        BLOG_POSTING = "BlogPosting", "Blog post"
        ARTICLE = "Article", "Article"
        NEWS = "NewsArticle", "News"

    category = models.ForeignKey(
        PostCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="posts",
        help_text="Shown before the title, e.g. “Feature: Night meet”. Leave empty for just the title.",
    )
    title = models.CharField(max_length=160)
    slug = models.SlugField(
        unique=True, max_length=180, blank=True,
        help_text="The post's web address. Leave blank to generate it from the title.",
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    excerpt = models.CharField(
        max_length=300, blank=True, help_text="A sentence or two for post cards and social previews."
    )
    body = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to=upload_to, blank=True, validators=[validate_image_upload])
    cover_thumb = models.ImageField(upload_to=upload_to, blank=True, editable=False)
    cover_width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    cover_height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    cover_alt = models.CharField(
        "cover description", max_length=200, blank=True,
        help_text="Describe the photo for screen readers, e.g. “Silver E46 at sunset on PCH”.",
    )
    cover_caption = models.CharField(max_length=200, blank=True, help_text="Optional caption under the cover.")
    tags = models.ManyToManyField(Tag, blank=True, related_name="posts")
    meta_description = models.CharField(
        max_length=160, blank=True, help_text="For search results. Falls back to the excerpt."
    )
    schema_type = models.CharField(max_length=20, choices=SchemaType.choices, default=SchemaType.BLOG_POSTING)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(
        "publish date", null=True, blank=True,
        help_text="Set when you publish. Change it to backdate a post, or pick a future time to schedule it.",
    )
    updated_on = models.DateField(
        null=True, blank=True, help_text="Optional. Shown as “Updated …” when you revise a published post."
    )
    is_featured = models.BooleanField(
        "feature on blog home", default=False, help_text="The newest featured post leads the blog homepage."
    )
    allow_comments = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [models.Index(fields=["status", "published_at"], name="blog_post_status_pub_idx")]

    def __str__(self):
        return self.title

    @property
    def display_title(self):
        return f"{self.category.name}: {self.title}" if self.category_id else self.title

    def get_absolute_url(self):
        return reverse("blog:post", args=[self.slug])

    def clean(self):
        if self.slug in RESERVED_SLUGS:
            raise ValidationError({"slug": "That address is reserved. Pick a different slug."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Post, self.title, self.pk)
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        if self.cover_image and not self.cover_image._committed:
            self.cover_width, self.cover_height = store_optimized(
                self.cover_image, 2400, thumb_field=self.cover_thumb, thumb_px=960
            )
        elif not self.cover_image:
            self.cover_thumb = None
            self.cover_width = self.cover_height = None
        super().save(*args, **kwargs)

    @property
    def is_live(self):
        return self.status == self.Status.PUBLISHED and self.published_at and self.published_at <= timezone.now()

    @property
    def is_scheduled(self):
        return self.status == self.Status.PUBLISHED and self.published_at and self.published_at > timezone.now()

    @property
    def published_month(self):
        """First day of the publish month (site time zone), for grouping and archive links."""
        if not self.published_at:
            return None
        return timezone.localtime(self.published_at).date().replace(day=1)

    @property
    def card_image(self):
        return self.cover_thumb or self.cover_image

    @property
    def author_name(self):
        if not self.author:
            return f"{settings.BRAND['name']} Crew"
        return self.author.get_full_name() or self.author.get_username()

    @cached_property
    def rendered_body(self):
        return render_markdown(self.body)

    @property
    def summary(self):
        return self.meta_description or self.excerpt or Truncator(plain_text(self.body)).chars(155)

    @property
    def reading_minutes(self):
        return max(1, math.ceil(len(plain_text(self.body).split()) / 220))

    def schema(self, request, tags=None):
        modified = self.updated_on or (self.updated_at.date() if self.updated_at else None)
        data = {
            "@context": "https://schema.org",
            "@type": self.schema_type,
            "headline": self.title,
            "description": self.summary,
            "datePublished": self.published_at.isoformat() if self.published_at else None,
            "dateModified": modified.isoformat() if modified else None,
            "author": {"@type": "Person", "name": self.author_name},
            "publisher": {"@type": "Organization", "name": settings.BRAND["name"]},
            "mainEntityOfPage": request.build_absolute_uri(self.get_absolute_url()),
            "keywords": ", ".join(t.name for t in (tags if tags is not None else self.tags.all())),
        }
        if self.cover_image:
            data["image"] = request.build_absolute_uri(self.cover_image.url)
        return {k: v for k, v in data.items() if v is not None}


class MediaAsset(models.Model):
    image = models.ImageField(upload_to=upload_to, validators=[validate_image_upload])
    thumb = models.ImageField(upload_to=upload_to, blank=True, editable=False)
    alt = models.CharField(
        "description", max_length=200, blank=True, help_text="Used as the caption when inserted into a post."
    )
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "image"
        verbose_name_plural = "media library"

    def __str__(self):
        return self.alt or self.image.name.rsplit("/", 1)[-1]

    def save(self, *args, **kwargs):
        if self.image and not self.image._committed:
            self.width, self.height = store_optimized(self.image, 2000, thumb_field=self.thumb, thumb_px=480)
        super().save(*args, **kwargs)

    @property
    def markdown(self):
        alt = self.alt.replace("[", "(").replace("]", ")")
        return f"![{alt}]({self.image.url})"


class Comment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SPAM = "spam", "Spam"

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    name = models.CharField("display name", max_length=60, blank=True)
    email = models.EmailField(help_text="Private. Never shown on the site.")
    body = models.TextField("comment", max_length=3000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    moderated_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["post", "status", "created_at"], name="blog_comment_post_status_idx")]

    def __str__(self):
        return f"{self.display_name} on {self.post}"

    @property
    def display_name(self):
        return self.name or "Guest"


class BlogSettings(models.Model):
    title = models.CharField(max_length=80, default="Articles", help_text="Heading on the Articles page.")
    intro = models.CharField(
        max_length=300, default="Notes, photos, and progress from the garage.", blank=True,
        help_text="Short line under the heading. Also used for the RSS feed.",
    )
    posts_per_page = models.PositiveSmallIntegerField(
        default=9, validators=[MinValueValidator(3), MaxValueValidator(48)]
    )
    comments_enabled = models.BooleanField(default=True, help_text="Turn off to close comments on every post.")
    require_approval = models.BooleanField(
        default=True, help_text="Hold new comments until you approve them."
    )
    auto_approve_known = models.BooleanField(
        "auto-approve returning commenters", default=True,
        help_text="Skip the queue for an email address that already has an approved comment.",
    )
    notify_email = models.EmailField(
        blank=True, help_text="Optional. Get an email when someone comments (needs email sending configured)."
    )
    blocked_words = models.TextField(
        blank=True, help_text="One word or phrase per line. Comments containing them go straight to spam."
    )

    class Meta:
        verbose_name = "articles page settings"
        verbose_name_plural = "articles page settings"

    def __str__(self):
        return "Articles page settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def blocked_word_list(self):
        return [w.strip().lower() for w in self.blocked_words.splitlines() if w.strip()]


class PostAutosave(models.Model):
    """Server-side backup of what's in the editor, so a crash or closed tab never loses writing."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True, related_name="autosaves")
    title = models.CharField(max_length=160, blank=True)
    excerpt = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True)
    saved_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="blog_autosave_user_post")]
