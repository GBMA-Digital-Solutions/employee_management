from django.core.management.base import BaseCommand

from api.attendance_reminders import send_due_reminders


class Command(BaseCommand):
    help = "Send one departure reminder to employees still inside near the end of their workday."

    def handle(self, *args, **options):
        sent = send_due_reminders()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} attendance reminder(s)."))
