"""Authentication and admin access-control regression tests."""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils.crypto import get_random_string
from rest_framework import status

from bakerapi.test_utils import ThrottledAPITestCase

from accounts.password_reset import issue_password_reset_token


def _make_user(email: str, password: str, **extra):
    extra.setdefault("first_name", "Test")
    extra.setdefault("last_name", "User")
    extra.setdefault("is_approved", True)
    return get_user_model().objects.create_user(email=email, password=password, **extra)


@override_settings(TURNSTILE_ENABLED=False)
class LoginTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.password = get_random_string(length=32)
        self.user = _make_user("clinician@example.com", self.password)

    def _login(self, **overrides):
        payload = {"email": self.user.email, "password": self.password}
        payload.update(overrides)
        return self.client.post(reverse("accounts:login"), data=payload, format="json")

    def test_valid_credentials_return_a_token_pair(self):
        response = self._login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())

    def test_wrong_password_is_rejected(self):
        response = self._login(password="not-the-password")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unapproved_account_cannot_log_in(self):
        self.user.is_approved = False
        self.user.save(update_fields=["is_approved"])

        response = self._login()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deactivated_account_cannot_log_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self._login()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(TURNSTILE_ENABLED=False)
class DeactivationTests(ThrottledAPITestCase):
    """Switching a user off must end their access, not just block new logins."""

    def setUp(self):
        super().setUp()
        self.password = get_random_string(length=32)
        self.user = _make_user("clinician@example.com", self.password)

        response = self.client.post(
            reverse("accounts:login"),
            data={"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.access = body["access"]
        self.refresh = body["refresh"]

    def _deactivate(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

    def test_existing_access_token_stops_working_once_deactivated(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        self.assertEqual(self.client.get(reverse("clients:client-list")).status_code, status.HTTP_200_OK)

        self._deactivate()

        self.assertEqual(
            self.client.get(reverse("clients:client-list")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_deactivated_user_cannot_mint_new_tokens(self):
        self._deactivate()

        response = self.client.post(
            reverse("accounts:token-refresh"),
            data={"refresh": self.refresh},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(TURNSTILE_ENABLED=False)
class PasswordResetTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.password = get_random_string(length=32)
        self.user = _make_user("clinician@example.com", self.password)

        response = self.client.post(
            reverse("accounts:login"),
            data={"email": self.user.email, "password": self.password},
            format="json",
        )
        self.refresh = response.json()["refresh"]

    def test_completing_a_reset_revokes_existing_sessions(self):
        token, raw_token, created = issue_password_reset_token(self.user)
        self.assertTrue(created)

        completion = self.client.post(
            reverse("accounts:password-reset-complete"),
            data={
                "token": str(token.token_id),
                "signature": raw_token,
                "password": get_random_string(length=32),
            },
            format="json",
        )
        self.assertEqual(completion.status_code, status.HTTP_200_OK)

        reuse = self.client.post(
            reverse("accounts:token-refresh"),
            data={"refresh": self.refresh},
            format="json",
        )

        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reset_token_cannot_be_used_twice(self):
        token, raw_token, _ = issue_password_reset_token(self.user)
        payload = {
            "token": str(token.token_id),
            "signature": raw_token,
            "password": get_random_string(length=32),
        }

        first = self.client.post(reverse("accounts:password-reset-complete"), data=payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self.client.post(reverse("accounts:password-reset-complete"), data=payload, format="json")

        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("accounts.views.send_password_reset_email")
    def test_request_does_not_reveal_whether_an_account_exists(self, mock_send):
        known = self.client.post(
            reverse("accounts:password-reset-request"),
            data={"email": self.user.email},
            format="json",
        )
        unknown = self.client.post(
            reverse("accounts:password-reset-request"),
            data={"email": "nobody@example.com"},
            format="json",
        )

        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json()["detail"], unknown.json()["detail"])
        mock_send.assert_called_once()


@override_settings(TURNSTILE_ENABLED=False)
class AdminEndpointTests(ThrottledAPITestCase):
    """Every admin handler re-checks is_superuser; none may answer to a clinician."""

    def setUp(self):
        super().setUp()
        self.clinician = _make_user("clinician@example.com", get_random_string(length=32))
        self.target = _make_user("target@example.com", get_random_string(length=32), is_approved=False)

    def _endpoints(self):
        return [
            ("get", reverse("accounts:pending-users"), None),
            ("get", reverse("accounts:all-users"), None),
            ("post", reverse("accounts:approve-user"), {"user_id": self.target.id}),
            ("post", reverse("accounts:reject-user"), {"user_id": self.target.id}),
            ("post", reverse("accounts:toggle-user-active"), {"user_id": self.target.id}),
            ("post", reverse("accounts:delete-user"), {"user_id": self.target.id}),
        ]

    def test_clinician_is_refused_by_every_admin_endpoint(self):
        self.client.force_authenticate(self.clinician)

        for method, url, payload in self._endpoints():
            with self.subTest(url=url):
                request = getattr(self.client, method)
                response = request(url, data=payload, format="json") if payload else request(url)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.target.refresh_from_db()
        self.assertFalse(self.target.is_approved)
        self.assertTrue(self.target.is_active)

    def test_anonymous_is_refused_by_every_admin_endpoint(self):
        for method, url, payload in self._endpoints():
            with self.subTest(url=url):
                request = getattr(self.client, method)
                response = request(url, data=payload, format="json") if payload else request(url)
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_superuser_can_approve(self):
        admin = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password=get_random_string(length=32),
            first_name="Admin",
            last_name="User",
            is_approved=True,
        )
        self.client.force_authenticate(admin)

        response = self.client.post(
            reverse("accounts:approve-user"),
            data={"user_id": self.target.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_approved)
