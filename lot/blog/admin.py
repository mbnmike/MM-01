from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import path, reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html

from .forms import PostAdminForm
from .models import BlogSettings, Comment, MediaAsset, Post, PostAutosave, PostCategory, Tag
from .rendering import PROSE_CLASSES, render_markdown
from .views import post_context


def _badge(label, tone):
    colors = {
        "green": ("#2c570e", "#fff"), "black": ("#0a0a0a", "#fff"),
        "amber": ("#fde68a", "#713f12"), "grey": ("#e5e5e5", "#404040"), "red": ("#fee2e2", "#991b1b"),
    }
    bg, fg = colors[tone]
    return format_html(
        '<span style="background:{};color:{};padding:3px 8px;font-size:10px;font-weight:700;'
        'letter-spacing:.12em;text-transform:uppercase;white-space:nowrap">{}</span>', bg, fg, label,
    )


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "post_count")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count("posts"))

    @admin.display(description="Posts", ordering="n")
    def post_count(self, obj):
        return obj.n


@admin.register(PostCategory)
class PostCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "position", "post_count")
    list_editable = ("position",)
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count("posts"))

    @admin.display(description="Posts", ordering="n")
    def post_count(self, obj):
        return obj.n


class StatusFilter(admin.SimpleListFilter):
    title = "status"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return [("draft", "Draft"), ("live", "Published"), ("scheduled", "Scheduled")]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "draft":
            return queryset.filter(status=Post.Status.DRAFT)
        if self.value() == "live":
            return queryset.filter(status=Post.Status.PUBLISHED, published_at__lte=now)
        if self.value() == "scheduled":
            return queryset.filter(status=Post.Status.PUBLISHED, published_at__gt=now)
        return queryset


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    form = PostAdminForm
    change_form_template = "admin/blog/post/editor.html"
    list_display = ("title", "category", "state", "published_at", "updated_at", "comment_count", "links")
    list_display_links = ("title",)
    list_filter = (StatusFilter, "category", "published_at", "tags", "is_featured")
    search_fields = ("title", "excerpt", "body", "slug")
    date_hierarchy = "published_at"
    ordering = ("-updated_at",)
    autocomplete_fields = ("tags",)
    actions = ["publish", "unpublish"]
    list_per_page = 30
    fieldsets = (
        (None, {"fields": ("category", "title", "slug", "excerpt", "body")}),
        ("Publishing", {"fields": ("published_at", "updated_on", "is_featured", "allow_comments", "author")}),
        ("Cover", {"fields": ("cover_image", "cover_alt", "cover_caption")}),
        ("Tags", {"fields": ("tags",)}),
        ("SEO", {"fields": ("meta_description", "schema_type")}),
    )

    # ----- list -----

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related("author", "category")
            .annotate(
                n_comments=Count("comments", distinct=True),
                n_pending=Count("comments", filter=Q(comments__status=Comment.Status.PENDING), distinct=True),
            )
        )

    @admin.display(description="Status", ordering="status")
    def state(self, obj):
        if obj.is_scheduled:
            return _badge("Scheduled", "amber")
        if obj.is_live:
            return _badge("Published", "green")
        return _badge("Draft", "grey")

    @admin.display(description="Comments", ordering="n_comments")
    def comment_count(self, obj):
        if not obj.n_comments:
            return "—"
        url = reverse("admin:blog_comment_changelist") + f"?post__id__exact={obj.pk}"
        if obj.n_pending:
            return format_html('<a href="{}">{} <strong style="color:#b45309">({} new)</strong></a>',
                               url, obj.n_comments, obj.n_pending)
        return format_html('<a href="{}">{}</a>', url, obj.n_comments)

    @admin.display(description="")
    def links(self, obj):
        preview = reverse("admin:blog_post_preview", args=[obj.pk])
        if obj.is_live:
            return format_html('<a href="{}" target="_blank">View ↗</a>', obj.get_absolute_url())
        return format_html('<a href="{}" target="_blank">Preview ↗</a>', preview)

    @admin.action(description="Publish selected posts")
    def publish(self, request, queryset):
        count = 0
        for post in queryset.filter(status=Post.Status.DRAFT):
            post.status = Post.Status.PUBLISHED
            post.save()
            count += 1
        self.message_user(request, f"Published {count} post(s).", messages.SUCCESS)

    @admin.action(description="Unpublish selected posts (back to draft)")
    def unpublish(self, request, queryset):
        count = queryset.update(status=Post.Status.DRAFT)
        self.message_user(request, f"Moved {count} post(s) to drafts.", messages.SUCCESS)

    # ----- editor -----

    def get_changeform_initial_data(self, request):
        return {"author": request.user.pk}

    def _autosave_for(self, request, obj):
        autosaves = PostAutosave.objects.filter(user=request.user)
        autosave = autosaves.filter(post=obj).first() if obj else autosaves.filter(post__isnull=True).first()
        if autosave and obj and autosave.saved_at <= obj.updated_at:
            return None
        return autosave

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        autosave = self._autosave_for(request, obj)
        context["editor_config"] = {
            "postId": obj.pk if obj else None,
            "renderUrl": reverse("admin:blog_post_render"),
            "autosaveUrl": reverse("admin:blog_post_autosave"),
            "uploadUrl": reverse("admin:blog_post_upload"),
            "mediaUrl": reverse("admin:blog_post_media"),
            "previewCss": [
                static("css/app.css"),
                "https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:wght@400;500;600;700"
                "&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap",
            ],
            "proseClasses": PROSE_CLASSES,
            "autosave": {
                "title": autosave.title, "excerpt": autosave.excerpt, "body": autosave.body,
                "savedAt": date_format(timezone.localtime(autosave.saved_at), "M j, g:i A"),
            } if autosave else None,
        }
        context["post_obj"] = obj
        return super().render_change_form(request, context, add, change, form_url, obj)

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        if "_publish" in request.POST:
            obj.status = Post.Status.PUBLISHED
            if not obj.published_at:
                obj.published_at = timezone.now()
        elif "_unpublish" in request.POST:
            obj.status = Post.Status.DRAFT
        super().save_model(request, obj, form, change)
        stale = Q(post=obj) if change else Q(post=obj) | Q(post__isnull=True)
        PostAutosave.objects.filter(stale, user=request.user).delete()

    def _publish_response(self, request, obj):
        if "_publish" in request.POST:
            if obj.is_scheduled:
                when = date_format(timezone.localtime(obj.published_at), "M j, Y, g:i A")
                self.message_user(request, f"Scheduled — “{obj}” goes live {when}.", messages.SUCCESS)
            else:
                self.message_user(request, format_html(
                    'Published — “{}” is live. <a href="{}" target="_blank">View post ↗</a>',
                    obj, obj.get_absolute_url()), messages.SUCCESS)
        else:
            self.message_user(request, f"“{obj}” is now a draft and hidden from the public.", messages.SUCCESS)
        return HttpResponseRedirect(reverse("admin:blog_post_change", args=[obj.pk]))

    def response_add(self, request, obj, post_url_continue=None):
        if "_publish" in request.POST or "_unpublish" in request.POST:
            return self._publish_response(request, obj)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_publish" in request.POST or "_unpublish" in request.POST:
            return self._publish_response(request, obj)
        return super().response_change(request, obj)

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path("editor/render/", wrap(self.render_view), name="blog_post_render"),
            path("editor/autosave/", wrap(self.autosave_view), name="blog_post_autosave"),
            path("editor/upload/", wrap(self.upload_view), name="blog_post_upload"),
            path("editor/media/", wrap(self.media_view), name="blog_post_media"),
            path("preview/", wrap(self.preview_view), name="blog_post_preview_new"),
            path("<int:object_id>/preview/", wrap(self.preview_view), name="blog_post_preview"),
        ] + super().get_urls()

    def _require_edit(self, request, obj=None):
        allowed = self.has_change_permission(request, obj) if obj else (
            self.has_add_permission(request) or self.has_change_permission(request)
        )
        if not allowed:
            raise PermissionDenied

    @staticmethod
    def _error(message, status=400):
        return JsonResponse({"error": message}, status=status)

    def render_view(self, request):
        if request.method != "POST":
            return self._error("POST required.", 405)
        self._require_edit(request)
        return JsonResponse({"html": str(render_markdown(request.POST.get("body", "")))})

    def autosave_view(self, request):
        if request.method != "POST":
            return self._error("POST required.", 405)
        post = None
        if request.POST.get("post_id"):
            post = get_object_or_404(Post, pk=request.POST["post_id"])
        self._require_edit(request, post)
        lookup = {"user": request.user, "post": post}
        if request.POST.get("discard"):
            PostAutosave.objects.filter(**lookup).delete()
            return JsonResponse({"ok": True})
        values = {
            "title": request.POST.get("title", "")[:160],
            "excerpt": request.POST.get("excerpt", "")[:300],
            "body": request.POST.get("body", ""),
        }
        autosave = PostAutosave.objects.filter(**lookup).first()
        if autosave:
            for key, value in values.items():
                setattr(autosave, key, value)
            autosave.save()
        else:
            autosave = PostAutosave.objects.create(**lookup, **values)
        return JsonResponse({"ok": True, "savedAt": date_format(timezone.localtime(autosave.saved_at), "g:i A")})

    def upload_view(self, request):
        if request.method != "POST":
            return self._error("POST required.", 405)
        self._require_edit(request)
        if not request.user.has_perm("blog.add_mediaasset"):
            raise PermissionDenied
        upload = request.FILES.get("image")
        if not upload:
            return self._error("Choose an image to upload.")
        asset = MediaAsset(image=upload, alt=request.POST.get("alt", "")[:200], uploaded_by=request.user)
        try:
            asset.full_clean()
            asset.save()
        except ValidationError as exc:
            return self._error(" ".join(exc.messages))
        return JsonResponse(self._asset_json(asset))

    @staticmethod
    def _asset_json(asset):
        return {
            "id": asset.pk, "url": asset.image.url, "thumb": (asset.thumb or asset.image).url,
            "alt": asset.alt, "width": asset.width, "height": asset.height,
        }

    def media_view(self, request):
        self._require_edit(request)
        assets = MediaAsset.objects.all()[:60]
        return JsonResponse({"items": [self._asset_json(a) for a in assets]})

    def preview_view(self, request, object_id=None):
        """GET: the saved post as visitors would see it. POST: the editor's unsaved form, without saving."""
        obj = get_object_or_404(Post, pk=object_id) if object_id else None
        self._require_edit(request, obj)
        extra = {}
        if request.method == "POST":
            Form = self.get_form(request, obj, change=obj is not None)
            form = Form(request.POST, request.FILES, instance=obj)
            if not form.is_valid():
                return render(request, "admin/blog/post/preview_error.html", {"form": form}, status=400)
            post = form.save(commit=False)
            if post.cover_image and not post.cover_image._committed:
                # A just-picked cover isn't stored until you save; preview with the saved one.
                post.cover_image = Post.objects.get(pk=obj.pk).cover_image if obj else None
            post.slug = post.slug or "preview"
            extra = {"tags": list(form.cleaned_data.get("tags") or [])}
        elif obj is None:
            raise Http404
        else:
            post = obj
        request.storefront_page = True
        context = post_context(request, post, preview=True, **extra)
        context["edit_url"] = reverse("admin:blog_post_change", args=[post.pk]) if post.pk else None
        response = render(request, "blog/post_detail.html", context)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("thumbnail", "__str__", "dimensions", "created_at", "usage")
    search_fields = ("alt", "image")
    readonly_fields = ("preview", "markdown_snippet", "dimensions", "uploaded_by", "created_at", "usage")
    fields = ("image", "alt", "preview", "markdown_snippet", "dimensions", "uploaded_by", "created_at", "usage")
    list_per_page = 40

    def save_model(self, request, obj, form, change):
        if not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="")
    def thumbnail(self, obj):
        img = obj.thumb or obj.image
        return format_html('<img src="{}" alt="" style="width:96px;height:64px;object-fit:cover">', img.url) if img else ""

    @admin.display(description="Preview")
    def preview(self, obj):
        if not obj.image:
            return "—"
        return format_html('<img src="{}" alt="" style="max-width:480px;max-height:320px">', obj.image.url)

    @admin.display(description="Paste into a post")
    def markdown_snippet(self, obj):
        if not obj.image:
            return "—"
        return format_html('<code style="user-select:all;padding:6px 8px;background:var(--darkened-bg)">{}</code>',
                           obj.markdown)

    @admin.display(description="Size")
    def dimensions(self, obj):
        return f"{obj.width} × {obj.height}px" if obj.width else "—"

    @admin.display(description="Used in")
    def usage(self, obj):
        if not obj.image:
            return "—"
        posts = list(Post.objects.filter(body__contains=obj.image.url).values_list("title", flat=True)[:5])
        return ", ".join(posts) if posts else "Not used in any post"


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("snippet", "display_name", "email", "post", "status_badge", "created_at")
    list_filter = ("status", "created_at", "post")
    search_fields = ("name", "email", "body", "post__title")
    list_select_related = ("post",)
    readonly_fields = ("post", "email", "created_at", "moderated_at", "view_on_post")
    fields = ("post", "view_on_post", "name", "email", "body", "status", "created_at", "moderated_at")
    actions = ["approve", "reject", "mark_spam"]
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        if not request.GET and not request.META.get("QUERY_STRING"):
            return redirect(f"{request.path}?status__exact=pending")
        return super().changelist_view(request, extra_context)

    @admin.display(description="Comment")
    def snippet(self, obj):
        return obj.body if len(obj.body) <= 90 else obj.body[:90] + "…"

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        tone = {"pending": "amber", "approved": "green", "rejected": "grey", "spam": "red"}[obj.status]
        return _badge(obj.get_status_display(), tone)

    @admin.display(description="Link")
    def view_on_post(self, obj):
        if obj.status != Comment.Status.APPROVED or not obj.post.is_live:
            return "Visible on the post once approved and the post is published."
        return format_html('<a href="{}#comment-{}" target="_blank">View on post ↗</a>',
                           obj.post.get_absolute_url(), obj.pk)

    def save_model(self, request, obj, form, change):
        if "status" in form.changed_data:
            obj.moderated_at = timezone.now()
        super().save_model(request, obj, form, change)

    def _set(self, request, queryset, status, label):
        count = queryset.update(status=status, moderated_at=timezone.now())
        self.message_user(request, f"{label} {count} comment(s).", messages.SUCCESS)

    @admin.action(description="Approve selected comments")
    def approve(self, request, queryset):
        self._set(request, queryset, Comment.Status.APPROVED, "Approved")

    @admin.action(description="Reject selected comments")
    def reject(self, request, queryset):
        self._set(request, queryset, Comment.Status.REJECTED, "Rejected")

    @admin.action(description="Mark selected as spam")
    def mark_spam(self, request, queryset):
        self._set(request, queryset, Comment.Status.SPAM, "Marked as spam:")


@admin.register(BlogSettings)
class BlogSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Articles page", {"fields": ("title", "intro", "posts_per_page")}),
        ("Comments", {"fields": ("comments_enabled", "require_approval", "auto_approve_known",
                                 "notify_email", "blocked_words")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:blog_blogsettings_change", args=[BlogSettings.load().pk]))
