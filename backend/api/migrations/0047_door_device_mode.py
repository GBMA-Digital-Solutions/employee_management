from django.db import migrations, models


def mark_enrolled_devices_as_hardware(apps, schema_editor):
    """Anything enrolled before this migration holds a real secret, so it keeps
    its hardware powers. Only rows created from here on default to virtual."""
    DoorDevice = apps.get_model("api", "DoorDevice")
    DoorDevice.objects.exclude(secret_hash="").update(mode="hardware")


def provision_existing_rooms(apps, schema_editor):
    """Backfill missing rows without changing any existing controller."""
    Room = apps.get_model("api", "Room")
    DoorDevice = apps.get_model("api", "DoorDevice")
    for room in Room.objects.filter(door_device__isnull=True).order_by("pk").iterator():
        base_id = f"virtual-room-{room.pk}"
        for suffix in ("", *(f"-{number}" for number in range(2, 101))):
            device_id = f"{base_id}{suffix}"
            if not DoorDevice.objects.filter(device_id=device_id).exists():
                DoorDevice.objects.create(
                    room=room, device_id=device_id, mode="virtual", secret_hash="",
                    enabled=True, relay_locked=True,
                )
                break
        else:
            raise RuntimeError(f"Could not allocate a virtual controller id for room {room.pk}")


def back_to_single_mode(apps, schema_editor):
    """Reversing only drops the distinction; no device loses its secret."""


class Migration(migrations.Migration):
    dependencies = [("api", "0046_door_devices")]

    operations = [
        migrations.AddField(
            model_name="doordevice",
            name="mode",
            field=models.CharField(
                max_length=10, default="virtual",
                choices=[("virtual", "Virtual (browser-only simulation)"),
                         ("hardware", "Enrolled hardware controller")],
            ),
        ),
        migrations.AlterField(
            model_name="doordevice",
            name="secret_hash",
            field=models.CharField(max_length=64, blank=True),
        ),
        migrations.RunPython(mark_enrolled_devices_as_hardware, back_to_single_mode),
        migrations.RunPython(provision_existing_rooms, migrations.RunPython.noop),
    ]
