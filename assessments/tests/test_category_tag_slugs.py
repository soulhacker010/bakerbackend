from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from assessments.models import AssessmentCategory, AssessmentTag


class CategoryAndTagSlugTests(APITestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser(
            email="admin@example.com", password="pass-12345-word")
        self.client.force_authenticate(admin)

    def test_a_category_created_through_the_api_gets_a_slug(self):
        response = self.client.post("/api/assessment-categories/", {"name": "Organizational Development"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["slug"], "organizational-development")

    def test_two_categories_can_be_created_one_after_another(self):
        for name in ("Clinical", "Performance"):
            response = self.client.post("/api/assessment-categories/", {"name": name})
            self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(set(AssessmentCategory.objects.values_list("slug", flat=True)) >= {"clinical", "performance"}, True)

    def test_a_tag_created_through_the_api_gets_a_slug(self):
        response = self.client.post("/api/assessment-tags/", {"name": "High Performance"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["slug"], "high-performance")

    def test_an_existing_slug_is_kept(self):
        tag = AssessmentTag.objects.create(name="ASD", slug="asd")
        tag.name = "Autism"
        tag.save()
        tag.refresh_from_db()
        self.assertEqual(tag.slug, "asd")
