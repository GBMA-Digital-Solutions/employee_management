# Employee Management System

A multi-tenant employee management platform. One deployment serves many
companies: each company's employer runs their own workspace, their employees
reach only their own records, and a single platform owner (super admin) manages
the companies themselves.

The stack is a React frontend (Vite), a Django REST Framework backend,
PostgreSQL, and JWT authentication. An optional Wokwi-simulated ESP32 door
controller can be driven from the Access Control screens.

## Contents

- [What you get](#what-you-get)
- [Requirements](#requirements)
- [1. Clone the repository](#1-clone-the-repository)
- [2. Create the virtual environment](#2-create-the-virtual-environment)
- [3. Install backend dependencies](#3-install-backend-dependencies)
- [4. Create the PostgreSQL database](#4-create-the-postgresql-database)
- [5. Configure backend/.env](#5-configure-backendenv)
- [6. Migrate and create the admin](#6-migrate-and-create-the-admin)
- [7. Install frontend dependencies](#7-install-frontend-dependencies)
- [8. Run the project](#8-run-the-project)
- [Roles](#roles)
- [API documentation](#api-documentation)
- [Tests](#tests)
- [Vercel and Render](#vercel-and-render)
- [Wokwi ESP32 door](#wokwi-esp32-door)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)

## What you get

**Super admin (platform owner).** Platform dashboard with company counts,
employer and employee totals, usage over today / 7 days / 30 days, and a
12-month growth chart. Company lifecycle (create a company with its employer,
change status between pending, active and suspended, or delete it). Account
issue reports, live platform health (database ping, email sender state, disk
usage), and two-way messaging with any company.

**Employer (company workspace).** Employees, contracts (draft, send for
signature, approve, terminate), attendance and shifts, leave requests and yearly
allocations, company holidays, announcements, a company calendar, salaries,
payroll and payslips, access control for rooms and doors, activity monitoring,
and a reports roll-up.

**Employee.** Own profile, attendance clock-in and clock-out, leave requests,
contract signing, announcements, company calendar, payroll view, and door
unlocking by QR scan where access has been granted.

Employees reach the workspace only after their employer approves their signed
contract. The super admin never sees a company's attendance, leave, payroll,
contracts, salaries, holidays or announcements.

## Requirements

Install these before you start:

- Python 3.12 is what deployment pins (`.python-version`). Local development is
  currently running 3.10, and either works.
- Node.js 20 or newer (this project has been run on v22).
- PostgreSQL 14 or newer, running locally.
- Git.

Optional, only for the simulated door:

- Visual Studio Code with the PlatformIO IDE and Wokwi for VS Code extensions.

All commands below are PowerShell on Windows, which is the environment this
project is developed in. On macOS or Linux the only differences are the virtual
environment activation line and the path separators.

## 1. Clone the repository

```powershell
git clone <your-repository-url> employee_management
cd employee_management
```

Everything that follows assumes you are in that `employee_management` folder.

## 2. Create the virtual environment

The virtual environment lives at the repository root, in a folder named `env`.
Several scripts and docs assume that name and location.

```powershell
py -3 -m venv env
.\env\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

On macOS or Linux:

```bash
python3 -m venv env
source env/bin/activate
python -m pip install --upgrade pip
```

If PowerShell refuses to run the activation script, allow local scripts once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 3. Install backend dependencies

Note the path: the requirements file sits inside the inner `backend` package,
not at the top of the `backend` folder.

```powershell
python -m pip install -r backend\backend\requirements.txt
```

That installs Django 5.2, Django REST Framework, SimpleJWT, drf-spectacular,
psycopg2-binary, Pillow, whitenoise, gunicorn, django-storages and the rest.

## 4. Create the PostgreSQL database

Create a database and a user that owns it. Using `psql` as the postgres
superuser:

```sql
CREATE DATABASE employee_management;
CREATE USER employee_app WITH PASSWORD 'choose-a-local-password';
GRANT ALL PRIVILEGES ON DATABASE employee_management TO employee_app;
ALTER DATABASE employee_management OWNER TO employee_app;
```

If you intend to run the test suite against PostgreSQL rather than the bundled
SQLite test settings, also grant the ability to create databases:

```sql
ALTER USER employee_app CREATEDB;
```

## 5. Configure backend/.env

Copy the template and edit it. This file is git-ignored and must never be
committed.

```powershell
Copy-Item backend\.env.example backend\.env
```

The values that matter for a first run:

```dotenv
DB_NAME=employee_management
DB_USER=employee_app
DB_PASSWORD=the-password-you-chose
DB_HOST=127.0.0.1
DB_PORT=5432

FRONTEND_URL=http://localhost:5173
```

Notes on the rest of the file:

- `DEBUG` defaults to true locally, so you do not need to set it. Set
  `DEBUG=false` only with a real `SECRET_KEY`, or startup will refuse to run.
- `ALLOWED_HOSTS` defaults to `localhost,127.0.0.1,[::1]`. Add
  `host.wokwi.internal` to it if you are using the Wokwi door, otherwise the
  ESP32 is answered with a 400 page instead of JSON.
- Email is optional. Leave `EMAIL_HOST` and `BREVO_API_KEY` blank and invitation
  emails are simply not sent. Set `BREVO_API_KEY` to send over HTTPS instead of
  SMTP, which helps on hosts that block outbound SMTP.
- `DATABASE_URL` overrides the five `DB_*` values if you prefer a single
  connection string.

The frontend has its own `frontend/.env.example`, but you do not need it for
development. The dev server proxies `/api` to `http://127.0.0.1:8000` through
`frontend/vite.config.js`. Copy it to `frontend/.env` and set `VITE_API_URL`
only when you build or preview the frontend as static assets.

## 6. Migrate and create the admin

```powershell
cd backend
python manage.py migrate
```

Migration `0047` adds an idempotent virtual ESP32 controller to every existing
room that does not already have a controller. Every room created later gets one
automatically. No simulated door enrollment step is required. To audit/repair
this invariant at any time, run the same safe command that Render runs at
startup:

```powershell
python manage.py initialize_door_controllers
```

It only creates missing virtual controllers. It never changes or deletes an
existing virtual or hardware controller, its secret, or any business data.

Then create the platform super admin. `seed` is idempotent and also creates the
Managers group, so it is safe to re-run.

```powershell
$env:PLATFORM_ADMIN_PASSWORD='choose-a-strong-password'
python manage.py seed
Remove-Item Env:PLATFORM_ADMIN_PASSWORD
```

That gives you an account with username `admin`. You can also set
`PLATFORM_ADMIN_PASSWORD` in `backend/.env` instead, but remove it once the
account exists.

## 7. Install frontend dependencies

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
```

## 8. Run the project

Two terminals, both left running.

Backend (from `backend`, with the virtual environment active):

```powershell
python manage.py runserver 0.0.0.0:8000
```

Frontend (from `frontend`):

```powershell
npm run dev -- --host 0.0.0.0
```

Then open:

- App: http://localhost:5173/
- API root: http://localhost:8000/api/
- Health check: http://localhost:8000/api/health/
- Django admin: http://localhost:8000/admin/
- API docs: http://localhost:8000/api/docs/

`--host 0.0.0.0` on both makes the app reachable from a phone on the same
network, which you need for scanning door QR codes. Use the Network URL that
Vite prints, for example `http://10.0.0.5:5173/`.

Sign in as `admin` to reach the platform dashboard, create a company and its
employer, then sign in as that employer to build out employees, contracts and
rooms.

## Roles

| Role | Reaches | Created by |
|---|---|---|
| Super admin | Platform dashboard, companies, employers, platform messaging | `python manage.py seed` |
| Employer | One company workspace and everything inside it | Super admin, when creating a company |
| Employee | Own records only, after contract approval | Employer, by invitation |

## API documentation

The schema is generated from the live views and serializers by
drf-spectacular, so it stays in step with the code.

- Swagger UI: http://localhost:8000/api/docs/
- ReDoc: http://localhost:8000/api/redoc/
- Raw schema: http://localhost:8000/api/schema/
- Written guide: `docs/API.md`

To call protected endpoints from Swagger, POST your credentials to
`/api/token/`, copy the `access` token, and paste it into Authorize as
`Bearer <token>`.

## Tests

The default test runner needs permission to create a PostgreSQL database. If
your database user does not have `CREATEDB`, use the bundled test settings,
which run against in-memory SQLite instead:

```powershell
python manage.py test --settings=backend.test_settings
```

Otherwise:

```powershell
python manage.py test
```

Frontend linting:

```powershell
cd frontend
npm run lint
```

The production frontend build is:

```powershell
npm run build
```

## Vercel and Render

Deploy the backend first. Render must use `backend` as the Root Directory,
`bash build.sh` as the Build Command, `bash start.sh` as the Start Command, and
`/api/health/` as its health check. `start.sh` migrates the database and runs
the repeatable controller initializer before starting Gunicorn. This preserves
all existing doors, employees, contracts, payroll records, and enrolled
controller settings while filling only missing virtual controllers.

Required Render environment variables:

```dotenv
DEBUG=false
SECRET_KEY=<long-random-production-secret>
DATABASE_URL=<Render-PostgreSQL-connection-string>
FRONTEND_URL=https://<your-vercel-site>
CORS_ALLOWED_ORIGINS=https://<your-vercel-site>
ALLOWED_HOSTS=<your-render-hostname>.onrender.com
```

Optional backend variables are `BREVO_API_KEY` and `DEFAULT_FROM_EMAIL` for
email, plus the three `DOOR_*_SECONDS` values documented in
`backend/.env.example`. Set
`DOOR_GATEWAY=api.wokwi_gateway.WokwiPollingGateway` only when an enrolled
ESP32/Wokwi controller should poll this backend. Virtual browser controllers do
not need a gateway or secret.

Vercel must use `frontend` as its Root Directory and set:

```dotenv
VITE_API_URL=https://<your-render-service>.onrender.com
```

Do not append `/api`. Redeploy the frontend after changing it because Vite
embeds the value at build time. Keep all device secrets in Render/local
environment variables or `wokwi/secrets.h`; never use a `VITE_*` variable for a
secret because those values are public in the browser bundle. See
`docs/DEPLOYMENT.md` for the deployment checklist.

## Wokwi ESP32 door

The Door Simulator works immediately in browser-only mode on local, Vercel, and
Render installations. Selecting a room shows the same Connection,
Relay / Maglock, and Last Command fields everywhere; the automatically created
virtual controller follows the browser door state. Wokwi is not required for
this mode, and its simulated commands are clearly labelled rather than being
reported as a physical unlock.

Wokwi is an optional hardware-controller demonstration. Django authorizes a QR
scan and queues a one-use command; the ESP32 polls only for authorized commands
and signs every request with HMAC-SHA256. A physical/hardware attempt remains
unconfirmed until the signed controller acknowledgement arrives. Virtual
controllers have no secret and are rejected by the device endpoints.

Full detail is in `docs/WOKWI_DOOR.md`. The short path:

**1. Add the door settings to `backend/.env`.**

```dotenv
ALLOWED_HOSTS=localhost,127.0.0.1,host.wokwi.internal
DOOR_GATEWAY=api.wokwi_gateway.WokwiPollingGateway
DOOR_COMMAND_TTL_SECONDS=8
DOOR_DEVICE_OFFLINE_SECONDS=10
DOOR_SIGNATURE_WINDOW_SECONDS=60
```

Both of the first two are required. Without `ALLOWED_HOSTS` the ESP32 receives a
Django error page rather than JSON, and without `DOOR_GATEWAY` no unlock command
is ever queued. Restart Django after editing `.env`, because it is read only at
startup.

**2. Create the room in the app**, under Access Control, and note its door
identifier (for example `Door 1`). The room already has a virtual controller;
the next step securely upgrades that same row to hardware rather than creating
a duplicate.

**3. Enroll the device.** The first argument is the room's door identifier, not
the device id. The device id is the `--device-id` option. Getting these the
wrong way round fails with `door_identifier must match exactly one room`.

```powershell
$env:WOKWI_DEVICE_SECRET='a-long-random-local-secret'
python manage.py enroll_door_device "Door 1" --device-id "door-101"
Remove-Item Env:WOKWI_DEVICE_SECRET
```

If you leave `WOKWI_DEVICE_SECRET` unset, the command generates a secret and
prints it once. Only the SHA-256 derivation is stored, so a lost secret means
re-enrolling.

**4. Create `wokwi/secrets.h`** from the example and paste in the same device id
and secret. The file is git-ignored and must stay that way.

```powershell
Copy-Item wokwi\secrets.h.example wokwi\secrets.h
```

**5. Build the firmware.** PlatformIO Core ships inside the PlatformIO IDE
extension but is not always on PATH. If `pio` is not recognised, either restart
VS Code completely so it picks up the PATH entry the extension added, or prefix
it for the current session:

```powershell
$env:Path = "$env:USERPROFILE\.platformio\penv\Scripts;$env:Path"
cd wokwi
pio run
```

**6. Start the simulation** with Wokwi for VS Code, which includes the private
gateway that makes `host.wokwi.internal` resolve. Wait for
`ESP32 online; maglock LED ON (locked)` in the serial monitor. The public Wokwi
gateway cannot reach a service on your own machine.

**7. Test it.** Sign in as the employer, open Access Control, start the Door
Simulator for that room, and confirm the page shows the controller online and
locked. On a phone, sign in as an employee who has a grant for that room, choose
the room, and scan the rotating QR code on the employer screen. The LED turns
off for five seconds and the page reports the unlock, then it relocks.

## Project layout

```
employee_management/
├── README.md
├── .python-version                 # Pins 3.12 for deployment platforms
├── backend/
│   ├── manage.py
│   ├── .env.example                # Copy to backend/.env
│   ├── build.sh                    # Deployment build
│   ├── start.sh                    # Deployment start (migrate, seed, gunicorn)
│   ├── backend/
│   │   ├── settings.py
│   │   ├── test_settings.py        # In-memory SQLite, for tests only
│   │   ├── urls.py                 # All routes, including /api/docs/
│   │   ├── health.py               # Public readiness probe
│   │   └── requirements.txt        # Backend dependencies live here
│   └── api/
│       ├── models.py
│       ├── views.py                # Employer workspace viewsets
│       ├── accounts.py             # Auth, account, and /api/me/ endpoints
│       ├── platform.py             # Super admin company management
│       ├── dashboard.py            # Super admin overview and health
│       ├── access_control.py       # Rooms, grants, unlock requests
│       ├── door_device.py          # Signed ESP32 poll and acknowledge endpoints
│       ├── door_hardware.py        # Gateway interface and resolution
│       ├── wokwi_gateway.py        # Polling gateway for the ESP32
│       ├── door_simulator.py       # Rotating QR proximity simulator
│       ├── payroll_views.py        # Payroll and payslips
│       ├── management/commands/    # seed, enroll_door_device, and others
│       └── migrations/
├── frontend/
│   ├── package.json
│   ├── vite.config.js              # Dev proxy: /api -> 127.0.0.1:8000
│   └── src/
│       ├── App.jsx
│       ├── AccountPage.jsx         # Employee workspace
│       ├── ManagerDashboard.jsx    # Employer workspace
│       ├── AccessControl.jsx       # Rooms, doors, simulator
│       └── api.js                  # Every API call, with JWT refresh
├── wokwi/
│   ├── sketch.ino                  # ESP32 firmware
│   ├── platformio.ini
│   ├── diagram.json                # Wokwi wiring
│   └── secrets.h.example           # Copy to secrets.h (git-ignored)
└── docs/
    ├── API.md
    ├── DEPLOYMENT.md
    └── WOKWI_DOOR.md
```

## Troubleshooting

**`manage.py` cannot connect to the database.** Confirm PostgreSQL is running
and that the five `DB_*` values in `backend/.env` match the database and user
you created. A missing `backend/.env` produces a `KeyError` on `DB_NAME`,
because those settings are read with `os.environ[...]` and have no defaults.

**Changes to `.env` seem ignored.** The file is read once at startup and the
autoreloader does not watch it. Stop the server and start it again.

**The Wokwi terminal prints HTML instead of status lines.** `host.wokwi.internal`
is missing from `ALLOWED_HOSTS`, so Django is returning its debug error page and
the firmware prints the body. Add it and restart Django.

**The door shows offline even though Wokwi is running.** Every poll is failing
authentication, so `last_seen_at` never updates. The usual cause is clock drift:
the simulated ESP32 clock falls behind real time until the signed timestamp
falls outside `DOOR_SIGNATURE_WINDOW_SECONDS`. Restart the simulation to resync
its clock, or widen that window.

**Scanning returns 502.** That is the application's own response, not a server
failure. `RoomUnlockView` returns 502 when the door controller cannot be
reached, which means the device is offline. Access is still recorded as granted
with a failed unlock.

**`pio` is not recognised.** PlatformIO Core is installed with the IDE extension
at `%USERPROFILE%\.platformio\penv\Scripts`, but an already-open terminal holds
the PATH from before the extension was installed. Restart VS Code fully, or
prepend that folder for the session.

**Port 8000 is already in use.** Check for an older `runserver` still holding
it. Running two Django servers on the same port makes which one answers a given
request unpredictable on Windows.
