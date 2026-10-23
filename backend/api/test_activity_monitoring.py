from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import (AccountProfile, ActivityClassification, ActivityEvent, Attendance,
                     AttendanceVisit, Business, Employee, MonitoringConsent)


class ActivityMonitoringTests(APITestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Acme")
        self.employer = get_user_model().objects.create_user("boss", password="pass")
        AccountProfile.objects.create(user=self.employer, role="employer", business=self.business)
        self.employee = Employee.objects.create(
            business=self.business, first_name="Ada", last_name="Lovelace", email="ada@example.com",
            job_title="Engineer", date_joined=timezone.localdate(), is_active=True,
        )
        self.employee_user = get_user_model().objects.create_user("ada", password="pass")
        AccountProfile.objects.create(user=self.employee_user, role="employee", employee=self.employee)
        MonitoringConsent.objects.create(employee=self.employee, acknowledged_at=timezone.now())
        now = timezone.now()
        attendance = Attendance.objects.create(employee=self.employee, date=timezone.localdate(), check_in_at=now - timedelta(hours=1))
        AttendanceVisit.objects.create(attendance=attendance, check_in_at=now - timedelta(hours=1))

    def token(self):
        self.client.force_authenticate(self.employer)
        return self.client.post(f"/api/activity-monitoring/agents/{self.employee.pk}/").data["token"]

    def test_authorized_agent_ingests_sanitized_activity_during_attendance(self):
        token = self.token()
        now = timezone.now()
        self.client.force_authenticate(None)
        response = self.client.post("/api/activity-monitoring/ingest/", {
            "source": "browser", "kind": "website",
            "resource": "https://docs.example.com/project?secret=value#private",
            "started_at": now - timedelta(minutes=5), "ended_at": now,
        }, format="json", HTTP_X_MONITORING_AGENT_TOKEN=token)
        self.assertEqual(response.status_code, 201, response.data)
        event = ActivityEvent.objects.get()
        self.assertEqual(event.resource, "https://docs.example.com/project")
        self.assertEqual(event.domain, "docs.example.com")
        self.client.force_authenticate(self.employer)
        report = self.client.get(f"/api/activity-monitoring/?employee={self.employee.pk}&period=daily")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data["total_seconds"], 300)
        self.assertTrue(report.data["employees"][0]["agent_active"])
        self.assertIsNotNone(report.data["employees"][0]["agent_last_seen_at"])

    def test_sensitive_payloads_and_activity_outside_attendance_are_rejected(self):
        token = self.token()
        now = timezone.now()
        self.client.force_authenticate(None)
        sensitive = self.client.post("/api/activity-monitoring/ingest/", {
            "source": "windows", "kind": "application", "resource": "Teams",
            "started_at": now - timedelta(minutes=2), "ended_at": now, "keystrokes": "secret",
        }, format="json", HTTP_X_MONITORING_AGENT_TOKEN=token)
        self.assertEqual(sensitive.status_code, 400)
        AttendanceVisit.objects.update(check_out_at=now - timedelta(minutes=3))
        outside = self.client.post("/api/activity-monitoring/ingest/", {
            "source": "windows", "kind": "application", "resource": "Excel",
            "started_at": now - timedelta(minutes=2), "ended_at": now,
        }, format="json", HTTP_X_MONITORING_AGENT_TOKEN=token)
        self.assertEqual(outside.status_code, 403)

    def test_reports_are_company_scoped_and_domains_are_classified(self):
        other = Business.objects.create(name="Other")
        # Active on purpose, so the exclusion below proves company scoping
        # rather than simply skipping an inactive employee.
        outsider = Employee.objects.create(business=other, first_name="Other", last_name="Worker",
                                            email="other@example.com", job_title="Dev",
                                            date_joined=timezone.localdate(), is_active=True)
        now = timezone.now()
        ActivityEvent.objects.create(employee=self.employee, source="browser", kind="website",
                                     resource="https://youtube.com/", domain="youtube.com",
                                     started_at=now - timedelta(minutes=10), ended_at=now,
                                     duration_seconds=600)
        ActivityEvent.objects.create(employee=outsider, source="windows", kind="application", resource="PrivateApp",
                                     started_at=now - timedelta(minutes=5), ended_at=now, duration_seconds=300)
        self.client.force_authenticate(self.employer)
        classified = self.client.post("/api/activity-monitoring/classifications/",
                                      {"domain": "youtube.com", "category": "entertainment"}, format="json")
        self.assertEqual(classified.status_code, 200)
        report = self.client.get(f"/api/activity-monitoring/?employee={self.employee.pk}&period=daily")
        self.assertEqual(report.status_code, 200)
        self.assertEqual([row["resource"] for row in report.data["resources"]], ["https://youtube.com/"])
        self.assertEqual(report.data["resources"][0]["category"], "entertainment")
        self.assertNotContains(report, "PrivateApp")

    def test_employee_must_acknowledge_before_agent_is_issued(self):
        MonitoringConsent.objects.filter(employee=self.employee).update(acknowledged_at=None)
        self.client.force_authenticate(self.employer)
        self.assertEqual(self.client.post(f"/api/activity-monitoring/agents/{self.employee.pk}/").status_code, 400)
        self.client.force_authenticate(self.employee_user)
        acknowledged = self.client.post("/api/me/monitoring-disclosure/", {"acknowledged": True}, format="json")
        self.assertEqual(acknowledged.status_code, 200)
