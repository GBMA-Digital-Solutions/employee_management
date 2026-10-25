# Physical ESP32 door integration

A real ESP32 drives the maglock relay for one room. The firmware lives in
[esp-idf-door/](../esp-idf-door/), which also documents the board side; this
page covers the Django side and the end-to-end test.

Nothing is simulated. An authenticated employee asks Django to open a room;
Django checks identity, employment approval and the room grant, then queues a
one-use `DoorUnlockCommand` that expires in seconds. The board polls for
already-authorized commands and can never create one. GPIO 23 is active-low by
default: HIGH is locked, LOW energizes the unlock relay.

## Local setup (PowerShell)

From the repository root:

```powershell
cd backend
..\env\Scripts\Activate.ps1
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

In a second terminal:

```powershell
cd frontend
npm run dev -- --host 0.0.0.0
```

Set these values in `backend/.env`:

```dotenv
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.137.1
DOOR_GATEWAY=api.door_gateway.PhysicalDoorGateway
DOOR_COMMAND_TTL_SECONDS=8
DOOR_DEVICE_OFFLINE_SECONDS=10
DOOR_SIGNATURE_WINDOW_SECONDS=60
```

`ALLOWED_HOSTS` has to contain the address the board uses to reach Django, or
Django answers 400 DisallowedHost with an HTML debug page that the firmware
prints to the serial monitor. `192.168.137.1` is the Windows Mobile Hotspot
gateway, which is the most reliable way to let a board reach a server on this
computer; add your own LAN address instead if the board joins an existing
network that does not isolate its clients.

Without `DOOR_GATEWAY`, `gateway()` falls back to `NotConfiguredGateway` and
every unlock stops with "Door hardware integration is not configured", so no
command is ever queued.

## Enroll the room

The room must already exist in Access Control with its door identifier set.
Let the command generate a secret, or supply one in a temporary environment
variable:

```powershell
$env:DOOR_DEVICE_SECRET='use-a-long-random-local-test-secret'
python manage.py enroll_door_device door-101 --device-id door-101
Remove-Item Env:DOOR_DEVICE_SECRET
```

Django stores only the SHA-256 of the secret, so it cannot show it again.
Put the same device ID and secret into the firmware with `idf.py menuconfig`,
which writes them to the untracked `sdkconfig`. Re-running the command rotates
the secret, which immediately invalidates a board still holding the old one.

Every room also gets a *virtual* controller automatically. A virtual controller
holds no secret and is refused by the signed device endpoints, so it can never
stand in for enrolled hardware.

## How a request is authenticated

The board signs each `POST` with HMAC-SHA256 over

```
POST\n<path>\n<timestamp>\n<nonce>\n<sha256 of the body>
```

keyed by the raw SHA-256 digest of the device secret, and sends
`X-Door-Timestamp`, `X-Door-Nonce` and `X-Door-Signature`. Django rejects a
timestamp outside `DOOR_SIGNATURE_WINDOW_SECONDS`, and caches each nonce for
twice that window so a captured request cannot be replayed. This is why the
firmware waits for SNTP before it signs anything.

## Test

1. Start Django and the frontend, and flash the board as described in
   [esp-idf-door/README.md](../esp-idf-door/README.md).
2. Wait for `Clock synchronization ready` in the serial monitor. The board is
   now polling and `maglock: LOCKED` was printed at boot.
3. Sign in as the employer and open Access Control. The enrolled room reports
   the controller `online`; it drops to `offline` after
   `DOOR_DEVICE_OFFLINE_SECONDS` without a poll.
4. Sign in as an employee with an approved contract and a grant for that room,
   and unlock it from the employee workspace.
5. Django records a granted attempt with unlock status `unconfirmed` and queues
   the command. Within one poll interval the board sets GPIO 23 LOW, lights the
   status LED and acknowledges `executing`, which flips the attempt to
   `confirmed` and the device to relay-unlocked.
6. After the unlock duration the board returns GPIO 23 HIGH, clears the LED and
   acknowledges `completed`, and the device reads as relay-locked again.
7. Check the access history on both the employee and employer screens.
8. An employee without a grant must be denied with no `DoorUnlockCommand`
   created at all. An offline board must answer 502 with no command queued.

## Safety

The firmware forces the locked level at boot and whenever Wi-Fi drops, and it
always relocks locally after the unlock interval even if the network never
comes back. That is controller logic only. Whether a real door is fail-safe or
fail-secure during loss of mains power depends on the installed lock, its relay
contacts, its emergency-release circuit, its wiring and its power supply.
Software cannot guarantee the physical safety mode. Drive the maglock through a
relay or MOSFET rated for it, never from an ESP32 pin directly, and fit the
surge protection the lock manufacturer requires.
