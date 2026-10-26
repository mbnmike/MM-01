import logging
import re
from datetime import timedelta

from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import Comment

log = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"(https?://|www\.)", re.I)
MAX_LINKS = 2
BURST_LIMIT, BURST_WINDOW = 3, timedelta(minutes=10)
DAILY_LIMIT = 20


def rate_limited(ip_hash):
    now = timezone.now()
    recent = Comment.objects.filter(ip_hash=ip_hash, created_at__gte=now - timedelta(days=1))
    return (
        recent.filter(created_at__gte=now - BURST_WINDOW).count() >= BURST_LIMIT
        or recent.count() >= DAILY_LIMIT
    )


def is_duplicate(post, email, body):
    return Comment.objects.filter(post=post, email__iexact=email, body=body).exists()


def initial_status(comment, cfg):
    text = f"{comment.name}\n{comment.body}".lower()
    if any(word in text for word in cfg.blocked_word_list):
        return Comment.Status.SPAM
    if len(URL_PATTERN.findall(comment.body)) > MAX_LINKS:
        return Comment.Status.PENDING
    if not cfg.require_approval:
        return Comment.Status.APPROVED
    if cfg.auto_approve_known and Comment.objects.filter(
        email__iexact=comment.email, status=Comment.Status.APPROVED
    ).exists():
        return Comment.Status.APPROVED
    return Comment.Status.PENDING


def notify_new_comment(request, comment, cfg):
    if not cfg.notify_email or comment.status == Comment.Status.SPAM:
        return
    url = request.build_absolute_uri(reverse("admin:blog_comment_change", args=[comment.pk]))
    try:
        send_mail(
            f"New comment on “{comment.post.title}” ({comment.get_status_display().lower()})",
            f"{comment.display_name} wrote:\n\n{comment.body}\n\nModerate: {url}",
            None,
            [cfg.notify_email],
        )
    except Exception:  # Email trouble must never break commenting.
        log.exception("Could not send comment notification")
