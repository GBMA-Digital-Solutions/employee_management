"""Model signals. Imported from ApiConfig.ready(), including under tests."""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Room

logger = logging.getLogger("api")


@receiver(post_save, sender=Room, dispatch_uid="api.provision_door_device")
def provision_door_device(sender, instance, created, **kwargs):
    """Give every new room a virtual controller as soon as it is saved.

    Only on creation: saving an existing room must never disturb a controller
    someone enrolled against it. Provisioning failures are logged rather than
    raised, because a controller is a convenience and must not block an
    employer from creating a room.
    """
    if not created:
        return
    from .door_provisioning import ensure_device_for
    try:
        ensure_device_for(instance)
    except Exception:
        logger.exception("Could not provision a door controller for room %s", instance.pk)
