import hashlib
import hmac
import json
import time

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import DoorDevice, DoorUnlockCommand


class DeviceThrottle(AnonRateThrottle):
    rate = "300/min"


def authenticated_device(request, device_id):
    device = DoorDevice.objects.filter(device_id=device_id, enabled=True).first()
    timestamp = request.headers.get("X-Door-Timestamp", "")
    nonce = request.headers.get("X-Door-Nonce", "")
    supplied = request.headers.get("X-Door-Signature", "")
    try:
        fresh = abs(int(time.time()) - int(timestamp)) <= getattr(settings, "DOOR_SIGNATURE_WINDOW_SECONDS", 60)
    except (TypeError, ValueError):
        fresh = False
    if (not device or device.mode != DoorDevice.HARDWARE or len(device.secret_hash) != 64 or
            not fresh or not nonce or len(nonce) > 100 or len(supplied) != 64):
        return None
    nonce_key = f"door-nonce:{device.pk}:{nonce}"
    if not cache.add(nonce_key, True, timeout=getattr(settings, "DOOR_SIGNATURE_WINDOW_SECONDS", 60) * 2):
        return None
    body_hash = hashlib.sha256(request.body).hexdigest()
    canonical = "\n".join([request.method.upper(), request.path, timestamp, nonce, body_hash]).encode()
    try:
        key = bytes.fromhex(device.secret_hash)
    except ValueError:
        cache.delete(nonce_key)
        return None
    expected = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied.lower()):
        cache.delete(nonce_key)
        return None
    return device


def unauthorized():
    return Response({"detail": "Device authentication failed."}, status=status.HTTP_401_UNAUTHORIZED)


class DoorDevicePollView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [DeviceThrottle]

    def post(self, request, device_id):
        device = authenticated_device(request, device_id)
        if not device:
            return unauthorized()
        now = timezone.now()
        with transaction.atomic():
            device = DoorDevice.objects.select_for_update().get(pk=device.pk)
            DoorUnlockCommand.objects.filter(device=device, state__in=["created", "pending", "claimed"],
                                             expires_at__lte=now).update(state="expired")
            command = DoorUnlockCommand.objects.select_for_update().filter(
                device=device, state="pending", expires_at__gt=now).first()
            device.last_seen_at = now
            device.save(update_fields=["last_seen_at"])
            if not command:
                return Response({"command": None, "poll_after_ms": 400})
            command.state = "claimed"
            command.claimed_at = now
            command.save(update_fields=["state", "claimed_at"])
        return Response({"command": {"id": str(command.pk), "action": "unlock", "relay_gpio": 23,
                                      "duration_ms": 5000, "expires_at": command.expires_at},
                         "poll_after_ms": 400})


class DoorDeviceAcknowledgeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [DeviceThrottle]

    def post(self, request, device_id, command_id):
        device = authenticated_device(request, device_id)
        if not device:
            return unauthorized()
        try:
            payload = json.loads(request.body or b"{}")
        except (TypeError, ValueError):
            return Response({"detail": "Invalid JSON."}, status=400)
        ack = payload.get("status")
        if ack not in {"executing", "completed", "failed"}:
            return Response({"detail": "status must be executing, completed, or failed."}, status=400)
        now = timezone.now()
        with transaction.atomic():
            command = DoorUnlockCommand.objects.select_for_update().filter(pk=command_id, device=device).first()
            if not command:
                return Response({"detail": "Command not found."}, status=404)
            if command.expires_at <= now and command.state not in {"executing", "completed"}:
                command.state = "expired"
                command.save(update_fields=["state"])
                return Response({"detail": "Command expired."}, status=410)
            if ack == "executing" and command.state == "claimed":
                command.state = "executing"
                command.acknowledged_at = now
                command.save(update_fields=["state", "acknowledged_at"])
                device.relay_locked = False
                device.last_command_id = command.pk
                device.last_acknowledged_at = now
                device.last_seen_at = now
                device.save(update_fields=["relay_locked", "last_command_id", "last_acknowledged_at", "last_seen_at"])
                if command.access_attempt_id:
                    command.access_attempt.unlock_status = "confirmed"
                    command.access_attempt.save(update_fields=["unlock_status"])
            elif ack == "completed" and command.state in {"executing", "completed"}:
                command.state = "completed"
                command.completed_at = command.completed_at or now
                command.save(update_fields=["state", "completed_at"])
                device.relay_locked = True
                device.last_seen_at = now
                device.save(update_fields=["relay_locked", "last_seen_at"])
            elif ack == "failed" and command.state in {"claimed", "executing"}:
                command.state = "failed"
                command.failure_code = str(payload.get("error", "device_failed"))[:80]
                command.save(update_fields=["state", "failure_code"])
                device.relay_locked = True
                device.last_seen_at = now
                device.save(update_fields=["relay_locked", "last_seen_at"])
            else:
                return Response({"detail": "Acknowledgement is not valid for the command state."}, status=409)
        return Response({"accepted": True, "state": command.state})
