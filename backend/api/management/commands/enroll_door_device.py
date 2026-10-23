import hashlib
import os
import secrets

from django.core.management.base import BaseCommand, CommandError

from api.models import DoorDevice, Room


class Command(BaseCommand):
    help = "Enroll or rotate a Wokwi door device without exposing its secret through an API."

    def add_arguments(self, parser):
        parser.add_argument("door_identifier")
        parser.add_argument("--device-id")
        parser.add_argument("--secret-env", default="WOKWI_DEVICE_SECRET")

    def handle(self, *args, **options):
        matches = list(Room.objects.filter(door_identifier=options["door_identifier"])[:2])
        if len(matches) != 1:
            raise CommandError("door_identifier must match exactly one room")
        room = matches[0]
        device_id = options["device_id"] or room.door_identifier
        raw = os.getenv(options["secret_env"]) or secrets.token_urlsafe(32)
        derived = hashlib.sha256(raw.encode()).hexdigest()
        DoorDevice.objects.update_or_create(room=room, defaults={
            "device_id": device_id, "mode": DoorDevice.HARDWARE,
            "secret_hash": derived, "enabled": True, "relay_locked": True,
        })
        self.stdout.write(self.style.SUCCESS(f"Enrolled {device_id} for {room}."))
        if not os.getenv(options["secret_env"]):
            self.stdout.write("Generated secret (shown once; store it outside Git):")
            self.stdout.write(raw)
