
import os
import io
import base64
import secrets
import sqlite3

from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)

from werkzeug.security import generate_password_hash, check_password_hash

import qrcode
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.environ.get(
    'PARKWISE_DB_PATH',
    os.path.join(BASE_DIR, 'parking.db')
)

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY')

if not app.secret_key:
    raise RuntimeError(
        "SECRET_KEY is missing. Configure it in your .env file."
    )

app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

ACTIVE_BOOKING_STATES = ('booked', 'checked_in')


# ---------------- DATABASE CONNECTION ----------------

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row

    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 15000')

    try:
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def _columns(con, table):
    return {
        row['name']
        for row in con.execute(
            f'PRAGMA table_info({table})'
        ).fetchall()
    }


def _add_column(con, table, name, declaration):
    if name not in _columns(con, table):
        con.execute(
            f'ALTER TABLE {table} ADD COLUMN {name} {declaration}'
        )


# ---------------- DATABASE INITIALIZATION ----------------

def init_db():

    with db() as con:

        con.executescript('''

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_code TEXT NOT NULL UNIQUE,
            zone TEXT NOT NULL,
            vehicle_type TEXT NOT NULL DEFAULT 'Car',
            hourly_rate REAL NOT NULL DEFAULT 30,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            slot_id INTEGER NOT NULL,
            vehicle_number TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            qr_token TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'booked',
            checked_in_at TEXT,
            checked_out_at TEXT,
            payment_status TEXT NOT NULL DEFAULT 'demo_pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(slot_id) REFERENCES slots(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            booking_id INTEGER,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(booking_id) REFERENCES bookings(id)
        );

        ''')

        # Migrate older database versions.

        for name, declaration in [
            ('role', "TEXT NOT NULL DEFAULT 'user'"),
            ('created_at', 'TEXT'),
        ]:
            _add_column(con, 'users', name, declaration)

        for name, declaration in [
            ('active', 'INTEGER NOT NULL DEFAULT 1'),
            ('vehicle_type', "TEXT NOT NULL DEFAULT 'Car'"),
            ('hourly_rate', 'REAL NOT NULL DEFAULT 30'),
        ]:
            _add_column(con, 'slots', name, declaration)

        for name, declaration in [
            ('qr_token', 'TEXT'),
            ('amount', 'REAL NOT NULL DEFAULT 0'),
            ('status', "TEXT NOT NULL DEFAULT 'booked'"),
            ('checked_in_at', 'TEXT'),
            ('checked_out_at', 'TEXT'),
            ('payment_status', "TEXT NOT NULL DEFAULT 'demo_pending'"),
            ('created_at', 'TEXT'),
        ]:
            _add_column(con, 'bookings', name, declaration)

        # Generate QR tokens for older bookings.

        for row in con.execute(
            'SELECT id FROM bookings WHERE qr_token IS NULL OR qr_token=""'
        ).fetchall():

            con.execute(
                'UPDATE bookings SET qr_token=? WHERE id=?',
                (secrets.token_urlsafe(24), row['id'])
            )

        # Database indexes.

        con.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_bookings_qr_token ON bookings(qr_token)
        ''')

        con.execute('''
            CREATE INDEX IF NOT EXISTS
            idx_booking_slot_time
            ON bookings(slot_id,start_time,end_time,status)
        ''')

        con.execute('''
            CREATE INDEX IF NOT EXISTS
            idx_notifications_user
            ON notifications(user_id,is_read,created_at)
        ''')

        # Create administrator using private environment variables.

        admin_email = os.getenv('PARKWISE_ADMIN_EMAIL')
        admin_password = os.getenv('PARKWISE_ADMIN_PASSWORD')

        if admin_email and admin_password:

            admin_email = admin_email.strip().lower()

            if len(admin_password) < 12:
                raise RuntimeError(
                    "PARKWISE_ADMIN_PASSWORD must be at least 12 characters."
                )

            admin = con.execute(
                'SELECT id FROM users WHERE email=?',
                (admin_email,)
            ).fetchone()

            if admin:

                con.execute(
                    '''
                    UPDATE users
                    SET password_hash=?, role=?
                    WHERE id=?
                    ''',
                    (
                        generate_password_hash(admin_password),
                        'admin',
                        admin['id']
                    )
                )

            else:

                con.execute(
                    '''
                    INSERT INTO users(name,email,password_hash,role)
                    VALUES(?,?,?,?)
                    ''',
                    (
                        'Parkwise Admin',
                        admin_email,
                        generate_password_hash(admin_password),
                        'admin'
                    )
                )

        # Create default parking slots independently of admin creation.

        if con.execute(
            'SELECT COUNT(*) FROM slots'
        ).fetchone()[0] == 0:

            seed = []

            for i in range(1, 7):
                seed.append((f'A-{i:02d}', 'A', 'Car', 30))

            for i in range(1, 7):
                seed.append((f'B-{i:02d}', 'B', 'Car', 25))

            for i in range(7, 11):
                seed.append((f'B-{i:02d}', 'B', 'Bike', 12))

            con.executemany(
                '''
                INSERT INTO slots(
                    slot_code,zone,vehicle_type,hourly_rate
                )
                VALUES(?,?,?,?)
                ''',
                seed
            )


# ---------------- LOGIN DECORATORS ----------------

def login_required(fn):

    @wraps(fn)
    def wrapped(*args, **kwargs):

        if 'user_id' not in session:
            return redirect(url_for('login'))

        return fn(*args, **kwargs)

    return wrapped


def admin_required(fn):

    @wraps(fn)
    def wrapped(*args, **kwargs):

        if 'user_id' not in session:
            return redirect(url_for('login'))

        if session.get('role') != 'admin':
            flash(
                'Administrator access is required.',
                'error'
            )
            return redirect(url_for('dashboard'))

        return fn(*args, **kwargs)

    return wrapped


# ---------------- HELPER FUNCTIONS ----------------

def add_notification(con, user_id, title, message, booking_id=None):

    con.execute(
        '''
        INSERT INTO notifications(
            user_id,title,message,booking_id
        )
        VALUES(?,?,?,?)
        ''',
        (user_id, title, message, booking_id)
    )


def overlapping_booking(
    con, slot_id, start, end, exclude_id=None
):

    sql = '''
        SELECT id FROM bookings
        WHERE slot_id=?
        AND status IN ('booked','checked_in')
        AND start_time < ?
        AND end_time > ?
    '''

    params = [slot_id, end, start]

    if exclude_id is not None:
        sql += ' AND id<>?'
        params.append(exclude_id)

    return con.execute(
        sql + ' LIMIT 1',
        params
    ).fetchone()


def qr_data(token):

    url = (
        request.url_root.rstrip('/')
        + url_for('admin_scan', token=token)
    )

    image = qrcode.make(url)

    buffer = io.BytesIO()

    image.save(buffer, format='PNG')

    return base64.b64encode(
        buffer.getvalue()
    ).decode('ascii')


def parse_period(start_raw, end_raw, require_future=True):

    start = datetime.fromisoformat(start_raw)
    end = datetime.fromisoformat(end_raw)

    now = datetime.now()

    if end <= start or (
        require_future and start < now
    ):
        raise ValueError(
            'Choose a valid future time range.'
        )

    return start, end


# ---------------- HOME PAGE ----------------

@app.route('/')
def index():

    if 'user_id' in session:

        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))

        return redirect(url_for('dashboard'))

    with db() as con:

        total = con.execute(
            'SELECT COUNT(*) FROM slots WHERE active=1'
        ).fetchone()[0]

    return render_template(
        'landing.html',
        total_slots=total
    )


# ---------------- REGISTRATION ----------------

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form.get(
            'name', ''
        ).strip()

        email = request.form.get(
            'email', ''
        ).strip().lower()

        password = request.form.get(
            'password', ''
        )

        confirm = request.form.get(
            'confirm_password', ''
        )

        if not name or not email or len(password) < 8:

            flash(
                'Enter all details. Password must be at least 8 characters.',
                'error'
            )

            return render_template(
                'auth.html',
                mode='register'
            )

        if password != confirm:

            flash(
                'Your passwords do not match. Please try again.',
                'error'
            )

            return render_template(
                'auth.html',
                mode='register'
            )

        if request.form.get('terms') != 'on':

            flash(
                'Please accept the terms to continue.',
                'error'
            )

            return render_template(
                'auth.html',
                mode='register'
            )

        try:

            with db() as con:

                con.execute(
                    '''
                    INSERT INTO users(
                        name,email,password_hash,role
                    )
                    VALUES(?,?,?,?)
                    ''',
                    (
                        name,
                        email,
                        generate_password_hash(password),
                        'user'
                    )
                )

            flash(
                'Account created. You can now sign in.',
                'success'
            )

            return redirect(url_for('login'))

        except sqlite3.IntegrityError:

            flash(
                'An account with this email already exists.',
                'error'
            )

    return render_template(
        'auth.html',
        mode='register'
    )


# ---------------- LOGIN ----------------

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form.get(
            'email', ''
        ).strip().lower()

        password = request.form.get(
            'password', ''
        )

        with db() as con:

            user = con.execute(
                'SELECT * FROM users WHERE email=?',
                (email,)
            ).fetchone()

        if user and check_password_hash(
            user['password_hash'],
            password
        ):

            session.clear()
            session.permanent = True

            session.update(
                user_id=user['id'],
                name=user['name'],
                email=user['email'],
                role=user['role']
            )

            if user['role'] == 'admin':
                return redirect(
                    url_for('admin_dashboard')
                )

            return redirect(
                url_for('dashboard')
            )

        flash(
            'Email or password is incorrect.',
            'error'
        )

    return render_template(
        'auth.html',
        mode='login'
    )


# ---------------- LOGOUT ----------------

@app.route('/logout')
def logout():

    session.clear()

    return redirect(url_for('index'))


# ---------------- USER DASHBOARD ----------------

@app.route('/dashboard')
@login_required
def dashboard():

    with db() as con:

        bookings = con.execute(
            '''
            SELECT
                b.*,
                s.slot_code,
                s.zone,
                s.vehicle_type,
                s.hourly_rate
            FROM bookings b
            JOIN slots s ON s.id=b.slot_id
            WHERE b.user_id=?
            ORDER BY b.created_at DESC
            ''',
            (session['user_id'],)
        ).fetchall()

        active = con.execute(
            '''
            SELECT COUNT(*)
            FROM bookings
            WHERE user_id=?
            AND status IN ('booked','checked_in')
            ''',
            (session['user_id'],)
        ).fetchone()[0]

        enabled = con.execute(
            'SELECT COUNT(*) FROM slots WHERE active=1'
        ).fetchone()[0]

    return render_template(
        'dashboard.html',
        bookings=bookings,
        total_slots=enabled,
        active_bookings=active
    )


# ---------------- AVAILABLE SLOTS API ----------------

@app.route('/api/slots')
@login_required
def api_slots():

    try:

        start, end = parse_period(
            request.args.get('start', ''),
            request.args.get('end', '')
        )

    except (ValueError, TypeError):

        return jsonify({
            'error': 'Choose a future arrival time and a later departure time.'
        }), 400

    start_s = start.isoformat(
        timespec='minutes'
    )

    end_s = end.isoformat(
        timespec='minutes'
    )

    with db() as con:

        slots = con.execute(
            'SELECT * FROM slots ORDER BY zone,slot_code'
        ).fetchall()

        result = []

        for slot in slots:

            busy = (
                overlapping_booking(
                    con,
                    slot['id'],
                    start_s,
                    end_s
                )
                if slot['active']
                else True
            )

            result.append({

                'id': slot['id'],

                'code': slot['slot_code'],

                'zone': slot['zone'],

                'vehicle_type': slot['vehicle_type'],

                'rate': slot['hourly_rate'],

                'available': (
                    bool(slot['active'])
                    and not bool(busy)
                ),

                'active': bool(slot['active'])

            })

    return jsonify(result)


# ---------------- BOOK PARKING SLOT ----------------

@app.route('/book', methods=['POST'])
@login_required
def book():

    try:

        slot_id = int(
            request.form.get('slot_id', '0')
        )

        start, end = parse_period(
            request.form.get('start', ''),
            request.form.get('end', '')
        )

        vehicle = request.form.get(
            'vehicle_number', ''
        ).strip().upper()

        if not vehicle or len(vehicle) > 15:
            raise ValueError(
                'Enter a valid vehicle registration number.'
            )

    except (ValueError, TypeError):

        flash(
            'Please enter valid booking details and a future time.',
            'error'
        )

        return redirect(
            url_for('dashboard')
        )

    with db() as con:

        con.execute('BEGIN IMMEDIATE')

        slot = con.execute(
            '''
            SELECT * FROM slots
            WHERE id=? AND active=1
            ''',
            (slot_id,)
        ).fetchone()

        if not slot:

            flash(
                'That parking slot is not active.',
                'error'
            )

            return redirect(
                url_for('dashboard')
            )

        start_s = start.isoformat(
            timespec='minutes'
        )

        end_s = end.isoformat(
            timespec='minutes'
        )

        if overlapping_booking(
            con,
            slot_id,
            start_s,
            end_s
        ):

            flash(
                'This slot is already reserved for the selected time. Please choose another.',
                'error'
            )

            return redirect(
                url_for('dashboard')
            )

        hours = max(
            1,
            (end - start).total_seconds() / 3600
        )

        amount = round(
            hours * slot['hourly_rate'],
            2
        )

        token = secrets.token_urlsafe(32)

        con.execute(
            '''
            INSERT INTO bookings(
                user_id,
                slot_id,
                vehicle_number,
                start_time,
                end_time,
                amount,
                qr_token,
                status,
                payment_status
            )
            VALUES(?,?,?,?,?,?,?,'booked','demo_pending')
            ''',
            (
                session['user_id'],
                slot_id,
                vehicle,
                start_s,
                end_s,
                amount,
                token
            )
        )

        booking_id = con.execute(
            'SELECT last_insert_rowid()'
        ).fetchone()[0]

        add_notification(
            con,
            session['user_id'],
            'Booking confirmed',
            f'{slot["slot_code"]} is reserved. Your QR parking pass is ready.',
            booking_id
        )

    flash(
        'Your parking slot is booked. Your QR pass is ready.',
        'success'
    )

    return redirect(
        url_for(
            'booking_detail',
            booking_id=booking_id
        )
    )


# ---------------- BOOKING DETAILS AND QR ----------------

@app.route('/booking/<int:booking_id>')
@login_required
def booking_detail(booking_id):

    with db() as con:

        booking = con.execute(
            '''
            SELECT
                b.*,
                s.slot_code,
                s.zone,
                s.vehicle_type,
                s.hourly_rate
            FROM bookings b
            JOIN slots s ON s.id=b.slot_id
            WHERE b.id=? AND b.user_id=?
            ''',
            (
                booking_id,
                session['user_id']
            )
        ).fetchone()

    if not booking:
        abort(404)

    return render_template(
        'booking.html',
        booking=booking,
        qr=qr_data(booking['qr_token'])
    )


# ---------------- CANCEL USER BOOKING ----------------

@app.route(
    '/booking/cancel/<int:booking_id>',
    methods=['POST']
)
@login_required
def user_cancel_booking(booking_id):

    with db() as con:

        booking = con.execute(
            '''
            SELECT
                b.id,
                b.user_id,
                s.slot_code
            FROM bookings b
            JOIN slots s ON s.id=b.slot_id
            WHERE b.id=?
            AND b.user_id=?
            AND b.status='booked'
            ''',
            (
                booking_id,
                session['user_id']
            )
        ).fetchone()

        if not booking:

            flash(
                'Only your upcoming bookings can be cancelled.',
                'error'
            )

        else:

            con.execute(
                '''
                UPDATE bookings
                SET status='cancelled'
                WHERE id=?
                AND user_id=?
                AND status='booked'
                ''',
                (
                    booking_id,
                    session['user_id']
                )
            )

            add_notification(
                con,
                session['user_id'],
                'Booking cancelled',
                f'Your reservation for {booking["slot_code"]} was cancelled.',
                booking_id
            )

            flash(
                'Your booking has been cancelled.',
                'success'
            )

    return redirect(
        url_for('dashboard')
    )


# ---------------- NOTIFICATIONS API ----------------

@app.route('/api/notifications')
@login_required
def api_notifications():

    with db() as con:

        rows = con.execute(
            '''
            SELECT
                id,
                title,
                message,
                is_read,
                created_at
            FROM notifications
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 20
            ''',
            (session['user_id'],)
        ).fetchall()

        unread = con.execute(
            '''
            SELECT COUNT(*)
            FROM notifications
            WHERE user_id=? AND is_read=0
            ''',
            (session['user_id'],)
        ).fetchone()[0]

    return jsonify({
        'items': [
            dict(row)
            for row in rows
        ],
        'unread': unread
    })


@app.route('/notifications/read', methods=['POST'])
@login_required
def notifications_read():

    with db() as con:

        con.execute(
            '''
            UPDATE notifications
            SET is_read=1
            WHERE user_id=?
            ''',
            (session['user_id'],)
        )

    return jsonify({
        'ok': True
    })


# ---------------- ADMIN DASHBOARD ----------------

@app.route('/admin')
@admin_required
def admin_dashboard():

    with db() as con:

        stats = {

            'slots': con.execute(
                'SELECT COUNT(*) FROM slots WHERE active=1'
            ).fetchone()[0],

            'total_slots': con.execute(
                'SELECT COUNT(*) FROM slots'
            ).fetchone()[0],

            'bookings': con.execute(
                'SELECT COUNT(*) FROM bookings'
            ).fetchone()[0],

            'today': con.execute(
                '''
                SELECT COUNT(*)
                FROM bookings
                WHERE date(start_time)=date('now','localtime')
                '''
            ).fetchone()[0],

            'revenue': con.execute(
                '''
                SELECT COALESCE(SUM(amount),0)
                FROM bookings
                WHERE status='completed'
                '''
            ).fetchone()[0],

            'completed': con.execute(
                '''
                SELECT COUNT(*)
                FROM bookings
                WHERE status='completed'
                '''
            ).fetchone()[0],

            'cancelled': con.execute(
                '''
                SELECT COUNT(*)
                FROM bookings
                WHERE status='cancelled'
                '''
            ).fetchone()[0],

            'checked_in': con.execute(
                '''
                SELECT COUNT(*)
                FROM bookings
                WHERE status='checked_in'
                '''
            ).fetchone()[0],

        }

        bookings = con.execute(
            '''
            SELECT
                b.*,
                u.name,
                u.email,
                s.slot_code
            FROM bookings b
            JOIN users u ON u.id=b.user_id
            JOIN slots s ON s.id=b.slot_id
            ORDER BY b.created_at DESC
            LIMIT 50
            '''
        ).fetchall()

        slots = con.execute(
            'SELECT * FROM slots ORDER BY zone,slot_code'
        ).fetchall()

        daily = con.execute(
            '''
            SELECT
                date(checked_out_at) AS day,
                ROUND(SUM(amount),2) AS revenue
            FROM bookings
            WHERE status='completed'
            AND checked_out_at IS NOT NULL
            GROUP BY date(checked_out_at)
            ORDER BY day DESC
            LIMIT 7
            '''
        ).fetchall()

    return render_template(
        'admin.html',
        stats=stats,
        bookings=bookings,
        slots=slots,
        daily_revenue=daily
    )


# ---------------- ADD PARKING SLOT ----------------

@app.route('/admin/slots/add', methods=['POST'])
@admin_required
def add_slot():

    code = request.form.get(
        'slot_code', ''
    ).strip().upper()

    zone = request.form.get(
        'zone', ''
    ).strip().upper()

    vehicle_raw = request.form.get(
        'vehicle_type', 'Car'
    ).strip().lower()

    vehicle_type = {
        'car': 'Car',
        'bike': 'Bike',
        'ev': 'EV'
    }.get(vehicle_raw, 'Car')

    try:

        rate = float(
            request.form.get('hourly_rate', '0')
        )

        if (
            not code
            or not zone
            or rate <= 0
            or len(code) > 20
            or len(zone) > 10
            or vehicle_type not in ('Car', 'Bike', 'EV')
        ):
            raise ValueError

        with db() as con:

            con.execute(
                '''
                INSERT INTO slots(
                    slot_code,
                    zone,
                    vehicle_type,
                    hourly_rate
                )
                VALUES(?,?,?,?)
                ''',
                (
                    code,
                    zone,
                    vehicle_type,
                    rate
                )
            )

        flash(
            f'Slot {code} added.',
            'success'
        )

    except (
        ValueError,
        sqlite3.IntegrityError
    ):

        flash(
            'Enter a unique slot code, zone, vehicle type and positive hourly rate.',
            'error'
        )

    return redirect(
        url_for('admin_dashboard')
    )


# ---------------- ENABLE / DISABLE SLOT ----------------

@app.route(
    '/admin/slots/toggle/<int:slot_id>',
    methods=['POST']
)
@admin_required
def toggle_slot(slot_id):

    with db() as con:

        slot = con.execute(
            'SELECT * FROM slots WHERE id=?',
            (slot_id,)
        ).fetchone()

        if not slot:

            flash(
                'Parking slot not found.',
                'error'
            )

        elif (
            slot['active']
            and con.execute(
                '''
                SELECT 1
                FROM bookings
                WHERE slot_id=?
                AND status='checked_in'
                LIMIT 1
                ''',
                (slot_id,)
            ).fetchone()
        ):

            flash(
                'A checked-in vehicle is using this slot. Check it out before disabling it.',
                'error'
            )

        else:

            con.execute(
                'UPDATE slots SET active=? WHERE id=?',
                (
                    0 if slot['active'] else 1,
                    slot_id
                )
            )

            flash(
                'Slot status updated.',
                'success'
            )

    return redirect(
        url_for('admin_dashboard')
    )


# ---------------- ADMIN CANCEL BOOKING ----------------

@app.route(
    '/admin/booking/cancel/<int:booking_id>',
    methods=['POST']
)
@admin_required
def cancel_booking(booking_id):

    with db() as con:

        booking = con.execute(
            '''
            SELECT
                b.user_id,
                b.id,
                s.slot_code
            FROM bookings b
            JOIN slots s ON s.id=b.slot_id
            WHERE b.id=?
            AND b.status='booked'
            ''',
            (booking_id,)
        ).fetchone()

        if booking:

            con.execute(
                '''
                UPDATE bookings
                SET status='cancelled'
                WHERE id=?
                AND status='booked'
                ''',
                (booking_id,)
            )

            add_notification(
                con,
                booking['user_id'],
                'Booking cancelled by administrator',
                f'Your reservation for {booking["slot_code"]} was cancelled by the parking administrator.',
                booking_id
            )

            flash(
                'Booking cancelled.',
                'success'
            )

        else:

            flash(
                'Only bookings that have not checked in can be cancelled.',
                'error'
            )

    return redirect(
        url_for('admin_dashboard')
    )


# ---------------- QR SCAN / CHECK-IN / CHECK-OUT ----------------

@app.route(
    '/admin/scan/<token>',
    methods=['GET', 'POST']
)
@admin_required
def admin_scan(token):

    with db() as con:

        booking = con.execute(
            '''
            SELECT
                b.*,
                u.name,
                u.email,
                s.slot_code,
                s.hourly_rate,
                s.vehicle_type
            FROM bookings b
            JOIN users u ON u.id=b.user_id
            JOIN slots s ON s.id=b.slot_id
            WHERE b.qr_token=?
            ''',
            (token,)
        ).fetchone()

        if not booking:

            flash(
                'QR code is not valid.',
                'error'
            )

            return redirect(
                url_for('admin_dashboard')
            )

        if request.method == 'POST':

            action = request.form.get('action')

            now_dt = datetime.now()

            now = now_dt.isoformat(
                timespec='minutes'
            )

            # CHECK-IN

            if (
                action == 'checkin'
                and booking['status'] == 'booked'
            ):

                start = datetime.fromisoformat(
                    booking['start_time']
                )

                end = datetime.fromisoformat(
                    booking['end_time']
                )

                if now_dt < start - timedelta(minutes=30):

                    flash(
                        'This booking is not yet within its 30-minute early check-in window.',
                        'error'
                    )

                elif now_dt > end:

                    flash(
                        'This booking has expired. Contact the administrator.',
                        'error'
                    )

                else:

                    con.execute(
                        '''
                        UPDATE bookings
                        SET status='checked_in',
                            checked_in_at=?
                        WHERE id=?
                        AND status='booked'
                        ''',
                        (
                            now,
                            booking['id']
                        )
                    )

                    add_notification(
                        con,
                        booking['user_id'],
                        'Vehicle checked in',
                        f'Your vehicle has checked in at {booking["slot_code"]}.',
                        booking['id']
                    )

                    flash(
                        'Vehicle checked in successfully.',
                        'success'
                    )

            # CHECK-OUT

            elif (
                action == 'checkout'
                and booking['status'] == 'checked_in'
            ):

                checked_in = datetime.fromisoformat(
                    booking['checked_in_at']
                )

                elapsed_hours = (
                    now_dt - checked_in
                ).total_seconds() / 3600

                billable_hours = max(
                    1,
                    int(elapsed_hours)
                    + (1 if elapsed_hours % 1 else 0)
                )

                final_amount = round(
                    billable_hours * booking['hourly_rate'],
                    2
                )

                con.execute(
                    '''
                    UPDATE bookings
                    SET status='completed',
                        checked_out_at=?,
                        amount=?,
                        payment_status='demo_recorded'
                    WHERE id=?
                    AND status='checked_in'
                    ''',
                    (
                        now,
                        final_amount,
                        booking['id']
                    )
                )

                add_notification(
                    con,
                    booking['user_id'],
                    'Parking completed',
                    f'Checkout complete. Final demo bill: ₹{final_amount:.2f}. No real payment was taken.',
                    booking['id']
                )

                flash(
                    f'Vehicle checked out. Final demo bill: ₹{final_amount:.2f}.',
                    'success'
                )

            else:

                flash(
                    'This action is not valid for the current booking status.',
                    'error'
                )

            return redirect(
                url_for(
                    'admin_scan',
                    token=token
                )
            )

    return render_template(
        'scan.html',
        booking=booking
    )


# ---------------- 404 PAGE ----------------

@app.errorhandler(404)
def not_found(_):

    return render_template(
        '404.html'
    ), 404


# ---------------- START APPLICATION ----------------

init_db()

if __name__ == '__main__':

    app.run(
        host='127.0.0.1',
        port=5000,
        debug=os.environ.get('FLASK_DEBUG') == '1'
    )
