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
class PhysicalDoorBase(APITestCase):
    """An enrolled hardware door, its employer, and an employee granted it."""

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


@override_settings(DOOR_GATEWAY=GATEWAY, DOOR_COMMAND_TTL_SECONDS=8,
                   DOOR_DEVICE_OFFLINE_SECONDS=10, DOOR_SIGNATURE_WINDOW_SECONDS=60)
class PhysicalDoorTests(PhysicalDoorBase):
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



@override_settings(DOOR_GATEWAY=GATEWAY, DOOR_COMMAND_TTL_SECONDS=8,
                   DOOR_DEVICE_OFFLINE_SECONDS=10, DOOR_SIGNATURE_WINDOW_SECONDS=60)
class PrintedDoorQrTests(PhysicalDoorBase):
    """The printed QR names the room and shows the employee stood at its door."""

    def qr_url(self):
        return f"/api/access-control/rooms/{self.room.pk}/qr/"

    def issued_payload(self):
        self.client.force_authenticate(self.employer)
        response = self.client.get(self.qr_url())
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_employer_issues_a_payload_and_can_reissue_a_different_one(self):
        first = self.issued_payload()
        self.room.refresh_from_db()
        self.assertEqual(first["payload"], f"employee-door:{self.room.pk}:{self.room.door_qr_token}")
        self.assertEqual(first["door_identifier"], "door-101")

        # A second GET is stable, so reprinting the same sign keeps working.
        self.assertEqual(self.issued_payload()["payload"], first["payload"])

        # POST retires the old printout.
        reissued = self.client.post(self.qr_url())
        self.assertEqual(reissued.status_code, 200)
        self.assertNotEqual(reissued.data["payload"], first["payload"])

    def test_employee_cannot_read_the_token(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.qr_url()).status_code, 403)
        # Nor does it leak through the room list the employee does see.
        rooms = self.client.get("/api/me/rooms/")
        self.assertEqual(rooms.status_code, 200)
        self.assertNotIn("door_qr_token", rooms.data[0])

    def unlock_by_qr(self, proof):
        RoomAccessGrant.objects.get_or_create(room=self.room, employee=self.employee)
        self.client.force_authenticate(self.user)
        return self.client.post(f"/api/access-control/rooms/{self.room.pk}/unlock/", {
            "access_method": "qr", "proximity_proof": proof,
        }, format="json")

    def test_scanning_the_printed_code_unlocks_and_a_wrong_one_does_not(self):
        token = self.issued_payload()["payload"].split(":")[2]

        granted = self.unlock_by_qr(token)
        self.assertEqual((granted.status_code, granted.data["result"]), (200, "granted"))
        self.assertEqual(RoomAccessAttempt.objects.get().access_method, "qr")
        self.assertEqual(DoorUnlockCommand.objects.count(), 1)

        DoorUnlockCommand.objects.all().delete()
        RoomAccessAttempt.objects.all().delete()
        denied = self.unlock_by_qr("not-the-printed-token")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(RoomAccessAttempt.objects.get().denial_reason, "proximity_failed")
        self.assertFalse(DoorUnlockCommand.objects.exists())

    def test_a_room_with_no_printed_code_refuses_every_qr_unlock(self):
        self.room.refresh_from_db()
        self.assertEqual(self.room.door_qr_token, "")
        self.assertEqual(self.unlock_by_qr("").status_code, 403)
        self.assertEqual(self.unlock_by_qr("guessed").status_code, 403)
