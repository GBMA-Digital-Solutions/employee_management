# Physical ESP-IDF maglock controller

Native ESP-IDF firmware for a real ESP32 connected to the Employee Management
Door Device API. It polls for authorized unlock commands, energizes the relay,
acknowledges `executing`, relocks locally after the server-provided duration,
and acknowledges `completed`.

There is no simulator in this path. Django authorizes the employee and queues a
one-use command; the board only ever collects commands that were already
authorized, and it signs every request with its enrolled secret.

The firmware is split into normal ESP-IDF components rather than one large
`main` file:

- `door_wifi`: Wi-Fi connection, reconnection and SNTP clock synchronization.
- `door_api`: signed polling and acknowledgement over one kept-alive connection.
- `maglock`: relay GPIO, status LED and lock/unlock polarity.
- `door_controller`: safe command execution and automatic relocking.
- `main`: starts the controller component only.

## Hardware

Any ESP32 development board with a USB-serial bridge. The board this was
verified against is an ESP32-D0WD-V3 DevKit with a Silicon Labs CP210x bridge,
4 MB of flash, which Windows presents as `COM6`.

Two things about the radio are worth knowing before you configure anything:

- The ESP32 has **no 5 GHz radio**. It can only join a 2.4 GHz network.
- The board and the Django server must be able to reach each other. A campus or
  guest network usually isolates clients from one another, so a local backend
  is easiest to reach over the computer's own Mobile Hotspot.

## 1. Enroll the device

From `backend/`, with the room already created in Access Control and its door
identifier set to `door-101`:

```powershell
$env:DOOR_DEVICE_SECRET='replace-with-a-long-random-secret'
python manage.py enroll_door_device door-101 --device-id door-101
Remove-Item Env:DOOR_DEVICE_SECRET
```

Leave `DOOR_DEVICE_SECRET` unset and the command generates a secret and prints
it once. Django stores only its SHA-256, so a lost secret means re-enrolling.
Keep it out of Git, screenshots and frontend code.

## 2. Decide which API the board talks to

**The deployed API** needs no local network at all, so the board works from any
2.4 GHz Wi-Fi with Internet access. Enroll the device against the deployed
database and keep the default base URL.

**A local Django** has to be reachable from the board:

```powershell
# In Windows Settings, turn on Mobile Hotspot, then from backend/
python manage.py runserver 0.0.0.0:8000
```

The hotspot gateway is `192.168.137.1`, so the base URL becomes
`http://192.168.137.1:8000` and `ALLOWED_HOSTS` in `backend/.env` must contain
`192.168.137.1`, or Django answers 400 DisallowedHost with an HTML page that
the firmware prints to the serial monitor.

## 3. Configure, build and flash

```powershell
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
cd esp-idf-door
idf.py menuconfig
```

Open **Employee Management Door** and set the Wi-Fi SSID and password, the API
base URL, the device ID and the secret from step 1. The build refuses to start
while the SSID or the secret is empty: an empty Kconfig string is a
compile-time constant, so the optimizer would otherwise delete the controller
task, the Wi-Fi stack and the HTTP client, and produce firmware that boots
cleanly and can never open anything.

```powershell
idf.py build
idf.py -p COM6 flash monitor
```

`sdkconfig.defaults` holds the build settings (4 MB flash, the large
single-app partition table, the certificate bundle for HTTPS).
`idf.py menuconfig` writes your values to `sdkconfig`, which is untracked, so
the secret never reaches Git. Leave the monitor with `Ctrl+]`.

## 4. What working looks like

```
I (...) door_controller: Door device door-101 -> http://192.168.137.1:8000
I (...) door_controller: Relay GPIO 23 unlocks low, status LED GPIO 2, polling every 400 ms
I (...) maglock: LOCKED
I (...) door_wifi: Joining "your-ssid"
I (...) door_wifi: Connected, IP=192.168.137.42
I (...) door_wifi: Clock synchronization ready
```

The board then polls quietly. Unlock the room from the employee app and the
monitor shows the whole exchange:

```
I (...) door_api: Unlock command 4f1c... for 5000 ms
I (...) maglock: UNLOCKED
I (...) door_api: ACK executing accepted
I (...) maglock: LOCKED
I (...) door_api: ACK completed accepted
```

GPIO 2 is the on-board LED of a DevKit V1, so a bare board with nothing wired
to it still shows every unlock. Set the status LED GPIO to -1 in `menuconfig`
to disable it.

## Reading failures

- `Disconnected from "..." , reason 201` is no such network in range, which on
  this chip usually means the network is 5 GHz only.
- `reason 15` or `reason 204` is a wrong password.
- `Poll -> HTTP 401` means the signature was refused: the device ID, the secret
  or the board clock does not match what Django has. Re-enroll and set the new
  secret.
- `Poll -> HTTP -1` with no body is a transport failure: wrong base URL, Django
  not listening on `0.0.0.0`, or a firewall between the board and the computer.
- An HTML body instead of JSON is `ALLOWED_HOSTS` missing the address the board
  used.

Repeated poll failures are logged once and then once every 25 attempts, so the
monitor stays readable while a problem persists.

## Relay and maglock

The default signal is GPIO 23 with active-low unlock: GPIO HIGH means locked
and GPIO LOW energizes the unlock relay. Change the GPIO or polarity in
`menuconfig` if the relay board differs. Use a relay or MOSFET driver rated for
the maglock; never power the lock directly from an ESP32 pin. Add the lock
manufacturer's required flyback/surge protection and use a suitable external
power supply.

The firmware forces the logical locked state at boot and whenever Wi-Fi drops,
and it always relocks locally after the unlock interval. Whether a real door is
fail-safe or fail-secure during loss of mains power is determined by the lock,
relay contacts, emergency-release circuit and wiring, not by firmware.
