"""Tests for admin services API views.

Run with:
    python manage.py test imcp.tests.test_admin_services
"""
import json
import hashlib

from django.test import TestCase
from django.urls import reverse

from imcp.models.service import Service
from imcp.models.api_key import APIKey


def _make_api_key(raw="imcp_adminsvcs1234567890"):
    APIKey.objects.create(
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        key_prefix=raw[:12],
        name="Test Admin Key",
        user_id="admin@example.com",
        roles=["admin"],
    )
    return raw


class TestServicesListCreate(TestCase):

    def setUp(self):
        self.raw_key = _make_api_key()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_list_empty(self):
        resp = self.client.get(reverse("imcp-admin-services"), **self.auth)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("services", data)
        self.assertEqual(data["services"], [])

    def test_create_service(self):
        payload = {
            "name": "TestSvc",
            "spec_type": "OpenAPI",
            "url": "https://api.example.com/openapi.json",
            "category": "Claims",
        }
        resp = self.client.post(
            reverse("imcp-admin-services"),
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Service.objects.count(), 1)
        svc = Service.objects.first()
        self.assertEqual(svc.name, "TestSvc")

    def test_create_missing_required_fields(self):
        resp = self.client.post(
            reverse("imcp-admin-services"),
            data=json.dumps({"name": "NoSpec"}),
            content_type="application/json",
            **self.auth,
        )
        self.assertIn(resp.status_code, [400, 422])
        self.assertEqual(Service.objects.count(), 0)

    def test_list_after_create(self):
        Service.objects.create(
            name="SvcA", spec_type="OpenAPI",
            url="https://a.example.com", category="Cat"
        )
        resp = self.client.get(reverse("imcp-admin-services"), **self.auth)
        data = resp.json()
        self.assertEqual(len(data["services"]), 1)
        self.assertEqual(data["services"][0]["name"], "SvcA")

    def test_requires_auth(self):
        resp = self.client.get(reverse("imcp-admin-services"))
        self.assertEqual(resp.status_code, 401)


class TestServiceDetail(TestCase):

    def setUp(self):
        self.raw_key = _make_api_key("imcp_admindetail123456789")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}
        self.svc = Service.objects.create(
            name="DetailSvc", spec_type="OpenAPI",
            url="https://detail.example.com/openapi.json",
            category="Underwriting",
        )

    def test_get_service(self):
        resp = self.client.get(
            reverse("imcp-admin-service-detail", args=[self.svc.id]),
            **self.auth,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["name"], "DetailSvc")

    def test_update_service(self):
        resp = self.client.put(
            reverse("imcp-admin-service-detail", args=[self.svc.id]),
            data=json.dumps({"category": "Claims"}),
            content_type="application/json",
            **self.auth,
        )
        self.assertIn(resp.status_code, [200, 204])
        self.svc.refresh_from_db()
        self.assertEqual(self.svc.category, "Claims")

    def test_delete_service(self):
        resp = self.client.delete(
            reverse("imcp-admin-service-detail", args=[self.svc.id]),
            **self.auth,
        )
        self.assertIn(resp.status_code, [200, 204])
        self.svc.refresh_from_db()
        self.assertFalse(self.svc.enabled)

    def test_get_not_found(self):
        resp = self.client.get(
            reverse("imcp-admin-service-detail", args=[99999]),
            **self.auth,
        )
        self.assertEqual(resp.status_code, 404)
