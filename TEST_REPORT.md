# Parkwise build validation report

## Checks completed while packaging

- Python syntax compilation: `app.py` and `tests/test_app.py` — passed.
- JavaScript syntax validation: `app.js`, `booking.js`, `scanner.js` with `node --check` — passed.
- SQLite schema validation: schema executed against a fresh temporary SQLite database — see package validation record.
- ZIP contents checked: source, templates, CSS, JavaScript, requirements, README and automated tests included; local `.venv`, `__pycache__` and `parking.db` excluded.

## Integration test suite included

Run `python -m unittest discover -s tests -v` after installing `requirements.txt`. It exercises registration/login, customer booking privacy, QR pass generation, shared availability, booking cancellation, notifications, admin access, slot management, check-in, checkout billing and analytics.

**Environment limitation:** the packaging environment did not have Flask or qrcode installed and had no network access to install them. Therefore the Flask integration suite could not be executed here. It is included for execution on the user's Windows machine after dependency installation. The project is not represented as having passed runtime integration tests in this packaging environment.
