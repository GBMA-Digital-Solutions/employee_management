import hashlib
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from .door_provisioning import ensure_device_for, ensure_door_devices
from .models import Business, DoorDevice, Room


class DoorControllerProvisioningTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Controller Provisioning")

    def room(self, identifier="door-1"):
        return Room.objects.create(
            business=self.business, name=f"Room {identifier}", building="Main",
            floor="1", door_identifier=identifier,
        )

    def test_new_room_automatically_gets_virtual_controller(self):
        room = self.room()
        device = DoorDevice.objects.get(room=room)

        self.assertEqual(device.mode, DoorDevice.VIRTUAL)
        self.assertEqual(device.device_id, f"virtual-room-{room.pk}")
        self.assertEqual(device.secret_hash, "")
        self.assertTrue(device.enabled)

    def test_initialization_is_repeatable_and_backfills_only_missing_rooms(self):
        first = self.room("door-1")
        second = self.room("door-2")
        DoorDevice.objects.filter(room=second).delete()

        self.assertEqual(ensure_door_devices(), 1)
        self.assertEqual(ensure_door_devices(), 0)
        self.assertEqual(DoorDevice.objects.filter(room__in=[first, second]).count(), 2)

        output = StringIO()
        call_command("initialize_door_controllers", stdout=output)
        self.assertIn("created 0 virtual controller(s)", output.getvalue())

    def test_existing_hardware_configuration_is_never_changed(self):
        room = self.room()
        device = DoorDevice.objects.get(room=room)
        secret_hash = hashlib.sha256(b"hardware-secret").hexdigest()
        device.device_id = "installed-controller"
        device.mode = DoorDevice.HARDWARE
        device.secret_hash = secret_hash
        device.enabled = False
        device.save()

        returned = ensure_device_for(room)
        device.refresh_from_db()

        self.assertEqual(returned.pk, device.pk)
        self.assertEqual(device.device_id, "installed-controller")
        self.assertEqual(device.mode, DoorDevice.HARDWARE)
        self.assertEqual(device.secret_hash, secret_hash)
        self.assertFalse(device.enabled)

    @patch.dict("os.environ", {"TEST_DOOR_SECRET": "a-local-test-secret"})
    def test_hardware_enrollment_upgrades_virtual_row_without_duplicate(self):
        room = self.room()
        virtual = DoorDevice.objects.get(room=room)

        call_command(
            "enroll_door_device", room.door_identifier,
            device_id="real-door-1", secret_env="TEST_DOOR_SECRET", stdout=StringIO(),
        )
        virtual.refresh_from_db()

        self.assertEqual(DoorDevice.objects.filter(room=room).count(), 1)
        self.assertEqual(virtual.mode, DoorDevice.HARDWARE)
        self.assertEqual(virtual.device_id, "real-door-1")
        self.assertEqual(
            virtual.secret_hash, hashlib.sha256(b"a-local-test-secret").hexdigest(),
        )

    def test_virtual_controller_is_rejected_by_signed_hardware_endpoint(self):
        room = self.room()
        device = DoorDevice.objects.get(room=room)
        path = f"/api/door-devices/{device.device_id}/poll/"

        response = self.client.post(path, HTTP_X_DOOR_TIMESTAMP="1", HTTP_X_DOOR_NONCE="nonce",
                                    HTTP_X_DOOR_SIGNATURE="0" * 64)

        self.assertEqual(response.status_code, 401)
