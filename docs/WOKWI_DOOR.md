# Wokwi ESP32 door integration

The rotating QR simulator remains the proximity check. Django authorizes the employee and queues a one-use command; the ESP32 only polls for already-authorized commands. GPIO 23 is active-low by default: HIGH is locked/LED on, LOW is unlocked/LED off.

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
ALLOWED_HOSTS=localhost,127.0.0.1,host.wokwi.internal
DOOR_GATEWAY=api.wokwi_gateway.WokwiPollingGateway
DOOR_COMMAND_TTL_SECONDS=8
DOOR_DEVICE_OFFLINE_SECONDS=10
DOOR_SIGNATURE_WINDOW_SECONDS=60
```

Enroll the room after it exists in Access Control. Let the command generate a secret, or put one in a temporary environment variable:

```powershell
$env:WOKWI_DEVICE_SECRET='use-a-long-random-local-test-secret'
python manage.py enroll_door_device door-101 --device-id door-101
Remove-Item Env:WOKWI_DEVICE_SECRET
```

Copy `wokwi/secrets.h.example` to `wokwi/secrets.h` and insert the same device ID and secret. `secrets.h` is ignored by Git. Never paste the secret into `diagram.json`, frontend code, screenshots, or commits.

## Wokwi

Use the `wokwi` folder as a PlatformIO project, build it, and start it with Wokwi for VS Code. It includes the private gateway needed for `host.wokwi.internal`. For browser Wokwi, install/run the Private IoT Gateway, enable it from the command palette, then copy/upload `sketch.ino`, `diagram.json`, `libraries.txt`, and the untracked `secrets.h` to the project.

The public Wokwi gateway cannot reach a service on your Windows computer. The browser Private IoT Gateway requires a paid Wokwi plan. Wokwi for VS Code includes a private gateway. Use Chrome, Edge, or Firefox; the browser private gateway is not supported in Safari.

## Test

1. Start Django and the frontend.
2. Start Wokwi and wait for `ESP32 online; maglock LED ON (locked)` in Serial Monitor.
3. Sign in as the employer, open Access Control / Door Simulator, select the enrolled room, and start it.
4. Confirm the page reports ESP32 `online` and `Locked (LED on)`.
5. On a phone, open the frontend using an HTTPS URL or secure local setup, sign in as an employee with an approved contract and a grant for the room, then select the room.
6. Press **Scan QR to unlock** and scan the rotating QR on the employer screen.
7. Django authorizes the scan and queues a command. The ESP32 sets GPIO 23 LOW, the LED turns off, and it acknowledges `executing`.
8. The employer page reports the relay unlocked and command confirmed. After five seconds GPIO 23 returns HIGH, the LED turns on, and the ESP32 acknowledges `completed`.
9. Verify the employee/employer access history. An unauthorized employee should receive a denial and no `DoorUnlockCommand` is created.

The firmware starts and resets GPIO 23 to the simulated locked state and relocks locally after five seconds even if the network fails. This is only simulator/controller logic. A physical maglock's power-loss behavior depends on whether the installed lock is fail-safe or fail-secure, its relay wiring, and its power supply; software cannot guarantee the physical safety mode.
