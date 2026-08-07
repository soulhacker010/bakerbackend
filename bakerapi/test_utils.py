"""Shared helpers for the test suite."""
from __future__ import annotations

from django.core.cache import cache
from rest_framework.test import APITestCase


class ThrottledAPITestCase(APITestCase):
    """APITestCase that clears throttle history between tests.

    DRF keeps rate-limit counters in the default cache, which lives for the whole
    test process rather than per test. Without this reset a full-suite run trips
    the login and anonymous limits, and tests pass or fail depending on what ran
    before them.
    """

    def setUp(self):
        super().setUp()
        cache.clear()

    def tearDown(self):
        cache.clear()
        super().tearDown()
