from django.core.management.base import BaseCommand

from api.door_provisioning import ensure_door_devices


class Command(BaseCommand):
    help = "Idempotently add a virtual controller to every room that has no controller."

    def handle(self, *args, **options):
        created = ensure_door_devices()
        self.stdout.write(self.style.SUCCESS(
            f"Door controller initialization complete; created {created} virtual controller(s)."
        ))
