from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.ratelimit import ip_hash
from core.utils import json_ld

from . import services
from .forms import CommentForm, comment_token
from .models import BlogSettings, Comment, Post, Tag
from .rendering import PROSE_DARK_CLASSES


def _published():
    return Post.objects.published().select_related("author", "category").prefetch_related("tags")


def _archive_months():
    """[(date(year, month, 1), post_count), ...] newest first, only months that have published posts."""
    rows = (
        Post.objects.published()
        .annotate(month=TruncMonth("published_at"))
        .values("month")
        .annotate(n=Count("id"))
        .order_by("-month")
    )
    return [(timezone.localtime(r["month"]).date() if hasattr(r["month"], "tzinfo") else r["month"], r["n"])
            for r in rows]


def post_list(request, tag_slug=None, year=None, month=None):
    cfg = BlogSettings.load()
    tag = get_object_or_404(Tag, slug=tag_slug) if tag_slug else None
    query = request.GET.get("q", "").strip()[:100]
    selected_month = None
    if year is not None:
        try:
            selected_month = date(year, month, 1)
        except ValueError:
            raise Http404

    posts = _published()
    if selected_month:
        posts = posts.filter(published_at__year=year, published_at__month=month)
    if tag:
        posts = posts.filter(tags=tag)
    if query:
        posts = posts.filter(
            Q(title__icontains=query) | Q(excerpt__icontains=query) | Q(body__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()

    is_filtered = bool(selected_month or tag or query)
    featured = None
    if not is_filtered:
        featured = posts.filter(is_featured=True).first() or posts.first()
        if featured:
            posts = posts.exclude(pk=featured.pk)

    page = Paginator(posts, cfg.posts_per_page).get_page(request.GET.get("page"))
    months = _archive_months()
    if selected_month and selected_month not in [m for m, _ in months]:
        raise Http404

    newer_month = older_month = None
    if selected_month:
        keys = [m for m, _ in months]
        i = keys.index(selected_month)
        newer_month = keys[i - 1] if i > 0 else None
        older_month = keys[i + 1] if i + 1 < len(keys) else None

    live = Q(posts__status=Post.Status.PUBLISHED, posts__published_at__lte=timezone.now())
    tags = Tag.objects.annotate(n=Count("posts", filter=live, distinct=True)).filter(n__gt=0).order_by("-n", "name")[:24]

    return render(request, "blog/post_list.html", {
        "cfg": cfg,
        "page": page,
        "featured": featured if page.number == 1 else None,
        "tag": tag,
        "query": query,
        "months": months,
        "selected_month": selected_month,
        "newer_month": newer_month,
        "older_month": older_month,
        "tags": tags,
        "is_filtered": is_filtered,
    })


def post_context(request, post, *, form=None, tags=None, preview=False):
    """Everything post_detail.html needs. Also used by the admin's preview of unsaved edits."""
    cfg = BlogSettings.load()
    tags = list(post.tags.all()) if tags is None else tags

    related = []
    if post.pk:
        candidates = _published().exclude(pk=post.pk)
        related = list(candidates.filter(tags__in=tags).distinct()[:3]) if tags else []
        if len(related) < 3:
            related += list(candidates.exclude(pk__in=[p.pk for p in related])[: 3 - len(related)])

    share_url = request.build_absolute_uri(post.get_absolute_url()) if post.slug else ""
    return {
        "post": post,
        "post_tags": tags,
        "prose_classes": PROSE_DARK_CLASSES,
        "related_posts": related,
        "comments": post.comments.filter(status=Comment.Status.APPROVED) if post.pk else [],
        "comments_open": cfg.comments_enabled and post.allow_comments and not preview,
        "form": form or CommentForm(post=post),
        "comment_token": comment_token(post) if post.pk else "",
        "share_url": share_url,
        "schema_json": json_ld(post.schema(request, tags)) if share_url else "",
        "og_image": request.build_absolute_uri(post.cover_image.url) if post.cover_image else "",
        "preview": preview,
    }


def post_detail(request, slug):
    post = get_object_or_404(_published(), slug=slug)
    return render(request, "blog/post_detail.html", post_context(request, post))


@require_POST
def post_comment(request, slug):
    post = get_object_or_404(_published(), slug=slug)
    cfg = BlogSettings.load()
    if not (cfg.comments_enabled and post.allow_comments):
        messages.error(request, "Comments are closed on this post.")
        return redirect(post)

    form = CommentForm(request.POST, post=post)
    if form.is_valid():
        if form.is_trap:
            messages.success(request, "Thanks! Your comment will appear once it's approved.")
            return redirect(f"{post.get_absolute_url()}#comments")
        client = ip_hash(request)
        data = form.cleaned_data
        if services.rate_limited(client):
            form.add_error(None, "You're commenting a lot right now. Please try again in a few minutes.")
        elif services.is_duplicate(post, data["email"], data["body"]):
            form.add_error(None, "Looks like you've already posted this comment.")
        else:
            comment = Comment(post=post, name=data["name"], email=data["email"], body=data["body"], ip_hash=client)
            comment.status = services.initial_status(comment, cfg)
            comment.save()
            services.notify_new_comment(request, comment, cfg)
            if comment.status == Comment.Status.APPROVED:
                messages.success(request, "Thanks! Your comment is live.")
                return redirect(f"{post.get_absolute_url()}#comment-{comment.pk}")
            messages.success(request, "Thanks! Your comment will appear once it's approved.")
            return redirect(f"{post.get_absolute_url()}#comments")

    return render(request, "blog/post_detail.html", post_context(request, post, form=form), status=400)
