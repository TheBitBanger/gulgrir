import io
import os
from typing import Any, cast
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

# Old names, which Django falls back to outside start-up.
CREDENTIALS = {"DJANGO_ADMIN_USER": "owner", "DJANGO_ADMIN_PASS": "a-long-password"}
SETTING_NAMES = {
    "DJANGO_ADMIN_USER": "GULGRIR_ADMIN_USER",
    "DJANGO_ADMIN_PASS": "GULGRIR_ADMIN_PASSWORD",
}


class SuperuserBootstrapTests(TestCase):
    def bootstrap(self, **env: str) -> None:
        names = {*SETTING_NAMES, *SETTING_NAMES.values()}
        clean = {k: v for k, v in os.environ.items() if k not in names}
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
            call_command("createsuperuser_if_none", stdout=io.StringIO())

    def test_refuses_without_credentials_when_no_superuser_exists(self):
        cases = [
            {},
            {"DJANGO_ADMIN_USER": "owner"},
            {"DJANGO_ADMIN_PASS": "a-long-password"},
            {"DJANGO_ADMIN_USER": "owner", "DJANGO_ADMIN_PASS": ""},
            {"DJANGO_ADMIN_USER": "", "DJANGO_ADMIN_PASS": "a-long-password"},
        ]
        for env in cases:
            with self.subTest(env=env):
                with self.assertRaises(CommandError) as raised:
                    self.bootstrap(**env)

                message = str(raised.exception)
                self.assertIn("superuser", message.lower())
                for name, setting in SETTING_NAMES.items():
                    if env.get(name):
                        self.assertNotIn(setting, message)
                    else:
                        self.assertIn(setting, message)
                self.assertFalse(get_user_model().objects.exists())

    def test_creates_superuser_from_credentials(self):
        self.bootstrap(**CREDENTIALS)

        user = get_user_model().objects.get(username="owner")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("a-long-password"))

    def test_existing_superuser_ignores_credentials(self):
        cast(Any, get_user_model().objects).create_superuser(
            username="first", password="x"
        )

        self.bootstrap(**CREDENTIALS)

        self.assertEqual(
            list(get_user_model().objects.values_list("username", flat=True)), ["first"]
        )

    def test_existing_superuser_starts_without_credentials(self):
        cast(Any, get_user_model().objects).create_superuser(
            username="first", password="x"
        )

        self.bootstrap()

    def test_reads_new_names_before_old_ones(self):
        """CFG-V6: the new name wins; an empty or missing one falls back to the old."""
        cases = [
            (
                {"GULGRIR_ADMIN_USER": "new", "GULGRIR_ADMIN_PASSWORD": "new-password"},
                "new",
                "new-password",
            ),
            (
                {
                    **CREDENTIALS,
                    "GULGRIR_ADMIN_USER": "new",
                    "GULGRIR_ADMIN_PASSWORD": "new-password",
                },
                "new",
                "new-password",
            ),
            (
                {**CREDENTIALS, "GULGRIR_ADMIN_USER": "", "GULGRIR_ADMIN_PASSWORD": ""},
                "owner",
                "a-long-password",
            ),
            (
                {"GULGRIR_ADMIN_USER": "new", "DJANGO_ADMIN_PASS": "a-long-password"},
                "new",
                "a-long-password",
            ),
        ]
        for env, username, password in cases:
            with self.subTest(env=env):
                get_user_model().objects.all().delete()

                self.bootstrap(**env)

                user = get_user_model().objects.get()
                self.assertEqual(user.username, username)
                self.assertTrue(user.check_password(password))
