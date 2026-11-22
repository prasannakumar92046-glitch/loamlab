"""OPTIONAL: fills the local database with DEMO customers, bookings and reports so you can preview the dashboard,
sample queue and PDF layout. All numbers below are PLACEHOLDERS for layout testing — they are not real measurements.
Run once:  python seed_demo.py        Remove demo data: delete data/loamlab.sqlite3 (and uploads/)."""
import json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
import app as A

A.init_db()
now = datetime.now()
def ts(days): return (now - timedelta(days=days)).isoformat(timespec='seconds')

with A.db() as c:
    if c.execute("SELECT 1 FROM appointments").fetchone():
        print('Demo data already present.'); raise SystemExit
    def user(n, e, ph):
        ex = c.execute('SELECT id FROM users WHERE email=?', (e,)).fetchone()
        if ex: return ex['id']
        return c.execute('INSERT INTO users(name,email,phone,password,role,created_at) VALUES(?,?,?,?,?,?)',
                         (n, e, ph, generate_password_hash('Farmer@123'), 'customer', ts(40))).lastrowid
    ravi = user('Ravi Kumar', 'farmer@loamlab.local', '+91 90000 00001'); meera = user('Meera Shetty', 'meera@loamlab.local', '+91 90000 00002')
    admin = c.execute("SELECT id FROM users WHERE role='admin'").fetchone()['id']

    def appt(uid, farm, addr, dist, crop, acres, panel, status, d, note=''):
        code = A.code('LL'); cur = c.execute('INSERT INTO appointments(code,user_id,farm_name,address,district,state,crop,sample_type,area_acres,panel,sample_date,notes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (code, uid, farm, addr, dist, 'Karnataka', crop, 'Soil', acres, panel, (now + timedelta(days=3)).date().isoformat(), note, status, ts(d), ts(max(d - 2, 0))))
        aid = cur.lastrowid; seq = A.TRACK[:A.TRACK.index(status) + 1] if status in A.TRACK else ['Requested', 'Cancelled']
        for i, s in enumerate(seq):
            c.execute('INSERT INTO status_log(appointment_id,status,note,changed_by,created_at) VALUES(?,?,?,?,?)', (aid, s, 'Demo entry' if i else 'Booking received by LoamLab portal', admin, ts(d - i)))
        return aid

    def report(aid, vals, interp, reco):
        refs = {'pH': '6.0 - 7.5', 'Available Nitrogen': '280 - 560', 'Available Phosphorus': '> 22', 'Available Potassium': '110 - 280'}
        no = A.code('LLR')
        c.execute('INSERT INTO reports(appointment_id,report_no,lab_name,lab_address,lab_phone,lab_email,sample_received,tested_on,sample_condition,method_notes,results_json,reference_json,interpretation,recommendations,approved_by,designation,approved_at,attachment,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (aid, no, 'LoamLab Soil Testing Laboratory', 'Demo address, Mangaluru, Karnataka', '+91 00000 00000', 'lab@loamlab.local', (now - timedelta(days=6)).date().isoformat(), (now - timedelta(days=4)).date().isoformat(),
             'Air-dried, sieved (2 mm), sealed', 'DEMO: placeholder method notes for layout preview only.', json.dumps(vals), json.dumps({k: v for k, v in refs.items() if k in vals}), interp, reco, 'Demo Analyst', 'Senior Soil Chemist', ts(3), None, ts(3)))

    a1 = appt(ravi, 'Bidarahalli Farm', 'Survey No. 7, Bidarahalli', 'Mandya', 'Sugarcane', '8.1', 'Standard Fertility Panel', 'Completed', 20, 'Sugarcane plot, north section.')
    report(a1, {'pH': '6.9', 'EC': '0.42', 'Organic Carbon': '0.71', 'Available Nitrogen': '310', 'Available Phosphorus': '28', 'Available Potassium': '165'},
           'DEMO DATA — placeholder text for layout preview. Replace with the laboratory\'s own interpretation.', 'DEMO DATA — placeholder recommendations for layout preview only.\nSecond line to test wrapping.')
    a2 = appt(ravi, 'Karahalli Village Plot', 'Survey No. 42, Karahalli', 'Hassan', 'Paddy', '4.5', 'Complete Soil Health', 'Completed', 35, 'Paddy field, second crop season.')
    report(a2, {'pH': '5.8', 'EC': '0.9', 'Organic Carbon': '0.55', 'Available Nitrogen': '240', 'Available Phosphorus': '14', 'Available Potassium': '120', 'Zinc': '0.9', 'Iron': '14.2', 'Copper': '1.1', 'Manganese': '8.4', 'Boron': '0.4'},
           'DEMO DATA — placeholder interpretation.', 'DEMO DATA — placeholder recommendations.')
    appt(ravi, 'Alvas Estate', 'Moodbidri', 'Dakshina Kannada', 'Arecanut', '10', 'Standard Fertility Panel', 'Requested', 2, 'Black soil')
    appt(ravi, 'Plot 14', 'Nandihalli Estate, Sakleshpur', 'Hassan', 'Coffee', '3.2', 'Micronutrient Screen', 'In Lab', 9)
    appt(meera, 'Glenmore Coffee Estate', 'Block C, Chikmagalur', 'Chikmagalur', 'Coffee', '12', 'Micronutrient Screen', 'Sample Collected', 7, 'Arabica, yield dropped this season.')
    appt(meera, 'Home garden', 'Bantwal', 'Dakshina Kannada', 'Vegetables', '0.5', 'Standard Fertility Panel', 'Confirmed', 3)
    appt(meera, 'North paddock', 'Puttur', 'Dakshina Kannada', 'Paddy', '2', 'Complete Soil Health', 'Cancelled', 12)
print('Demo data created.\n  Customer: farmer@loamlab.local / Farmer@123\n  Admin:    admin@loamlab.local / LabAdmin@123')
