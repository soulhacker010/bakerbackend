"""Assessment bundles: a named set of assessments sent together.

The practice's October 2026 update: "Create bundles or batteries where we can
put all assessments together and send them out." The first one they need is
their Middlesex screening - PC-PTSD-5, the WHO-5 and the Oldenburg - and a
bundle saves choosing those three by hand for every client.

Bundles are shared the way the assessment library is: every clinician sees and
uses all of them, only the author or an admin may change one.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from bakerapi.test_utils import ThrottledAPITestCase

from assessments.models import Assessment, AssessmentBundle
from clients.models import Client

LIST = "assessments:assessment-bundle-list"


def detail(pk):
    return reverse("assessments:assessment-bundle-detail", args=[pk])


@override_settings(TURNSTILE_ENABLED=False)
class AssessmentBundleTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.author = User.objects.create_user(
            email="author@example.com", password="pw-Author-123456",
            first_name="Jennifer", last_name="Ajosa", is_approved=True,
        )
        self.colleague = User.objects.create_user(
            email="colleague@example.com", password="pw-Colleague-12345", is_approved=True,
        )
        self.admin = User.objects.create_user(
            email="admin@example.com", password="pw-Admin-1234567", is_approved=True,
            is_staff=True,
        )
        for slug in ("pc-ptsd-5", "who-5", "olbi", "phq-9"):
            Assessment.objects.create(
                title=slug.upper(), slug=slug, status=Assessment.Status.PUBLISHED,
                created_by=self.admin,
            )
        Assessment.objects.create(
            title="Unfinished", slug="draft-thing", status=Assessment.Status.DRAFT,
            created_by=self.admin,
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def create(self, name="Middlesex screening", assessments=("pc-ptsd-5", "who-5", "olbi"),
               user=None):
        self.as_user(user or self.author)
        return self.client.post(
            reverse(LIST), {"name": name, "assessments": list(assessments)}, format="json"
        )

    # --------------------------------------------------------------- creating

    def test_a_clinician_can_save_a_bundle(self):
        response = self.create()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        self.assertEqual(response.json()["name"], "Middlesex screening")

    def test_the_order_is_kept_because_it_is_the_order_the_patient_meets_them(self):
        response = self.create(assessments=("olbi", "pc-ptsd-5", "who-5"))
        self.assertEqual([a["slug"] for a in response.json()["assessments"]],
                         ["olbi", "pc-ptsd-5", "who-5"])

    def test_it_reads_back_names_as_well_as_codes(self):
        first = self.create().json()["assessments"][0]
        self.assertEqual(first, {"slug": "pc-ptsd-5", "title": "PC-PTSD-5"})

    def test_it_records_who_made_it(self):
        self.assertEqual(self.create().json()["created_by"], "Jennifer Ajosa")

    def test_stray_spaces_in_the_name_are_tidied(self):
        self.assertEqual(self.create(name="  Middlesex   screening ").json()["name"],
                         "Middlesex screening")

    # ------------------------------------------------------------- refusals

    def test_a_name_is_required(self):
        response = self.create(name="   ")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.json())

    def test_two_bundles_cannot_share_a_name_whatever_the_capitals(self):
        self.create()
        response = self.create(name="MIDDLESEX Screening", user=self.colleague)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already a bundle", str(response.json()["name"]))

    def test_an_empty_bundle_is_refused(self):
        self.assertEqual(self.create(assessments=()).status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_same_assessment_twice_is_refused(self):
        response = self.create(assessments=("who-5", "olbi", "who-5"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("who-5", str(response.json()["assessments"]))

    def test_a_draft_cannot_go_in_a_shared_bundle(self):
        """A draft is visible to its author and admins only. Anyone else picking
        the bundle would have the invitation refused when it was sent."""
        self.as_user(self.admin)
        response = self.create(assessments=("who-5", "draft-thing"), user=self.admin)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("draft-thing", str(response.json()["assessments"]))

    def test_an_assessment_that_does_not_exist_is_refused(self):
        response = self.create(assessments=("who-5", "no-such-thing"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_signed_out_visitor_sees_nothing(self):
        self.create()
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(reverse(LIST)).status_code, status.HTTP_401_UNAUTHORIZED)

    # -------------------------------------------------------------- sharing

    def test_every_clinician_sees_every_bundle(self):
        self.create()
        self.as_user(self.colleague)
        names = [b["name"] for b in self.client.get(reverse(LIST)).json()]
        self.assertEqual(names, ["Middlesex screening"])

    def test_a_colleague_cannot_change_someone_elses_bundle(self):
        pk = self.create().json()["id"]
        self.as_user(self.colleague)
        response = self.client.patch(detail(pk), {"name": "Mine now"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(AssessmentBundle.objects.get(pk=pk).name, "Middlesex screening")

    def test_a_colleague_cannot_delete_someone_elses_bundle(self):
        pk = self.create().json()["id"]
        self.as_user(self.colleague)
        self.assertEqual(self.client.delete(detail(pk)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(AssessmentBundle.objects.filter(pk=pk).exists())

    def test_the_page_is_told_who_may_edit(self):
        """So the edit and delete controls only appear for someone allowed them."""
        pk = self.create().json()["id"]
        self.as_user(self.author)
        self.assertTrue(self.client.get(detail(pk)).json()["can_edit"])
        self.as_user(self.colleague)
        self.assertFalse(self.client.get(detail(pk)).json()["can_edit"])
        self.as_user(self.admin)
        self.assertTrue(self.client.get(detail(pk)).json()["can_edit"])

    def test_an_admin_can_tidy_up_anyones_bundle(self):
        pk = self.create().json()["id"]
        self.as_user(self.admin)
        self.assertEqual(self.client.delete(detail(pk)).status_code, status.HTTP_204_NO_CONTENT)

    def test_a_bundle_outlives_its_authors_account(self):
        pk = self.create().json()["id"]
        self.author.delete()
        self.as_user(self.colleague)
        body = self.client.get(detail(pk)).json()
        self.assertEqual(len(body["assessments"]), 3)
        self.assertFalse(body["can_edit"])

    # -------------------------------------------------------------- editing

    def test_the_author_can_change_what_is_in_it(self):
        pk = self.create().json()["id"]
        response = self.client.patch(detail(pk), {"assessments": ["who-5", "phq-9"]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([a["slug"] for a in response.json()["assessments"]], ["who-5", "phq-9"])

    def test_renaming_alone_leaves_the_contents_alone(self):
        pk = self.create().json()["id"]
        response = self.client.patch(detail(pk), {"name": "Middlesex intake"}, format="json")
        self.assertEqual(len(response.json()["assessments"]), 3)

    def test_renaming_to_another_bundles_name_is_refused(self):
        self.create(name="First")
        pk = self.create(name="Second").json()["id"]
        response = self.client.patch(detail(pk), {"name": "first"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_keeping_its_own_name_is_not_a_clash(self):
        pk = self.create().json()["id"]
        response = self.client.patch(
            detail(pk), {"name": "Middlesex screening", "assessments": ["who-5"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

    # ------------------------------------------- when the library changes

    def test_an_assessment_unpublished_later_is_left_out_and_counted(self):
        """The bundle must not offer what the invitation would then refuse, and
        must not quietly look whole when it has shrunk."""
        pk = self.create().json()["id"]
        Assessment.objects.filter(slug="olbi").update(status=Assessment.Status.DRAFT)
        self.as_user(self.colleague)
        body = self.client.get(detail(pk)).json()
        self.assertEqual([a["slug"] for a in body["assessments"]], ["pc-ptsd-5", "who-5"])
        self.assertEqual(body["unavailable_count"], 1)

    def test_a_deleted_assessment_leaves_every_bundle(self):
        pk = self.create().json()["id"]
        Assessment.objects.filter(slug="olbi").delete()
        body = self.client.get(detail(pk)).json()
        self.assertEqual([a["slug"] for a in body["assessments"]], ["pc-ptsd-5", "who-5"])
        self.assertEqual(body["unavailable_count"], 0)

    # ------------------------------------------------------------ end to end

    def test_a_bundle_sends_as_one_invitation_in_its_own_order(self):
        """What a bundle is for: choose it, send it, the client meets the
        assessments in the order the bundle sets."""
        bundle = self.create(assessments=("who-5", "pc-ptsd-5", "olbi")).json()
        client = Client.objects.create(
            owner=self.author, first_name="Jordan", last_name="Doe", slug="jordan-doe",
        )

        self.as_user(self.author)
        issued = self.client.post(
            reverse("assessments:respondent-link-issue"),
            {"assessments": [a["slug"] for a in bundle["assessments"]],
             "mode": "linked", "clientSlug": client.slug},
            format="json",
        )
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED, issued.json())

        self.client.force_authenticate(user=None)
        resolved = self.client.post(
            reverse("assessments:respondent-link-resolve"),
            {"token": issued.json()["token"]}, format="json",
        ).json()
        self.assertEqual([a["slug"] for a in resolved["assessments"]],
                         ["who-5", "pc-ptsd-5", "olbi"])
