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


class WokwiPollingGateway(DoorGateway):
    """Queues authorized commands for a locally simulated polling controller."""

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
        # Real-device proximity is intentionally not inferred from the poller.
        # During QR simulation, SimulatorGateway performs the proof check.
        return False

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


def status_for_room(room):
    # Status includes virtual controllers so every Door Simulator renders the
    # same Connection / Relay / Last Command panel. Authentication and command
    # delivery above deliberately remain hardware-only.
    device = DoorDevice.objects.filter(room=room, enabled=True).first()
    if not device:
        return {"configured": False, "connection": "not_configured", "relay_locked": True,
                "last_command": None, "last_acknowledged_at": None}
    if device.mode == DoorDevice.VIRTUAL:
        from .door_simulator import active_doors

        door = active_doors().filter(room=room).first()
        now = timezone.now()
        last_attempt = room.access_attempts.filter(
            result="granted", unlock_status="confirmed", access_method="door_code",
            created_at__gte=device.created_at,
        ).order_by("-created_at").first()
        return {
            "configured": True,
            "mode": DoorDevice.VIRTUAL,
            "connection": "online" if door else "offline",
            "relay_locked": not bool(door and door.unlocked_until and door.unlocked_until > now),
            "last_command": ({
                "id": f"simulation-{last_attempt.pk}", "state": "completed",
                "created_at": last_attempt.created_at, "acknowledged_at": last_attempt.created_at,
                "simulated": True,
            } if last_attempt else None),
            "last_acknowledged_at": last_attempt.created_at if last_attempt else None,
        }
    command = device.commands.order_by("-created_at").first()
    if command and command.state in {"pending", "claimed"} and command.expires_at <= timezone.now():
        command.state = "expired"
        command.save(update_fields=["state"])
    return {
        "configured": True,
        "mode": DoorDevice.HARDWARE,
        "connection": "online" if online(device) else "offline",
        "relay_locked": device.relay_locked,
        "last_command": ({"id": str(command.pk), "state": command.state,
                          "created_at": command.created_at, "acknowledged_at": command.acknowledged_at}
                         if command else None),
        "last_acknowledged_at": device.last_acknowledged_at,
    }
