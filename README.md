<div align="center">

# ZionhiltPay

**A digital wallet that pays you back on every transaction — and quietly insures your devices while you spend.**

*Powered by Zionhilt · Full-Stack & Security Systems Engineering*

</div>

---

## What is ZionhiltPay?

ZionhiltPay is a full-stack digital wallet built on a real **double-entry ledger**. Every deposit,
transfer, and withdrawal is recorded as a balanced set of debits and credits — the same accounting
discipline real banks and payment processors use — so balances are always auditable and provably
correct.

On top of that ledger, ZionhiltPay layers two things most wallets don't offer:

- **Transaction rewards** — a share of the fee on every transfer/withdrawal comes back to the user
  as cashback, credited automatically to a separate reward wallet.
- **Device insurance, funded by your own spending** — a further share of every fee builds up in a
  personal insurance pool. Register a phone or laptop, and if it's later lost, stolen, or damaged,
  you can file a claim against the coverage you've already accrued — no separate premium payments.

> **Roadmap note — v1.1:** MAC-address based device tracking (to help locate a lost/stolen device)
> is scoped for v1.1. The database schema and device model already include the `mac_address`,
> `last_seen_at`, and `last_seen_location` fields so this ships without a migration later, but no
> tracking logic runs against them in v1.0.

---

## Table of contents

1. [Architecture](#architecture)
2. [Tech stack](#tech-stack)
3. [Getting started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Option A: run it on your local machine (no Docker)](#option-a-run-it-on-your-local-machine-no-docker)
   - [Option B: run it with Docker](#option-b-run-it-with-docker)
4. [Configuration](#configuration)
5. [Troubleshooting](#troubleshooting)
6. [Usage guide](#usage-guide)
7. [How the economics work](#how-the-economics-work)
8. [AI agents](#ai-agents)
9. [Security](#security)
10. [Testing](#testing)
11. [Project structure](#project-structure)
12. [Contributing](#contributing)
13. [Support / donations](#support--donations)
14. [License](#license)

---

## Architecture

```
                                   ┌────────────────────┐
                                   │   React Frontend    │
                                   │  (Vite + Tailwind)  │
                                   └──────────┬───────────┘
                                              │ REST / JSON, JWT bearer auth
                                   ┌──────────▼───────────┐
                                   │    FastAPI Backend    │
                                   │ ─────────────────────  │
                                   │ auth · wallet · devices│
                                   │ admin · fraud · rewards│
                                   └──────────┬───────────┘
                                              │ SQLAlchemy (async)
                                   ┌──────────▼───────────┐
                                   │      PostgreSQL        │
                                   │ double-entry ledger,   │
                                   │ users, devices, audit  │
                                   └────────────────────────┘
```

**The ledger is the core.** `backend/app/services/ledger.py` is the *only* place in the codebase
allowed to change an account balance. Every money movement is posted as a matched set of debit/credit
`ledger_entries` tied to one `transactions` row, and the service refuses to finalize a transaction
whose entries don't sum to zero — so a bug in fee-splitting logic fails loudly instead of silently
corrupting balances.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16, Pydantic v2 |
| Auth | JWT (access + rotating refresh tokens), bcrypt password/PIN hashing |
| Frontend | React 18, Vite, Tailwind CSS, React Router |
| Payments | Mock payment gateway (pluggable — swap in Paystack/Flutterwave/Stripe later) |
| OTP delivery | Console/log by default; pluggable SMTP (email) and Termii/Twilio (SMS) |
| Infra | Docker, Docker Compose, Nginx (frontend static serving) |

---

## Getting started

There are two ways to run ZionhiltPay:

| | **Option A: your local machine** | **Option B: Docker** |
|---|---|---|
| Best for | Day-to-day development and trying the app | A one-command setup that needs no Python/Node/Postgres install |
| You need | Python, Node.js, PostgreSQL | Docker Desktop |
| Jump to | [Option A](#option-a-run-it-on-your-local-machine-no-docker) | [Option B](#option-b-run-it-with-docker) |

### Prerequisites

| Tool | Version | Check it with | Notes |
|---|---|---|---|
| Python | 3.12 or 3.13 (64-bit) | `python --version` | On Windows, tick **"Add python.exe to PATH"** in the installer. You do **not** need Visual Studio or C++ build tools: every dependency installs from prebuilt wheels. |
| Node.js | 18 or newer (tested on 22) | `node --version` | Includes `npm`. |
| PostgreSQL | 14 or newer (tested on 16) | `psql --version` | Remember the password you choose for the `postgres` user during installation. |
| Git | optional | `git --version` | Only needed to clone the repository or apply patches. |

Ports used: **5173** (frontend), **8000** (backend API), **5432** (PostgreSQL). Docker also uses **80**.

You will use **three terminal windows**. Keep the first two open while you work:

| Terminal | What it does |
|---|---|
| 1. Backend | Runs the API. This is also where login/OTP codes are printed in development. |
| 2. Frontend | Runs the website. |
| 3. Spare | One-off commands: creating an admin, running tests. |

> **Run each command on its own line.** If two commands are pasted onto one line, only the first one runs.

---

### Option A: run it on your local machine (no Docker)

#### Step 1: Get the code

Unzip the project and open a terminal in the folder that contains `backend/`, `frontend/` and `db/`.

```bash
cd path/to/zionhiltpay
```

#### Step 2: Create the database

ZionhiltPay needs an **empty PostgreSQL database** and a login for it. You do not need to load any SQL
file: the backend creates every table by itself the first time it starts.

**Windows (PowerShell)**: find your Postgres folder first (the version number may differ from `18`):

```powershell
Get-CimInstance Win32_Service | Where-Object { $_.Name -like '*postgres*' } | Select-Object Name, State, PathName | Format-List
```

Then run this, using the `bin` folder you found. It asks for the **`postgres` password** you set when you
installed PostgreSQL (nothing shows as you type):

```powershell
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
$pw   = "ChooseAPassword123"      # pick your own (letters and digits only)

@"
CREATE USER zp_app WITH PASSWORD '$pw';
CREATE DATABASE zionhiltpay OWNER zp_app;
"@ | Set-Content setup.sql -Encoding ascii
& $psql -U postgres -h localhost -f setup.sql
Remove-Item setup.sql
```

You should see `CREATE ROLE` and `CREATE DATABASE`. (Prefer a GUI? In pgAdmin, create a login role `zp_app`
with a password, then a database `zionhiltpay` owned by it.)

**macOS / Linux**:

```bash
PW='ChooseAPassword123'     # pick your own (letters and digits only)
sudo -u postgres psql -c "CREATE USER zp_app WITH PASSWORD '$PW';"
sudo -u postgres psql -c "CREATE DATABASE zionhiltpay OWNER zp_app;"
```

On macOS with Homebrew, your own user is the Postgres superuser, so use `psql postgres -c "..."` instead of
`sudo -u postgres psql -c "..."`.

> Already have a role or database with these names? Choose different names and use them consistently in
> steps 2 and 3.

#### Step 3: Set up the backend

**Windows (PowerShell)**:

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `activate` says *"running scripts is disabled on this system"*, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and then `venv\Scripts\activate` again.
(In Git Bash use `source venv/Scripts/activate` instead.) If you have several Python versions, create the
environment with `py -3.13 -m venv venv`.

**macOS / Linux**:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Your prompt now starts with `(venv)`. Everything below runs inside this virtual environment.

Now create the settings file, **`backend/.env`**. This writes it for you, including two freshly generated
secrets:

**Windows (PowerShell)**: still inside `backend`, with the environment active:

```powershell
$pw = "ChooseAPassword123"      # the same password you used in step 2

@"
DATABASE_URL=postgresql+asyncpg://zp_app:$pw@localhost:5432/zionhiltpay
SYNC_DATABASE_URL=postgresql+psycopg2://zp_app:$pw@localhost:5432/zionhiltpay
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
DATA_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
"@ | Set-Content .env -Encoding ascii
```

> Use exactly this method on Windows. Creating `.env` with `echo ... > .env`, or saving it from an editor
> as "UTF-8 with BOM" or "UTF-16", makes the app silently ignore the file and fall back to the Docker
> database host `db`.

**macOS / Linux**:

```bash
PW='ChooseAPassword123'     # the same password you used in step 2
cat > .env << EOF
DATABASE_URL=postgresql+asyncpg://zp_app:${PW}@localhost:5432/zionhiltpay
SYNC_DATABASE_URL=postgresql+psycopg2://zp_app:${PW}@localhost:5432/zionhiltpay
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
DATA_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
EOF
```

**Check that it was read.** This must print a URL containing `@localhost:5432`, not `@db`:

```bash
python -c "from app.core.config import settings; print(settings.DATABASE_URL)"
```

> `DATA_ENCRYPTION_KEY` encrypts customers' ID numbers. Back it up: if it is lost, stored IDs cannot be
> decrypted. See [Protecting stored ID numbers](#protecting-stored-id-numbers-do-this-before-real-users-sign-up).

#### Step 4: Start the backend (Terminal 1)

```bash
python -m uvicorn app.main:app --reload
```

When it is ready you will see these two lines:

```
Database schema verified/created; integrity guards installed.
Application startup complete.
```

Check it: open <http://localhost:8000/api/health> (it shows `{"status":"ok", ...}`) and
<http://localhost:8000/docs> (interactive API documentation). **Leave this terminal open.**

#### Step 5: Start the frontend (Terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open **<http://localhost:5173>**. Use `localhost`, not the `172.x.x.x` / `192.168.x.x` "Network" address
Vite prints: the backend only accepts requests from `localhost:5173` (see
[Troubleshooting](#troubleshooting)). If your backend runs on a different address, create
`frontend/.env` containing `VITE_API_BASE_URL=http://localhost:8000` with the right address.

#### Step 6: Create your first admin account (Terminal 3)

There is deliberately **no way to become an admin through the website**. Create one from the command line,
in `backend/` with the virtual environment active:

```bash
python -m scripts.create_admin --email admin@example.com --username zadmin --password "ChangeMe12345" --name "Admin User" --phone 08000000001 --super
```

Use an ordinary-looking email domain such as `example.com`: reserved domains like `.local` are rejected at
login. The command prints the four ways this admin can log in (username, email, phone, account number).
Log in at <http://localhost:5173/login>; the first login asks you to set a transaction PIN. The **Admin**
link then appears in the menu (☰ on a phone). (With Docker, see [Option B](#option-b-run-it-with-docker).)

#### Step 7: Try it out

1. **Register** a customer at <http://localhost:5173/register> (two steps: account details, then ID).
2. **Find the verification code in Terminal 1.** In development nothing is emailed or texted; the backend
   prints the code, on a line like this (the digits are random each time):

   ```
   [EMAIL OTP] To: you@example.com | Purpose: registration | Code: <6 digits>
   ```

   Use the **newest** line. Each "Resend code" creates a new code and cancels the older one, and each code
   allows 5 attempts. To receive real emails/SMS instead, see
   [Sending real OTP emails and SMS](#sending-real-otp-emails-and-sms).
3. **Log in** with the account number shown after verification (or the username, email or phone), then set a
   4 to 6 digit **PIN** (obvious ones such as `1234` or `0000` are refused).
4. **Fund the wallet** (Deposit). It uses a built-in *mock* payment gateway that declines about 1 in 20
   attempts on purpose; just retry.
5. Register a **second customer** and **send money** using the first customer's account number or username.
6. Log in as the **admin** and open **Users & KYC** to review the customers' IDs, **Transactions** to see the
   payments, and **Audit log** for the record of what happened.

The [Usage guide](#usage-guide) describes every screen.

#### Step 8: Everyday commands

**Start again later** (the database and your data are kept):

```powershell
# Terminal 1 (Windows PowerShell)
cd backend
venv\Scripts\activate
python -m uvicorn app.main:app --reload

# Terminal 2
cd frontend
npm run dev
```

```bash
# Terminal 1 (macOS / Linux)
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --reload

# Terminal 2
cd frontend && npm run dev
```

**Stop:** press `Ctrl+C` in each terminal.

**Start over with an empty database** (this deletes all data; stop the backend first):

```powershell
& $psql -U postgres -h localhost -c "DROP DATABASE zionhiltpay;"
& $psql -U postgres -h localhost -c "CREATE DATABASE zionhiltpay OWNER zp_app;"
```

```bash
sudo -u postgres psql -c "DROP DATABASE zionhiltpay;"
sudo -u postgres psql -c "CREATE DATABASE zionhiltpay OWNER zp_app;"
```

**Update to a newer version:** replace the project files (keep your `backend/.env`), then in `backend/` run
`python -m pip install -r requirements.txt`, in `frontend/` run `npm install`, and restart both. The database
upgrades itself on startup.

#### Run the tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

That runs the tests that need no database. To also run the database tests, create a **separate, empty**
test database (never use your real one) and point `TEST_DATABASE_URL` at it. The tests create the tables
themselves:

```bash
sudo -u postgres psql -c "CREATE DATABASE zionhiltpay_test OWNER zp_app;"
PW='ChooseAPassword123'     # the password from step 2
export TEST_DATABASE_URL="postgresql+asyncpg://zp_app:${PW}@localhost:5432/zionhiltpay_test"
python -m pytest tests/ -q
```

On Windows PowerShell, create the database with `CREATE DATABASE zionhiltpay_test OWNER zp_app;` in the same way
as step 2, then run
`$env:TEST_DATABASE_URL = "postgresql+asyncpg://zp_app:$pw@localhost:5432/zionhiltpay_test"` followed by
`python -m pytest tests/ -q`.

---

### Option B: run it with Docker

Requirements: Docker Desktop (running). It starts PostgreSQL, the backend and the frontend together.

```bash
cp backend/.env.example backend/.env        # Windows PowerShell: Copy-Item backend\.env.example backend\.env
docker compose up --build
```

| What | Where |
|---|---|
| Website | <http://localhost> |
| API | <http://localhost:8000> (docs at `/docs`) |
| PostgreSQL | `localhost:5432` (user, password and database: `zionhilt` / `zionhilt` / `zionhiltpay`) |

Create the first admin inside the running backend container:

```bash
docker compose exec backend python -m scripts.create_admin --email admin@example.com --username zadmin --password "ChangeMe12345" --name "Admin User" --phone 08000000001 --super
```

Verification codes are printed in the backend logs: `docker compose logs -f backend`.

Useful commands: `docker compose down` (stop, keeps data) and `docker compose down -v` (stop **and delete the
database**).

**Port already in use?** If you also have PostgreSQL installed on your machine, port `5432` is taken: in
`docker-compose.yml` change the `db` port mapping to `"5433:5432"` (the backend still reaches it internally).
If port `80` is taken, change the frontend mapping to `"8080:80"` and add `"http://localhost:8080"` to the
`CORS_ORIGINS` list under the backend service.

---

## Configuration

Settings are read from environment variables and from `backend/.env`. **A real environment variable
overrides the file.** Defaults are shown; everything marked *required* must be set for production.

| Variable | Default | What it does |
|---|---|---|
| `DATABASE_URL` | `...@db:5432/zionhiltpay` | Async connection string (`postgresql+asyncpg://user:password@host:port/database`). `db` is the Docker hostname, so use `localhost` locally. |
| `SYNC_DATABASE_URL` | `...@db:5432/zionhiltpay` | Same database, `postgresql+psycopg2://` form. |
| `JWT_SECRET_KEY` | placeholder | Signs login tokens. *Required* in production (the app refuses the placeholder). |
| `DATA_ENCRYPTION_KEY` | derived in dev | Encrypts ID numbers. *Required* in production. Back it up. |
| `APP_ENV` | `development` | `production` turns on stricter startup checks and stops OTP codes being written to logs. |
| `CORS_ORIGINS` | `["http://localhost:5173","http://localhost:3000"]` | Websites allowed to call the API, as a JSON list. Replaces the default when set. |
| `EMAIL_PROVIDER`, `SMTP_*`, `EMAIL_FROM` | `console` | Real email delivery. See below. |
| `SMS_PROVIDER`, `SMS_API_KEY`, `SMS_SENDER_ID` | `console` | Real SMS delivery (Termii or Twilio). See below. |
| `ANTHROPIC_API_KEY` | empty | Turns on the AI assistant, insights and admin copilot. Without it they report "not enabled". |
| `AGENT_MODEL` | `claude-sonnet-5-5` | Which Claude model the agents use. |
| `MOCK_GATEWAY_SUCCESS_RATE` | `0.95` | Share of mock deposits/withdrawals that succeed. Set `1.0` to stop random declines. |
| `RATE_LIMIT_AUTH`, `RATE_LIMIT_OTP`, `RATE_LIMIT_LOOKUP`, `RATE_LIMIT_AGENT` | `10/minute`, `5/minute`, `20/minute`, `20/minute` | Request limits per IP. |
| `REWARD_RATE`, `TRANSACTION_FEE_RATE`, `INSURANCE_CONTRIBUTION_RATE`, `WITHDRAWAL_FEE_FLAT` | `0.005`, `0.015`, `0.01`, `25.00` | Default economics (a super admin can change them live under Admin, Config). |

Frontend: `VITE_API_BASE_URL` (default `http://localhost:8000`) in `frontend/.env`, read when the dev server starts.

### Sending real OTP emails and SMS

Out of the box, OTP codes are printed to the backend console so you can try the flow with no
external accounts. To deliver them to a real inbox/phone, set these in `backend/.env` and restart
the backend:

**Email (SMTP)**
```
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=youraddress@gmail.com
SMTP_PASSWORD=<Google App Password>
EMAIL_FROM=youraddress@gmail.com
```
Gmail needs an App Password (Google Account → Security → 2-Step Verification → App Passwords).
Any SMTP provider (Zoho, Outlook, Mailgun, Resend) works the same way.

**SMS (Termii or Twilio)**
```
SMS_PROVIDER=termii
SMS_API_KEY=<your Termii API key>
SMS_SENDER_ID=ZionhiltPay
```
For Twilio use `SMS_PROVIDER=twilio` and `SMS_API_KEY=ACCOUNT_SID:AUTH_TOKEN:FROM_NUMBER`.
Nigerian sender IDs generally need to be registered with the provider before they deliver reliably.

If a real send fails, the failure is logged and (outside production) the code is still printed to
the console so you aren't locked out while debugging. With `APP_ENV=production` the code is never
written to logs.

### Protecting stored ID numbers (do this before real users sign up)

Customers' National ID / driver's license numbers are stored **encrypted**. Generate a key once and
put it in `backend/.env`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# then:  DATA_ENCRYPTION_KEY=<the value printed above>
```

Back this key up somewhere safe, separately from the database. **If it is lost or changed, stored ID
numbers can no longer be decrypted** (the masked last-4 digits and the one-ID-one-account check keep
working). With `APP_ENV=production` the backend refuses to start without it. In development, if it is
unset, a key is derived from `JWT_SECRET_KEY`, which is fine for trying things out but not for real data.

### Upgrading an existing installation

No manual migration is needed. On startup the backend adds the new identity columns and indexes to an
existing database and gives every existing user a unique account number. It is safe to restart
repeatedly. Existing users keep working (they can log in with their email or their new account number);
they simply have no username or ID on file. Take a database backup first, as you would for any upgrade.

---

## Troubleshooting

Find the **last line** of the error message in your terminal and match it below.

| What you see | Why | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'slowapi'` (or any other module) | The packages aren't installed in the Python you are running, usually because the virtual environment is not active (or another project's is) | `deactivate`, activate **this** project's `backend/venv`, check that `python -c "import sys; print(sys.executable)"` points inside it, then `python -m pip install -r requirements.txt` |
| `Failed building wheel for asyncpg` / `Microsoft Visual C++ 14.0 or greater is required` | Unsupported Python version or old pinned packages being compiled from source | Use Python 3.12 or 3.13 with this project's `requirements.txt`. No C++ tools are needed |
| `No module named 'greenlet'` | Python 3.13 doesn't install it automatically | It is in `requirements.txt`: run `python -m pip install -r requirements.txt` again |
| `socket.gaierror: [Errno 11001] getaddrinfo failed` | The app is trying to reach the Docker-only host `db`: `.env` is missing or not being read | Run the config check from step 3. `.env` must be in `backend/`, named exactly `.env` (not `.env.txt`), saved as plain ASCII/UTF-8 **without BOM**; also run `Remove-Item Env:DATABASE_URL` in case a leftover environment variable overrides it |
| `password authentication failed for user "zp_app"` | The role exists with a different password than the one in `.env` | Fix the password in `.env`, or in `psql` run `ALTER USER zp_app WITH PASSWORD 'the-one-in-env';` |
| `password authentication failed for user "postgres"` | Wrong or forgotten admin password | See *Resetting a forgotten postgres password* below |
| `ConnectionRefusedError` / `WinError 1225` / `WinError 10061` | PostgreSQL isn't running, or is on another port | Start the PostgreSQL service (Windows: `Start-Service postgresql-x64-18`, adjust the name) and check the port in `.env` |
| `database "zionhiltpay" does not exist` | Step 2 wasn't completed | Run the `CREATE DATABASE` command again |
| Browser: `ERR_CONNECTION_REFUSED` or "Network error" when registering | The backend isn't running (it crashed, or was never started) | Look at Terminal 1. Run `python -m uvicorn app.main:app --reload` **by itself**; the line must reach `Application startup complete.` |
| Browser console: *blocked by CORS policy* from `http://172.x.x.x:5173` or `http://192.168.x.x:5173` | The site was opened through a network address | Open **<http://localhost:5173>**. To allow another address, set `CORS_ORIGINS=["http://localhost:5173","http://THAT-ADDRESS:5173"]` in `backend/.env` and restart the backend |
| "Invalid or expired OTP code" | You typed an example code, an old code, or the code has used its 5 attempts | Use the **newest** `[EMAIL OTP]` line in Terminal 1, or click "Resend code" and use the new one. Codes in this README are placeholders |
| No email or SMS arrives | Development mode prints codes to the backend terminal instead of sending them | See [Sending real OTP emails and SMS](#sending-real-otp-emails-and-sms) |
| `running scripts is disabled on this system` when activating the venv | PowerShell execution policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again |
| `'uvicorn' is not recognized` | The venv isn't active, or it isn't on PATH | Always use `python -m uvicorn ...` with the venv active |
| `Address already in use` / `[Errno 10048]` | Another program is using port 8000, 5173, 5432 or 80 | Stop it, or pick another port (e.g. `--port 8001`, then update `VITE_API_BASE_URL` and `CORS_ORIGINS`) |
| `npm install` or `vite` errors mentioning the Node version | Node.js is too old | Install Node.js 18 or newer |
| Login says the email domain is invalid for an admin like `admin@x.local` | Reserved domains such as `.local` are rejected | Use a normal-looking domain, e.g. `admin@example.com` |
| The **Admin** link is missing | The account isn't an admin | Admins can only be created with `scripts.create_admin` (step 6) |
| A deposit fails now and then | The mock payment gateway declines ~5% on purpose | Retry, or set `MOCK_GATEWAY_SUCCESS_RATE=1.0` in `backend/.env` |
| "PIN is too weak/common" | `0000`, `1234`, `1111`, `000000` and `123456` are blocked | Choose another PIN |

<details>
<summary><strong>Resetting a forgotten <code>postgres</code> password (Windows)</strong></summary>

This briefly allows password-free logins from your own computer only (the `127.0.0.1` line), sets a new
admin password and creates the project database, then restores the original setting. It restarts the
PostgreSQL service twice, so close anything else that is using it. Run it in a **new PowerShell opened as
Administrator**, adjusting the version number `18` and the service name to match your install:

```powershell
$psql    = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
$hba     = "C:\Program Files\PostgreSQL\18\data\pg_hba.conf"
$svc     = "postgresql-x64-18"
$pw      = "ChooseAPassword123"      # password for the project user zp_app
$adminpw = "NewAdminPass123"         # your NEW postgres admin password - write it down

Copy-Item $hba "$hba.bak" -Force
try {
    (Get-Content $hba) -replace '(host\s+all\s+all\s+127\.0\.0\.1/32\s+)\S+', '${1}trust' | Set-Content $hba -Encoding ascii
    if (-not (Select-String -Path $hba -Pattern '127\.0\.0\.1/32\s+trust' -Quiet)) {
        throw "Could not find the 127.0.0.1/32 line in pg_hba.conf - stopping. Nothing was changed."
    }
    Restart-Service $svc
    Start-Sleep -Seconds 3
    @"
ALTER USER postgres WITH PASSWORD '$adminpw';
CREATE USER zp_app WITH PASSWORD '$pw';
CREATE DATABASE zionhiltpay OWNER zp_app;
"@ | Set-Content "$env:TEMP\zp_setup.sql" -Encoding ascii
    & $psql -U postgres -h 127.0.0.1 -d postgres -f "$env:TEMP\zp_setup.sql"
}
finally {
    Copy-Item "$hba.bak" $hba -Force
    Restart-Service $svc
    Remove-Item "$env:TEMP\zp_setup.sql" -ErrorAction SilentlyContinue
}
```

The `finally` block restores `pg_hba.conf` even if something fails. Afterwards you can delete the harmless
`pg_hba.conf.bak`.

</details>

---

## Usage guide

### As a user
1. **Register** in two steps. Step 1: full name, a username (checked live for availability), email,
   phone number (`08012345678` or `+2348012345678`) and a password. Step 2: choose a National ID (NIN,
   11 digits) or driver's license, enter the number, and tick the consent box. You choose whether
   OTP codes come via email or SMS. You are given a unique **10-digit account number** immediately.
2. **Verify** the 6-digit OTP (in local/dev mode, codes are printed to the backend console logs
   instead of being sent, so you don't need real email/SMS credentials to try it out). Each code
   allows 5 attempts; after that, request a new one.
3. **Log in** with your **account number, username, email or phone number** plus your password, then
   set a **4–6 digit transaction PIN** — separate from your password, required for every transfer and
   withdrawal. Your account number and ID verification status show on the dashboard.
4. **Fund your wallet** via Deposit (simulated through the mock payment gateway).
5. **Send money** to anyone by **account number, username, email or phone number**. The app shows the
   recipient's name (first name and last initial) before you enter your PIN, and a mistyped account
   number is rejected by its check digit. A share of the fee comes back to you as reward cashback and
   device-insurance coverage, automatically.
6. **Register a device** (phone/laptop/tablet) under Devices & Insurance to start building coverage.
7. If a registered device is lost, stolen, or damaged, **file a claim** — payouts are capped at your
   accrued insurance balance and a max coverage ratio of the device's estimated value.

### As an admin
- **Overview** — live platform stats: user counts, total wallet/reward/insurance liabilities,
  platform revenue, transaction volume, open fraud flags, pending claims.
- **Users & KYC** — search by name, username, account number, email or phone; filter by KYC status;
  verify or reject a submitted ID; freeze/unfreeze accounts. Only a `super_admin` can reveal a full ID
  number, and each reveal is written to the audit log (who looked at whose ID — never the number).
- **Transactions** — every transaction on the platform, searchable by reference, username, account
  number or email, and filterable by status and type.
- **Audit log** — the append-only trail of sensitive actions.
- **Fraud flags** — review and resolve rule-triggered flags (velocity limits, large-amount
  transactions, new-account risk).
- **Insurance claims** — approve (with optional partial payout amount) or reject pending claims.
- **Config** *(super_admin only)* — live-tune reward rate, insurance contribution rate, transaction
  fee rate, withdrawal fee, and fraud thresholds without a redeploy.

---

## How the economics work

Every transfer and withdrawal charges a fee. That fee is split three ways, computed in
`backend/app/services/rewards.py`:

```
fee_amount              = amount × fee_rate (+ flat_fee for withdrawals)
reward_amount            = amount × reward_rate            → credited to sender's reward wallet
insurance_contribution   = fee_amount × insurance_rate      → credited to sender's insurance pool
platform_net              = fee_amount − reward − insurance  → kept as platform revenue
```

A safety guard ensures `reward_amount + insurance_contribution` can never exceed `fee_amount` — the
platform never pays out more than it collects. Default rates (all live-tunable by a super_admin):

| Parameter | Default |
|---|---|
| Reward rate | 0.50% of transaction amount |
| Insurance contribution rate | 1.00% of the fee collected |
| Transfer fee rate | 1.50% of transaction amount |
| Withdrawal flat fee | ₦25.00 |

---

## AI agents

Three Claude-powered agents are built in. They are **off by default** and switch on when you set
`ANTHROPIC_API_KEY` in `backend/.env` (see `.env.example`) and restart.

| Agent | Who | What it does |
|---|---|---|
| **Assistant** (`/assistant`) | Customers | Answers questions about their own balances, charges, rewards, devices and claims. Uses a fee calculator tool for exact numbers. |
| **Insights** (`/insights`) | Customers | Spending summary over 7/30/90 days. The numbers are computed in SQL; the model only writes the narrative, and the numbers still show if the AI is unavailable. |
| **Admin copilot** (`/admin/copilot`, plus "AI triage" buttons on fraud flags and claims) | Admins | Gathers evidence for a flag or claim and recommends approve / reject / escalate with its reasoning. |

**Safety design**

- **Read-only.** No agent tool can move money, freeze accounts, approve claims or change any state. Those stay behind the PIN and admin flows; the admin copilot only *recommends*.
- **Scoped by the server, not the model.** Tools never take a user id from the model; the acting user always comes from the authenticated request, so a prompt can't make the agent read another customer's data. Admin tools are re-checked against the caller's role at execution time and each agent only gets its own allow-list of tools.
- **User text is treated as data.** Transfer narrations and claim descriptions are sanitized, truncated, and the system prompts instruct the model never to follow instructions found inside them.
- **Bounded.** Rate limited (`RATE_LIMIT_AGENT`), capped message/history size, capped tool rounds, client-supplied chat history is sanitized server-side, and upstream error bodies are never shown to users.
- **Audited.** Every agent call writes an audit-log entry (agent, tools used, message length — not the message text).

**Privacy note:** when an agent answers, the relevant account data it looks up (balances, transactions,
for admins also account snapshots) is sent to the Anthropic API to produce the answer. Disclose this in
your privacy policy and review it against the Nigeria Data Protection Act (NDPA) before enabling it for real users.

Code lives in `backend/app/services/agent/` (`tools.py`, `runner.py`, `llm.py`) and `backend/app/api/agent.py`.

## Security

Security was treated as a first-class requirement throughout, not bolted on:

- **Double-entry ledger with hard balance checks** — a transaction is only marked `completed` if
  its debits and credits sum to exactly zero; otherwise the whole operation rolls back.
- **Password & PIN hashing** — bcrypt, via `passlib`, with the transaction PIN cryptographically
  namespaced separately from the login password so a leak of one hash space can't be replayed
  against the other.
- **PIN lockout** — repeated wrong PIN attempts lock transaction authorization for a cooldown
  period.
- **JWT access + rotating refresh tokens** — short-lived access tokens (15 min default); refresh
  tokens are stored server-side *hashed*, rotated on every use, and individually revocable.
- **OTP-gated registration and sensitive actions**, with expiry and a 5-attempt limit per code. Failed
  guesses are persisted, so the limit holds across requests, and verifying one channel never marks the
  other as verified.
- **Government ID numbers are encrypted at rest** (Fernet/AES) with a key kept outside the database.
  A keyed HMAC fingerprint enforces "one ID, one account" without storing anything guessable, only the
  last 4 digits are ever returned by an API, and the number is never written to logs or the audit trail.
  Revealing a full ID is restricted to `super_admin` and audited.
- **Account numbers** are random (not sequential, so they can't be enumerated) 10-digit numbers with a
  Luhn check digit that catches every single-digit typo. Recipient lookups are rate-limited and show
  only a masked name.
- **Login does not reveal which accounts exist**: unknown identifiers and wrong passwords return the
  same message and take the same time.
- **Rule-based fraud detection** — velocity limits, large-amount thresholds, and new-account risk
  scoring, with high/critical severity flags blocking a transaction pending manual review rather
  than silently allowing it.
- **Immutable audit log** — every sensitive action (login, PIN changes, transfers, admin actions,
  freezes, config changes) is recorded to an append-only `audit_logs` table; the ledger's own
  `ledger_entries` table is similarly append-only at the database level (`UPDATE`/`DELETE` are
  no-ops via Postgres rules).
- **Role-based access control** — `user` / `admin` / `super_admin`, with platform-economics config
  changes gated behind `super_admin` specifically.
- **Rate limiting** on auth and OTP endpoints to blunt brute-force and abuse.
- **Security headers** (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, HSTS in
  production) applied to every response.
- **Input validation** at the schema layer (Pydantic) for every request — phone format, password
  strength, PIN format, amount bounds, NUBAN account number format, etc.
- **No secrets in source** — all credentials and keys are environment-variable driven; `.env` is
  git-ignored, only `.env.example` templates are committed.

### What ID collection does and does not do

The app validates the **format** of an ID number (NIN: 11 digits; driver's license: 8–20 letters/digits),
stores it securely, prevents the same ID from being used on two accounts, and gives admins a review
queue. It does **not** check the number against NIMC or FRSC. To verify identities for real you need a
KYC provider (for example Smile ID, Dojah or Prembly) or a manual process, and admins should only press
"Verify ID" after doing that check. Collecting identity data also carries obligations under the Nigeria
Data Protection Act (consent, purpose limitation, retention, breach notification) and, for a licensed
payment business, CBN KYC rules; take proper advice before launching with real customers.

If you find a security issue, please see [Support / donations](#support--donations) below for
contact — do not open a public issue for anything that could be actively exploited.

---

## Testing

```bash
cd backend
python -m pip install -r requirements-dev.txt     # pytest, pytest-asyncio, aiosmtpd (on top of requirements.txt)
python -m pytest tests/ -q
```

This runs the tests that need no database (53). The database tests are skipped until you point them at an
**empty test database**; they create the tables themselves (full instructions under
[Run the tests](#run-the-tests)). With one, the whole suite runs (78 tests).

Included unit tests cover the fee-split economics (`test_rewards.py`) and core security primitives
(password/PIN hashing, OTP hashing, JWT round-tripping in `test_security.py`).

**Database integration tests.** `tests/test_agent_integration.py` runs the AI agent endpoints against a
real Postgres (only the Anthropic call is faked, by a model that deliberately misbehaves). It checks
that a customer can't read another customer's data, that smuggled `user_id` arguments are ignored,
that admin tools are closed to regular users, that agent calls never move money, that a database error
inside one tool can't break the request, and that recipients never see the sender's fee/reward figures.
It is skipped unless you point it at a database:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://zp_app:YOUR_PASSWORD@localhost:5432/zionhiltpay_test python -m pytest tests/ -q
```

**Identity tests.** `tests/test_identity.py` covers account-number generation (including that every
single-digit typo is caught), phone/username/ID rules and encryption. `tests/test_identity_integration.py`
runs against a real Postgres and covers registration, login by all four identifiers, disguised duplicates,
transfers by every identifier, the admin KYC flow and audited ID reveal, that ID numbers appear in no API
response or log, and upgrading an old-version database.

Beyond unit tests, the full stack was manually verified end-to-end during development: registration
→ OTP → login → PIN → deposit → transfer → withdrawal → device registration → insurance claim →
admin review, with every resulting transaction's ledger entries independently confirmed to balance
to exactly `0.00` via direct SQL audit.

---

## Project structure

```
zionhiltpay/
├── db/
│   └── schema.sql                  # Full PostgreSQL schema (optional: the backend creates it itself)
├── backend/
│   ├── app/
│   │   ├── core/                   # config, database, security, identity (account numbers, usernames, IDs),
│   │   │                           #   crypto (ID encryption), migrations, db_guards, rate limiting
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   ├── services/               # ledger, OTP, fraud, rewards, payment gateway, audit, directory, agent/
│   │   ├── api/                    # routers: auth, wallet, devices, admin, agent
│   │   └── main.py                 # FastAPI app entrypoint
│   ├── scripts/create_admin.py     # CLI to bootstrap admin accounts
│   ├── tests/                      # pytest suite (unit + database integration)
│   ├── requirements.txt            # runtime dependencies
│   ├── requirements-dev.txt        # extra packages for running the tests
│   ├── .env.example                # template for backend/.env
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/                  # route-level pages (incl. pages/admin/)
│   │   ├── components/             # shared UI (navbar, copy button, KYC badge, ...)
│   │   ├── context/                # AuthContext
│   │   ├── services/               # API client + endpoint groupings
│   │   └── utils/                  # formatting and phone helpers
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Contributing

Contributions, bug reports, and feature suggestions are welcome.

1. Fork the repository and create a feature branch: `git checkout -b feature/your-feature`
2. Keep changes focused — one concern per pull request.
3. If you touch the ledger, wallet, or fraud logic, add/update tests in `backend/tests/` and confirm
   `pytest tests/ -v` passes.
4. If you touch the schema, update **both** `db/schema.sql` and the corresponding SQLAlchemy model
   in `backend/app/models/` — they're expected to stay in sync.
5. Follow the existing code style (type-annotated Python, functional React components).
6. Open a pull request describing what changed and why.

Please don't include real credentials, API keys, or production data in any commit or PR.

---

## Support / donations

ZionhiltPay is built and maintained by **Zionhilt** — Full-Stack & Security Systems Engineering,
based in Lagos, Nigeria, covering software development, security tooling, OSINT, and computer
repair/technology services.

If this project has been useful to you and you'd like to support continued development:

**Bitcoin (BTC):** `bc1q-your-btc-address-here`

*(Replace the placeholder above with your actual BTC address before publishing.)*

For business inquiries, security consulting, or custom engineering work, reach out through the
Zionhilt channels you already use.

---

## License

This project is provided as-is for educational and portfolio purposes. Before using any part of
this codebase in a production financial system, ensure compliance with applicable financial
services regulation in your jurisdiction (in Nigeria, this includes CBN licensing requirements for
payment service providers) and have the security architecture independently audited. Nothing in
this repository constitutes legal, financial, or regulatory advice.

---

<div align="center">

**ZionhiltPay** — Send, save, and self-insure.
*Powered by Zionhilt.*

</div>
