from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .door_hardware import DoorGateway
from .models import DoorDevice, DoorUnlockCommand


def online(device):
    seconds = getattr(settings, "DOOR_DEVICE_OFFLINE_SECONDS", 10)
    return bool(device.enabled and device.last_seen_at and
                device.last_seen_at >= timezone.now() - timedelta(seconds=seconds))


def device_for(room):
    """Return only enrolled hardware; virtual rows never receive commands."""
    return DoorDevice.objects.filter(room=room, mode=DoorDevice.HARDWARE, enabled=True).first()


class PhysicalDoorGateway(DoorGateway):
    """Queues authorized commands for an enrolled physical polling controller."""

    def __init__(self, device=None):
        self.device = device
        self.configured = device is not None and device.enabled
        self.command = None

    @classmethod
    def for_room(cls, room):
        return cls(device_for(room))

    def device_status(self, room):
        device = self.device or device_for(room)
        if not device:
            return "not_configured"
        return "online" if online(device) else "offline"

    def verify_proximity(self, room, user, method, proof):
        # Identity, employment approval and the room grant have already been
        # checked by RoomUnlockView. This is direct authenticated app access.
        return method == "app"

    def unlock(self, room, user):
        if not self.device or not online(self.device):
            raise ConnectionError("ESP32 door controller is offline")
        ttl = getattr(settings, "DOOR_COMMAND_TTL_SECONDS", 8)
        self.command = DoorUnlockCommand.objects.create(
            device=self.device, requested_by=user,
            expires_at=timezone.now() + timedelta(seconds=ttl), state="created",
        )
        # Confirmation is asynchronous and is applied only by the signed ACK.
        return None
