"""Multi-tenant isolation tests for clients and client groups."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.crypto import get_random_string
from rest_framework import status

from bakerapi.test_utils import ThrottledAPITestCase

from clients.models import Client, ClientGroup


def _make_clinician(email: str):
    return get_user_model().objects.create_user(
        email=email,
        password=get_random_string(length=32),
        first_name="Test",
        last_name="Clinician",
        is_approved=True,
    )


class ClientIsolationTests(ThrottledAPITestCase):
    """Clinician A must never reach clinician B's client records."""

    def setUp(self):
        super().setUp()
        self.clinician_a = _make_clinician("a@example.com")
        self.clinician_b = _make_clinician("b@example.com")

        self.client_a = Client.objects.create(
            owner=self.clinician_a,
            first_name="Alice",
            last_name="Adams",
            email="alice@example.com",
            slug="alice-adams",
        )
        self.client_b = Client.objects.create(
            owner=self.clinician_b,
            first_name="Bianca",
            last_name="Bell",
            email="bianca@example.com",
            slug="bianca-bell",
        )

        self.client.force_authenticate(self.clinician_a)

    def test_list_only_returns_own_clients(self):
        response = self.client.get(reverse("clients:client-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [row["slug"] for row in response.json()]
        self.assertEqual(slugs, [self.client_a.slug])

    def test_retrieve_by_slug_of_another_clinicians_client_is_not_found(self):
        response = self.client.get(
            reverse("clients:client-detail", args=[self.client_b.slug])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn("bianca@example.com", response.content.decode())

    def test_retrieve_by_id_of_another_clinicians_client_is_not_found(self):
        response = self.client.get(
            reverse("clients:client-detail", args=[str(self.client_b.pk)])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_of_another_clinicians_client_is_not_found(self):
        response = self.client.patch(
            reverse("clients:client-detail", args=[self.client_b.slug]),
            data={"first_name": "Hacked"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.client_b.refresh_from_db()
        self.assertEqual(self.client_b.first_name, "Bianca")

    def test_delete_of_another_clinicians_client_is_not_found(self):
        response = self.client.delete(
            reverse("clients:client-detail", args=[self.client_b.slug])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Client.objects.filter(pk=self.client_b.pk).exists())

    def test_anonymous_cannot_list_clients(self):
        self.client.force_authenticate(None)

        response = self.client.get(reverse("clients:client-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SharedSlugIsolationTests(ThrottledAPITestCase):
    """Slugs are unique per owner, so both clinicians can hold the same one."""

    def setUp(self):
        super().setUp()
        self.clinician_a = _make_clinician("a@example.com")
        self.clinician_b = _make_clinician("b@example.com")

        self.client_a = Client.objects.create(
            owner=self.clinician_a,
            first_name="John",
            last_name="Doe",
            email="john.a@example.com",
            slug="john-doe",
        )
        self.client_b = Client.objects.create(
            owner=self.clinician_b,
            first_name="John",
            last_name="Doe",
            email="john.b@example.com",
            slug="john-doe",
        )

    def test_each_clinician_resolves_the_slug_to_their_own_client(self):
        for clinician, expected in ((self.clinician_a, self.client_a), (self.clinician_b, self.client_b)):
            with self.subTest(clinician=clinician.email):
                self.client.force_authenticate(clinician)
                response = self.client.get(reverse("clients:client-detail", args=["john-doe"]))

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.json()["id"], expected.id)
                self.assertEqual(response.json()["email"], expected.email)

    def test_editing_the_shared_slug_only_touches_the_callers_client(self):
        self.client.force_authenticate(self.clinician_a)

        response = self.client.patch(
            reverse("clients:client-detail", args=["john-doe"]),
            data={"first_name": "Jonathan"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_a.refresh_from_db()
        self.client_b.refresh_from_db()
        self.assertEqual(self.client_a.first_name, "Jonathan")
        self.assertEqual(self.client_b.first_name, "John")


class ClientGroupIsolationTests(ThrottledAPITestCase):
    """Client groups are scoped to their owner in the same way."""

    def setUp(self):
        super().setUp()
        self.clinician_a = _make_clinician("a@example.com")
        self.clinician_b = _make_clinician("b@example.com")

        self.group_b = ClientGroup.objects.create(
            owner=self.clinician_b,
            name="Bianca's cohort",
            slug="biancas-cohort",
        )
        self.client_b = Client.objects.create(
            owner=self.clinician_b,
            first_name="Bianca",
            last_name="Bell",
            email="bianca@example.com",
            slug="bianca-bell",
        )

        self.client.force_authenticate(self.clinician_a)

    def test_list_excludes_another_clinicians_groups(self):
        response = self.client.get(reverse("clients:client-group-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])

    def test_retrieve_of_another_clinicians_group_is_not_found(self):
        response = self.client.get(
            reverse("clients:client-group-detail", args=[self.group_b.slug])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_of_another_clinicians_group_is_not_found(self):
        response = self.client.delete(
            reverse("clients:client-group-detail", args=[self.group_b.slug])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(ClientGroup.objects.filter(pk=self.group_b.pk).exists())

    def test_cannot_add_another_clinicians_client_to_a_group(self):
        response = self.client.post(
            reverse("clients:client-group-list"),
            data={"name": "My cohort", "member_slugs": [self.client_b.slug]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.client_b.group_memberships.exists())
