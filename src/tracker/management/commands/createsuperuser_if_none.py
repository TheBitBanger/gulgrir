from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os


class Command(BaseCommand):
    help = "Create an admin user from env vars if none exist"

    def handle(self, *args, **kwargs):
        User = get_user_model()
        if not User.objects.filter(is_superuser=True).exists():
            username = os.getenv("DJANGO_ADMIN_USER", "admin")
            password = os.getenv("DJANGO_ADMIN_PASS", "admin")
            self.stdout.write(f"Creating superuser {username}")
            User.objects.create_superuser(username=username, password=password)
        else:
            self.stdout.write("Superuser already exists - skipping")
