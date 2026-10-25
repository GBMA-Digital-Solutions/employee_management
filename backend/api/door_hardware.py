"""The boundary between room access control and physical door hardware.

Nothing here opens a door by itself. A real NFC or Bluetooth integration is a
class implementing `DoorGateway`, named by the `DOOR_GATEWAY` setting (a dotted
path). Until one is configured every unlock request stops at
`NotConfiguredGateway`, which reports that no hardware is connected; a
successful unlock is never pretended.
"""
from django.conf import settings
from django.utils.module_loading import import_string


class DoorGateway:
    """What a door integration must provide.

    `configured` is False only for the placeholder below. Implementations must
    verify the proximity proof cryptographically against the door's own reader
    (an NFC tag challenge or a Bluetooth beacon handshake), never trust the
    method name alone.
    """

    configured = True
    # When set, an unlock request must report a distance to the door no greater than this.
    max_distance_cm = None

    def device_status(self, room):
        """"online", "offline" or "not_configured" for the room's door controller."""
        raise NotImplementedError

    def verify_proximity(self, room, user, method, proof):
        """True only when `proof` shows `user`'s device is at this room's door."""
        raise NotImplementedError

    def unlock(self, room, user):
        """Tell the door to open.

        Returns True when the door confirmed it unlocked, None when the command
        was accepted without confirmation, and raises when the controller could
        not be reached.
        """
        raise NotImplementedError


class NotConfiguredGateway(DoorGateway):
    configured = False

    def device_status(self, room):
        return "not_configured"

    def verify_proximity(self, room, user, method, proof):
        return False

    def unlock(self, room, user):
        raise RuntimeError("No door hardware integration is configured.")


def gateway():
    path = getattr(settings, "DOOR_GATEWAY", "")
    return import_string(path)() if path else NotConfiguredGateway()


def gateway_for(room):
    """Return the enrolled physical hardware integration for this room."""
    hardware = gateway()
    # The polling gateway is room-specific; other gateway implementations retain
    # their original no-argument construction contract.
    if hasattr(hardware, "for_room"):
        hardware = hardware.for_room(room)
    return hardware


def device_status(room, context):
    """The room's door status, caching the lookups in a serializer `context`."""
    if "gateway" not in context:
        context["gateway"] = gateway()
    selected = context["gateway"]
    if hasattr(selected, "for_room"):
        selected = selected.for_room(room)
    return selected.device_status(room)
