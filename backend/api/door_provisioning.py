"""Automatic virtual controllers, so every room has a working door panel.

A room with no controller used to fall back to "not enrolled", which is why a
freshly cloned or newly deployed install looked different from a machine where
someone had run `enroll_door_device` by hand. Every room now gets a virtual
controller instead: it drives the Access Control panel (connection, relay, last
command) without any hardware present.

A virtual controller holds no secret and is refused by the signed device
endpoints, so provisioning one can never stand in for enrolling real hardware.
Running this repeatedly is safe: a room that already has a controller, virtual
or hardware, is left exactly as it is.
"""
from django.db import IntegrityError, transaction

from .models import DoorDevice, Room


def device_id_for(room):
    """A stable id derived from the room's primary key.

    Primary keys are unique and never reused, so re-running provisioning
    produces the same id for the same room rather than a second controller.
    """
    return f"virtual-room-{room.pk}"


def ensure_device_for(room):
    """Give `room` a virtual controller if it has none. Returns the DoorDevice.

    Never edits an existing controller, so an enrolled hardware device keeps
    its secret, its mode, and its relay state.
    """
    existing = DoorDevice.objects.filter(room=room).first()
    if existing is not None:
        return existing
    base_id = device_id_for(room)
    # Old installations may already use one of these otherwise deterministic
    # ids for another room. Try stable suffixes without editing that device.
    for suffix in ("", *(f"-{number}" for number in range(2, 101))):
        try:
            with transaction.atomic():
                return DoorDevice.objects.create(
                    room=room, device_id=f"{base_id}{suffix}", mode=DoorDevice.VIRTUAL,
                    secret_hash="", enabled=True, relay_locked=True,
                )
        except IntegrityError:
            # A concurrent worker may have won the room's one-to-one race.
            existing = DoorDevice.objects.filter(room=room).first()
            if existing is not None:
                return existing
    raise IntegrityError(f"Could not allocate a virtual controller id for room {room.pk}")


def ensure_door_devices():
    """Provision every room that has no controller. Returns how many were added."""
    rooms = Room.objects.filter(door_device__isnull=True).order_by("pk")
    return sum(1 for room in rooms if ensure_device_for(room) is not None)
