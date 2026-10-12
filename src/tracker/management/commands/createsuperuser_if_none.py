import os
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

# The configuration check hands Django each setting under its old name.
CREDENTIALS = {
    "DJANGO_ADMIN_USER": "GULGRIR_ADMIN_USER",
    "DJANGO_ADMIN_PASS": "GULGRIR_ADMIN_PASSWORD",
}


class Command(BaseCommand):
    help = "Create the first superuser from the admin settings if none exists"

    def handle(self, *args, **kwargs):
        User = get_user_model()
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("Superuser already exists - skipping")
            return
        missing = [
            setting for name, setting in CREDENTIALS.items() if not os.getenv(name)
        ]
        if missing:
            raise CommandError(
                f"No superuser exists; set {' and '.join(missing)} to create one."
            )
        username = os.environ["DJANGO_ADMIN_USER"]
        self.stdout.write(f"Creating superuser {username}")
        cast(Any, User.objects).create_superuser(
            username=username, password=os.environ["DJANGO_ADMIN_PASS"]
        )
