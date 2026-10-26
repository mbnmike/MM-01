from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import Comment


class Command(BaseCommand):
    help = "Delete rejected and spam comments (and the email addresses on them) older than --days (default 30)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(days=opts["days"])
        deleted, _ = Comment.objects.filter(
            status__in=[Comment.Status.REJECTED, Comment.Status.SPAM], created_at__lt=cutoff
        ).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} rejected/spam comments older than {opts['days']} days."))
