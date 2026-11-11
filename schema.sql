-- Parkwise SQLite schema. app.py applies this schema and safe additive migrations.
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
CREATE INDEX IF NOT EXISTS idx_booking_slot_time ON bookings(slot_id,start_time,end_time,status);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id,is_read,created_at);
