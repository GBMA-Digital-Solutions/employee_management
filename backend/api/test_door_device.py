import hashlib
import hmac
import json
import time
import uuid
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import (AccountProfile, Business, Contract, DoorDevice, DoorUnlockCommand,
                     Employee, Room, RoomAccessAttempt, RoomAccessGrant)


GATEWAY = "api.door_gateway.PhysicalDoorGateway"


@override_settings(DOOR_GATEWAY=GATEWAY, DOOR_COMMAND_TTL_SECONDS=8,
                   DOOR_DEVICE_OFFLINE_SECONDS=10, DOOR_SIGNATURE_WINDOW_SECONDS=60)
class PhysicalDoorTests(APITestCase):
    raw_secret = "local-test-secret-not-for-production"

    def setUp(self):
        cache.clear()
        business = Business.objects.create(name="Door Test")
        self.employer = User.objects.create_user("boss", "boss@example.com", "password")
        AccountProfile.objects.create(user=self.employer, role="employer", business=business)
        self.employee = Employee.objects.create(business=business, first_name="A", last_name="User",
                                                email="a@example.com", job_title="Tester", date_joined=date.today())
        self.employee.is_active = True
        self.employee.save(update_fields=["is_active"])
        self.user = User.objects.create_user("employee", "a@example.com", "password")
        AccountProfile.objects.create(user=self.user, role="employee", employee=self.employee)
        Contract.objects.create(employee=self.employee, title="Employment", start_date=date.today(),
                                signature_status="signed", worker_approval_status="approved")
        self.room = Room.objects.create(business=business, name="Lab", building="Main", floor="1",
                                        door_identifier="door-101")
        # Creating the room already provisioned a virtual controller, so enroll
        # over that row the way `enroll_door_device` does rather than inserting
        # a second controller for the same room.
        self.device, _ = DoorDevice.objects.update_or_create(room=self.room, defaults={
            "device_id": "door-101", "mode": DoorDevice.HARDWARE,
            "secret_hash": hashlib.sha256(self.raw_secret.encode()).hexdigest(),
            "enabled": True, "relay_locked": True, "last_seen_at": timezone.now(),
        })

    def signed_post(self, path, payload=None, nonce=None, timestamp=None, secret=None):
        body = json.dumps(payload or {}, separators=(",", ":")).encode()
        timestamp = str(timestamp or int(time.time()))
        nonce = nonce or uuid.uuid4().hex
        canonical = b"\n".join([b"POST", path.encode(), timestamp.encode(), nonce.encode(),
                                 hashlib.sha256(body).hexdigest().encode()])
        key = hashlib.sha256((secret or self.raw_secret).encode()).digest()
        signature = hmac.new(key, canonical, hashlib.sha256).hexdigest()
        return self.client.generic("POST", path, body, content_type="application/json",
                                   HTTP_X_DOOR_TIMESTAMP=timestamp, HTTP_X_DOOR_NONCE=nonce,
                                   HTTP_X_DOOR_SIGNATURE=signature)

    def unlock_physical_door(self, grant=True):
        if grant:
            RoomAccessGrant.objects.get_or_create(room=self.room, employee=self.employee)
        self.client.force_authenticate(self.user)
        response = self.client.post(f"/api/access-control/rooms/{self.room.pk}/unlock/", {
            "access_method": "app",
        }, format="json")
        return response

    def test_authorized_scan_queues_then_acknowledgement_confirms(self):
        response = self.unlock_physical_door()
        self.assertEqual((response.status_code, response.data["unlock_status"]), (200, "unconfirmed"))
        command = DoorUnlockCommand.objects.get()
        self.assertIsNotNone(command.access_attempt_id)

        poll = self.signed_post(f"/api/door-devices/{self.device.device_id}/poll/")
        self.assertEqual(poll.status_code, 200, poll.data)
        self.assertEqual((poll.data["command"]["relay_gpio"], poll.data["command"]["duration_ms"]), (23, 5000))
        ack_path = f"/api/door-devices/{self.device.device_id}/commands/{command.pk}/ack/"
        executing = self.signed_post(ack_path, {"status": "executing"})
        self.assertEqual((executing.status_code, executing.data["state"]), (200, "executing"))
        self.assertEqual(RoomAccessAttempt.objects.get().unlock_status, "confirmed")
        self.device.refresh_from_db()
        self.assertFalse(self.device.relay_locked)

        completed = self.signed_post(ack_path, {"status": "completed"})
        self.assertEqual(completed.data["state"], "completed")
        self.device.refresh_from_db()
        self.assertTrue(self.device.relay_locked)

    def test_unauthorized_scan_never_creates_command(self):
        response = self.unlock_physical_door(grant=False)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DoorUnlockCommand.objects.exists())

    def test_device_authentication_replay_and_stale_timestamp(self):
        path = f"/api/door-devices/{self.device.device_id}/poll/"
        nonce = uuid.uuid4().hex
        self.assertEqual(self.signed_post(path, nonce=nonce).status_code, 200)
        self.assertEqual(self.signed_post(path, nonce=nonce).status_code, 401)
        self.assertEqual(self.signed_post(path, secret="wrong").status_code, 401)
        self.assertEqual(self.signed_post(path, timestamp=int(time.time()) - 120).status_code, 401)

    def test_expired_command_is_not_delivered_or_acknowledged(self):
        command = DoorUnlockCommand.objects.create(device=self.device, requested_by=self.user,
                                                   expires_at=timezone.now() - timedelta(seconds=1))
        poll = self.signed_post(f"/api/door-devices/{self.device.device_id}/poll/")
        self.assertIsNone(poll.data["command"])
        command.refresh_from_db()
        self.assertEqual(command.state, "expired")
        ack = self.signed_post(f"/api/door-devices/{self.device.device_id}/commands/{command.pk}/ack/",
                               {"status": "executing"})
        self.assertEqual(ack.status_code, 410)

    def test_missing_ack_stays_unconfirmed_and_offline_device_does_not_queue(self):
        response = self.unlock_physical_door()
        self.assertEqual(response.data["unlock_status"], "unconfirmed")
        command = DoorUnlockCommand.objects.get()
        command.expires_at = timezone.now() - timedelta(seconds=1)
        command.save(update_fields=["expires_at"])
        self.signed_post(f"/api/door-devices/{self.device.device_id}/poll/")
        self.assertEqual(RoomAccessAttempt.objects.get().unlock_status, "unconfirmed")

        DoorUnlockCommand.objects.all().delete()
        self.device.last_seen_at = timezone.now() - timedelta(minutes=1)
        self.device.save(update_fields=["last_seen_at"])
        self.client.force_authenticate(self.user)
        offline = self.client.post(f"/api/access-control/rooms/{self.room.pk}/unlock/", {
            "access_method": "app",
        }, format="json")
        self.assertEqual(offline.status_code, 502)
        self.assertFalse(DoorUnlockCommand.objects.exists())

