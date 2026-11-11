import os
import tempfile
import unittest
from datetime import datetime, timedelta

import app as parkwise


class ParkwiseFeatureTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = parkwise.DB_PATH

        # Save existing admin environment variables.
        self.old_admin_email = os.environ.get('PARKWISE_ADMIN_EMAIL')
        self.old_admin_password = os.environ.get('PARKWISE_ADMIN_PASSWORD')

        # Create a temporary admin account for testing.
        os.environ['PARKWISE_ADMIN_EMAIL'] = 'admin@example.test'
        os.environ['PARKWISE_ADMIN_PASSWORD'] = 'TestAdmin12345'

        parkwise.DB_PATH = os.path.join(self.temp.name, 'test_parking.db')
        parkwise.init_db()

        parkwise.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = parkwise.app.test_client()

        self._register('alex', 'alex@example.test', 'Password123')
        self._login('alex@example.test', 'Password123')



    def tearDown(self):
        parkwise.DB_PATH = self.old_db

        # Restore original environment variables.
        if self.old_admin_email is None:
            os.environ.pop('PARKWISE_ADMIN_EMAIL', None)
        else:
            os.environ['PARKWISE_ADMIN_EMAIL'] = self.old_admin_email

        if self.old_admin_password is None:
            os.environ.pop('PARKWISE_ADMIN_PASSWORD', None)
        else:
            os.environ['PARKWISE_ADMIN_PASSWORD'] = self.old_admin_password

        self.temp.cleanup()

    def _register(self, name, email, password):
        return self.client.post('/register', data={
            'name': name, 'email': email, 'password': password,
            'confirm_password': password, 'terms': 'on'
        }, follow_redirects=True)

    def _login(self, email, password):
        return self.client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)


    def _admin(self):
        self.client.get('/logout')
        return self._login('admin@example.test', 'TestAdmin12345')


    def _book(self, slot_id=1):
        start = datetime.now() + timedelta(minutes=5)
        end = start + timedelta(hours=2)
        response = self.client.post('/book', data={
            'slot_id': str(slot_id),
            'start': start.isoformat(timespec='minutes'),
            'end': end.isoformat(timespec='minutes'),
            'vehicle_number': 'TS09AB1234'
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        return int(response.location.rsplit('/', 1)[-1])

    def test_register_login_and_user_dashboard(self):
        self.assertEqual(self.client.get('/dashboard').status_code, 200)
        self.client.get('/logout')
        response = self._register('sam', 'sam@example.test', 'Password123')
        self.assertIn(b'Welcome back', response.data)
        login = self._login('sam@example.test', 'Password123')
        self.assertIn(b'Good day', login.data)

    def test_booking_qr_and_user_privacy(self):
        booking_id = self._book(1)
        page = self.client.get(f'/booking/{booking_id}')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'data:image/png;base64', page.data)
        self.client.get('/logout')
        self._register('tom', 'tom@example.test', 'Password123')
        self._login('tom@example.test', 'Password123')
        self.assertEqual(self.client.get(f'/booking/{booking_id}').status_code, 404)

    def test_shared_availability_and_overlap(self):
        booking_id = self._book(1)
        with parkwise.db() as con:
            booking = con.execute('SELECT * FROM bookings WHERE id=?', (booking_id,)).fetchone()
        response = self.client.get('/api/slots', query_string={
            'start': booking['start_time'], 'end': booking['end_time']
        })
        self.assertEqual(response.status_code, 200)
        slots = response.get_json()
        self.assertFalse(next(s for s in slots if s['id'] == 1)['available'])
        self.assertTrue(next(s for s in slots if s['id'] == 2)['available'])

    def test_cancel_booking_and_notification(self):
        booking_id = self._book(2)
        response = self.client.post(f'/booking/cancel/{booking_id}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with parkwise.db() as con:
            row = con.execute('SELECT status FROM bookings WHERE id=?', (booking_id,)).fetchone()
        self.assertEqual(row['status'], 'cancelled')
        notifications = self.client.get('/api/notifications').get_json()
        self.assertGreaterEqual(notifications['unread'], 2)

    def test_admin_slot_management_and_dashboard(self):
        self._admin()
        self.assertEqual(self.client.get('/admin').status_code, 200)
        add = self.client.post('/admin/slots/add', data={
            'slot_code': 'C-01', 'zone': 'C', 'vehicle_type': 'EV', 'hourly_rate': '40'
        }, follow_redirects=True)
        self.assertIn(b'C-01', add.data)
        with parkwise.db() as con:
            slot_id = con.execute('SELECT id FROM slots WHERE slot_code=?', ('C-01',)).fetchone()['id']
        self.client.post(f'/admin/slots/toggle/{slot_id}', follow_redirects=True)
        with parkwise.db() as con:
            active = con.execute('SELECT active FROM slots WHERE id=?', (slot_id,)).fetchone()['active']
        self.assertEqual(active, 0)

    def test_admin_checkin_checkout_billing_and_notification(self):
        booking_id = self._book(3)
        with parkwise.db() as con:
            row = con.execute('SELECT * FROM bookings WHERE id=?', (booking_id,)).fetchone()
            token = row['qr_token']
            # Put the appointment inside the check-in window for deterministic test.
            con.execute('UPDATE bookings SET start_time=?,end_time=? WHERE id=?', (
                (datetime.now() - timedelta(minutes=5)).isoformat(timespec='minutes'),
                (datetime.now() + timedelta(hours=3)).isoformat(timespec='minutes'), booking_id
            ))
        self._admin()
        scan = self.client.get(f'/admin/scan/{token}')
        self.assertEqual(scan.status_code, 200)
        checkin = self.client.post(f'/admin/scan/{token}', data={'action': 'checkin'}, follow_redirects=True)
        self.assertIn(b'checked in successfully', checkin.data)
        with parkwise.db() as con:
            con.execute('UPDATE bookings SET checked_in_at=? WHERE id=?', (
                (datetime.now() - timedelta(hours=2, minutes=10)).isoformat(timespec='minutes'), booking_id
            ))
        checkout = self.client.post(f'/admin/scan/{token}', data={'action': 'checkout'}, follow_redirects=True)
        self.assertIn(b'Vehicle checked out', checkout.data)
        with parkwise.db() as con:
            row = con.execute('SELECT status,amount,payment_status,checked_out_at FROM bookings WHERE id=?', (booking_id,)).fetchone()
        self.assertEqual(row['status'], 'completed')
        self.assertGreater(row['amount'], 0)
        self.assertEqual(row['payment_status'], 'demo_recorded')
        self.assertIsNotNone(row['checked_out_at'])
        admin_page = self.client.get('/admin')
        self.assertIn(b'Recent recorded revenue', admin_page.data)

    def test_non_admin_cannot_access_admin(self):
        response = self.client.get('/admin', follow_redirects=True)
        self.assertIn(b'Good day', response.data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
