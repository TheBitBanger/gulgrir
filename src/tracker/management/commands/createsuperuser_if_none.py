from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from gulgrir.settings import setting


class Command(BaseCommand):
    help = "Create the first superuser from the admin settings if none exists"

    def handle(self, *args, **kwargs):
        User = get_user_model()
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("Superuser already exists - skipping")
            return
        username = setting("GULGRIR_ADMIN_USER", "DJANGO_ADMIN_USER")
        password = setting("GULGRIR_ADMIN_PASSWORD", "DJANGO_ADMIN_PASS")
        missing = [
            name
            for name, value in [
                ("GULGRIR_ADMIN_USER", username),
                ("GULGRIR_ADMIN_PASSWORD", password),
            ]
            if not value
        ]
        if missing:
            raise CommandError(
                f"No superuser exists; set {' and '.join(missing)} to create one."
            )
        self.stdout.write(f"Creating superuser {username}")
        cast(Any, User.objects).create_superuser(username=username, password=password)
