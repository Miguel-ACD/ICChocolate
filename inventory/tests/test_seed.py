"""The public demo setup must be repeatable without changing existing data."""
import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from inventory.models import Movement, Presentation, Stock, UserProfile


class DemoSeedTests(TestCase):
    credentials = {
        "DEMO_OWNER_EMAIL": "demo-owner@qa.test",
        "DEMO_OWNER_PASSWORD": "private-owner-test-password",
        "DEMO_EMPLOYEE_EMAIL": "demo-employee@qa.test",
        "DEMO_EMPLOYEE_PASSWORD": "private-employee-test-password",
    }

    def seed(self):
        with patch.dict(os.environ, self.credentials):
            call_command("seed_demo", stdout=StringIO())

    def test_repeating_seed_does_not_duplicate_stock_or_reset_password(self):
        self.seed()
        self.assertEqual(Movement.objects.filter(type="INICIAL").count(), 5)
        self.assertEqual(Presentation.objects.count(), 5)
        self.assertEqual(sum(Stock.objects.values_list("quantity", flat=True)), 57)
        owner = get_user_model().objects.get(username=self.credentials["DEMO_OWNER_EMAIL"])
        self.assertEqual(owner.profile.role, UserProfile.Role.OWNER)
        self.assertTrue(owner.check_password(self.credentials["DEMO_OWNER_PASSWORD"]))
        owner.set_password("changed-by-owner")
        owner.save(update_fields=["password"])

        self.seed()
        owner.refresh_from_db()
        self.assertTrue(owner.check_password("changed-by-owner"))
        self.assertEqual(Movement.objects.filter(type="INICIAL").count(), 5)
        self.assertEqual(sum(Stock.objects.values_list("quantity", flat=True)), 57)

    def test_missing_demo_passwords_fail_before_creating_accounts(self):
        with patch.dict(os.environ, {"DEMO_OWNER_PASSWORD": "", "DEMO_EMPLOYEE_PASSWORD": ""}):
            with self.assertRaises(CommandError):
                call_command("seed_demo", stdout=StringIO())
        self.assertEqual(get_user_model().objects.count(), 0)
