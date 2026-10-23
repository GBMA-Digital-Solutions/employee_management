from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import AccountProfile, Attendance, AttendanceVisit, Business, Employee
from .work_schedule import work_summary


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", EMAIL_DELIVERS=True)
class WorkdayFeatureTests(APITestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Acme")
        self.employer = get_user_model().objects.create_user("boss", password="Strong-pass-123")
        AccountProfile.objects.create(user=self.employer, role="employer", business=self.business)

    def test_logout_invalidates_the_access_token_immediately(self):
        signed_in = self.client.post("/api/token/", {"username": "boss", "password": "Strong-pass-123"})
        access = signed_in.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get("/api/account/").status_code, 200)
        self.assertEqual(self.client.post("/api/logout/").status_code, 200)
        self.assertEqual(self.client.get("/api/account/").status_code, 401)

    def test_employer_can_set_company_working_hours(self):
        self.client.force_authenticate(self.employer)
        response = self.client.patch("/api/account/work-schedule/", {
            "expected_daily_hours": "7.50", "workday_start": "08:30",
            "workday_end": "16:00", "reminder_minutes": 20,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.business.refresh_from_db()
        self.assertEqual(str(self.business.expected_daily_hours), "7.50")
        self.assertEqual(self.business.reminder_minutes, 20)

    def test_departure_reminder_is_sent_only_once(self):
        now = timezone.now()
        self.business.expected_daily_hours = 8
        self.business.reminder_minutes = 15
        self.business.save(update_fields=["expected_daily_hours", "reminder_minutes"])
        employee = Employee.objects.create(
            business=self.business, first_name="Ada", last_name="Lovelace",
            email="ada@example.com", job_title="Engineer", date_joined=timezone.localdate(),
            is_active=True,
        )
        attendance = Attendance.objects.create(
            employee=employee, date=timezone.localdate(), check_in_at=now - timedelta(hours=7, minutes=50),
        )
        AttendanceVisit.objects.create(attendance=attendance, check_in_at=attendance.check_in_at)
        call_command("send_attendance_reminders")
        call_command("send_attendance_reminders")
        attendance.refresh_from_db()
        self.assertIsNotNone(attendance.departure_reminder_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("0.17 working hours remaining", mail.outbox[0].body)

    def test_time_outside_does_not_reduce_remaining_work(self):
        now = timezone.now()
        employee = Employee.objects.create(
            business=self.business, first_name="Grace", last_name="Hopper",
            email="grace@example.com", job_title="Engineer", date_joined=timezone.localdate(),
        )
        attendance = Attendance.objects.create(employee=employee, date=timezone.localdate(), check_in_at=now - timedelta(hours=5))
        AttendanceVisit.objects.create(
            attendance=attendance, check_in_at=now - timedelta(hours=5),
            check_out_at=now - timedelta(hours=3),
        )
        AttendanceVisit.objects.create(attendance=attendance, check_in_at=now - timedelta(hours=1))
        summary = work_summary(attendance, now)
        self.assertEqual(summary["worked_seconds"], 3 * 3600)
        self.assertEqual(summary["remaining_seconds"], 5 * 3600)
