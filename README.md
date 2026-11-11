# Parkwise — Advanced QR Smart Parking System

Parkwise is a responsive QR-based parking management project built with **Python Flask, SQLite, HTML, CSS and JavaScript**. This release preserves the existing Parkwise green-and-white visual design, page structure, hover effects and animations while adding administration, gate operations, demo billing, notifications and analytics.

## Features included

### Customer account and booking
- Customer sign-up and sign-in with hashed passwords.
- Customer-only booking history; users cannot open another user's booking pass.
- Search parking by arrival and departure time.
- Shared availability across all accounts, including occupied and maintenance spaces.
- Server-side overlap check when a booking is submitted.
- Vehicle registration number validation.
- Automatic estimated booking cost using slot rate and duration (minimum one billable hour).
- Unique, unguessable QR token and downloadable/printable browser pass.
- Customer cancellation before check-in.

### QR gate operations
- Camera-based QR scanner on the administrator dashboard (browser camera permission required).
- QR image-file scanning fallback provided by the scanner library.
- Protected QR verification page showing customer, vehicle, slot and reservation information.
- Check-in is allowed from 30 minutes before the reservation start until its end time.
- Check-out records the exit time and changes the booking status to `completed`.
- Checkout rounds elapsed parking time up to the next whole hour, with a one-hour minimum.

### Billing and notifications
- Demo checkout bill uses the slot's hourly rate and recorded check-in/check-out duration.
- Booking, cancellation, check-in and checkout notifications appear in the customer's dashboard.
- Notification unread count and mark-all-read action.
- Notifications refresh every 20 seconds while the customer dashboard is open.
- **No real payment is collected.** `demo_recorded` means a bill was calculated for demonstration only.

### Administrator and analytics
- Separate administrator login and role-protected routes.
- Overview cards for enabled spaces, total bookings, today's bookings, completed demo revenue, completed sessions, cancelled bookings and currently checked-in vehicles.
- Add parking spaces with a zone, vehicle type and hourly rate.
- Enable/disable spaces; a slot with a checked-in vehicle cannot be disabled.
- Recent booking table with customer, schedule, vehicle, amount, status and QR verification link.
- Cancel reservations that have not checked in; customer is notified.
- Recent completed revenue chart.

### UI and experience
- Existing Parkwise typography, colors, responsive layouts and animations retained.
- Green available slots, red occupied slots and disabled/maintenance labels.
- Availability auto-refreshes every 15 seconds after the first search.
- Reduced-motion support and responsive layouts are retained from the original styles.

## Project structure

```text
smart_parking/
├── app.py
├── schema.sql
├── requirements.txt
├── README.md
├── .env.example
├── run_windows.bat
├── tests/
│   └── test_app.py
├── templates/
│   ├── base.html
│   ├── landing.html
│   ├── auth.html
│   ├── dashboard.html
│   ├── booking.html
│   ├── admin.html
│   ├── scan.html
│   └── 404.html
└── static/
    ├── css/style.css
    └── js/
        ├── app.js
        ├── booking.js
        └── scanner.js
```

## Run on Windows

1. Extract the ZIP.
2. Open the `smart_parking` folder in VS Code.
3. Open PowerShell in that folder.
4. Create a virtual environment and install packages:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

5. Start the app:

```powershell
python app.py
```

6. Open `http://127.0.0.1:5000`.

You can also double-click `run_windows.bat`; it creates `.venv` if missing, installs dependencies and starts the server.

## Demo administrator

- Email: `admin@parkwise.local`
- Password: `Admin@123`

This is a local academic demo account. Change the password before sharing the app or deploying it. Normal customer registration always creates a `user` role; users cannot self-register as administrators.

## Suggested end-to-end demonstration

1. Register two customer accounts (for example, Alex and Sam).
2. Sign in as Alex and search a future time range.
3. Reserve a free space and open the QR pass.
4. Sign out and sign in as Sam; search the same time range. Alex's reserved slot should be shown as occupied. Alex's booking history must remain private.
5. Sign in as the administrator.
6. Open the QR scanner and grant camera access, or use the booking's **Open** link in Recent reservations.
7. Check in the vehicle when the booking is within the allowed check-in window.
8. Check out the vehicle. The booking becomes completed, the final demo bill is calculated and a customer notification is created.
9. Return to the customer account and inspect notifications and booking status.
10. Add a new parking space, disable/enable it, and inspect the admin statistics and revenue chart.

## Automated feature tests

The project includes standard-library `unittest` integration tests. After installing the requirements, run:

```powershell
python -m unittest discover -s tests -v
```

The tests use a temporary SQLite database and do not modify your real `parking.db`. They cover registration/login, QR pass generation, booking privacy, shared slot availability, overlap protection, cancellation, notifications, admin access, slot management, check-in, checkout billing and analytics.

## Existing database compatibility

The app uses `parking.db` in the project folder. On startup it creates missing tables and adds supported columns without deleting existing customer accounts, slots or bookings. **Back up your current `parking.db` before upgrading.** Do not delete it if you want to retain your data.

## Configuration and security notes

For local testing, the app runs on `127.0.0.1:5000`. The fallback Flask secret is for local development only. For a shared environment, set a private `SECRET_KEY` environment variable and keep `FLASK_DEBUG=0`. Do not commit secrets or a real customer database to source control.

The scanner uses `html5-qrcode` from a CDN; an internet connection is required to load that browser library. Camera access is supported on `localhost` or HTTPS and requires the user to grant permission. The QR itself is generated locally by Python.

This is an educational/demo project, not a production parking or payment service. Before public deployment, add CSRF protection to all state-changing forms, rate limiting, password reset, stronger admin account provisioning, HTTPS, secure secret management, database backups, audit logging and a production WSGI server. Real payments require a payment provider and server-side verification; this project deliberately does not collect real money.
