# Parkwise UI Refresh — Change Guide

## Replace these files in your existing project

Copy the updated files from this ZIP into the matching locations in your extracted `smart_parking` folder:

1. `templates/auth.html`
2. `static/css/style.css`
3. `static/js/app.js`
4. `templates/base.html`
5. `app.py`

Choose **Replace** if Windows asks whether to overwrite existing files.

## What each file controls

| File | What changed |
|---|---|
| `templates/auth.html` | Redesigned, separate sign-up and sign-in states; full name; email; password; confirm password; terms checkbox; show/hide buttons |
| `static/css/style.css` | New green visual identity, richer contrast, animated showcase panel, floating ticket, hover effects, responsive layout, reduced-motion support |
| `static/js/app.js` | Show/hide password, password-strength meter, password-match check, gentle scroll reveals |
| `templates/base.html` | Updated theme color and CSS/JS cache version |
| `app.py` | Server-side validation for password match and terms acceptance |

## Run after replacing

Open the terminal in the folder that contains `app.py`:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

If the old design is still visible, press `Ctrl + Shift + R`.

## Important

The existing database and booking records are not deleted by this UI update. The project continues to use SQLite (`parking.db`) and the existing QR booking workflow.
