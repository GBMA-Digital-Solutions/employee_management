import logging
import os
import threading
import time

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger("api")


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        if getattr(settings, "RUNNING_TESTS", False):
            return
        self.start_reminder_scheduler()
        # Shows in the Render deploy and runtime logs. Never logs the key itself.
        if settings.BREVO_API_KEY:
            logger.info("Email delivery: Brevo API key loaded; sending as %s.", settings.DEFAULT_FROM_EMAIL)
            return
        level = logging.WARNING if getattr(settings, "ON_RENDER", False) else logging.INFO
        logger.log(level, "Email delivery: BREVO_API_KEY is not set, so Brevo is off.")
        lookalikes = [name for name in os.environ if "BREVO" in name.upper() and name != "BREVO_API_KEY"]
        if lookalikes:
            logger.warning("Found similar environment variable names %s. The name must be exactly "
                           "BREVO_API_KEY.", ", ".join(repr(name) for name in lookalikes))

    def start_reminder_scheduler(self):
        """Sweep for due departure reminders on a timer.

        Without this nothing ever sends them: the management command only runs
        when someone invokes it. Set ATTENDANCE_REMINDER_SECONDS=0 to turn the
        thread off and drive the command from a real scheduler instead, which
        is what a multi-worker deployment should do.
        """
        seconds = getattr(settings, "ATTENDANCE_REMINDER_SECONDS", 0)
        if not seconds:
            return
        # runserver's autoreloader runs ready() in both processes; only the
        # child (RUN_MAIN) should own the timer, or reminders go out twice.
        if settings.DEBUG and os.environ.get("RUN_MAIN") != "true":
            return
        if getattr(ApiConfig, "_reminder_thread", None):
            return

        def sweep():
            from django.db import connections

            from .attendance_reminders import send_due_reminders
            while True:
                time.sleep(seconds)
                try:
                    sent = send_due_reminders()
                    if sent:
                        logger.info("Departure reminders: sent %s.", sent)
                except Exception:
                    logger.exception("Departure reminder sweep failed; will retry.")
                finally:
                    # A long-lived thread must not hold a connection open.
                    connections.close_all()

        ApiConfig._reminder_thread = threading.Thread(
            target=sweep, name="attendance-reminders", daemon=True)
        ApiConfig._reminder_thread.start()
        logger.info("Departure reminders: checking every %s seconds.", seconds)
