import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create or update the site admin from ADMIN_USERNAME / ADMIN_PASSWORD (and optional ADMIN_EMAIL). "
        "Handy on hosts without a shell. Remove ADMIN_PASSWORD from the environment afterwards."
    )

    def handle(self, *args, **opts):
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not username or not password:
            raise CommandError("Set ADMIN_USERNAME and ADMIN_PASSWORD first.")
        User = get_user_model()
        user = User.objects.filter(username=username).first() or User(username=username)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError("Password rejected: " + " ".join(exc.messages)) from exc
        created = user.pk is None
        user.email = os.environ.get("ADMIN_EMAIL", user.email or "")
        user.is_staff = user.is_superuser = user.is_active = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} admin user “{username}”."))
