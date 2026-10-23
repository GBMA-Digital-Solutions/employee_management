"""Departure reminders: one email per workday to anyone still inside near the end.

Lives apart from the management command so the scheduler in `apps.py` and the
command both run exactly the same sweep.
"""
from datetime import timedelta

from django.core.mail import send_mail
from django.utils import timezone

from . import onboarding
from .models import Attendance
from .work_schedule import expected_departure, work_summary


def send_due_reminders(now=None):
    """Email everyone whose remaining work has dropped under the reminder window."""
    now = now or timezone.now()
    rows = Attendance.objects.filter(
        finalized_at__isnull=True,
        departure_reminder_sent_at__isnull=True,
        visits__check_out_at__isnull=True,
        employee__is_active=True,
    ).select_related("employee__business").distinct()
    sent = 0
    for attendance in rows:
        business = attendance.employee.business
        due = expected_departure(attendance)
        summary = work_summary(attendance, now)
        fixed_schedule_due = bool(
            business.workday_start and business.workday_end
            and due - timedelta(minutes=business.reminder_minutes) <= now <= due + timedelta(hours=4)
        )
        duration_due = summary["remaining_seconds"] <= business.reminder_minutes * 60
        if not (fixed_schedule_due or duration_due):
            continue
        connection = onboarding.mail_connection(business)
        if connection is None or not attendance.employee.email:
            continue
        result = send_mail(
            "Reminder: Check Out before leaving work",
            f"Hello {attendance.employee.first_name},\n\nYour expected workday ends at "
            f"{timezone.localtime(due):%H:%M}. You have "
            f"{summary['remaining_seconds'] / 3600:.2f} working hours remaining. "
            "Please use Check Out for your final departure. "
            "Use Scan Out only if you plan to return today.",
            onboarding.from_address(business), [attendance.employee.email],
            connection=connection, fail_silently=False,
        )
        if result:
            attendance.departure_reminder_sent_at = now
            attendance.save(update_fields=["departure_reminder_sent_at"])
            sent += 1
    return sent
