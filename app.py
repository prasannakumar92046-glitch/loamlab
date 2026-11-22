import os, sqlite3, uuid, json, io
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import report_pdf

BASE=os.path.abspath(os.path.dirname(__file__))
for folder in ('data','uploads','generated_reports'): os.makedirs(os.path.join(BASE,folder),exist_ok=True)
app=Flask(__name__); app.secret_key=os.environ.get('SECRET_KEY','change-this-secret-key-before-deployment')
app.config['MAX_CONTENT_LENGTH']=15*1024*1024
DB=os.path.join(BASE,'data','loamlab.sqlite3')
ALLOWED={'pdf','png','jpg','jpeg'}
STATUSES=['Requested','Confirmed','Sample Collected','In Lab','Completed','Cancelled']
PANELS={
 'Standard Fertility Panel':['pH','EC','Organic Carbon','Available Nitrogen','Available Phosphorus','Available Potassium'],
 'Micronutrient Screen':['Zinc','Iron','Copper','Manganese','Boron'],
 'Complete Soil Health':['pH','EC','Organic Carbon','Available Nitrogen','Available Phosphorus','Available Potassium','Zinc','Iron','Copper','Manganese','Boron']}
UNITS={'pH':'pH units','EC':'dS/m','Organic Carbon':'%','Available Nitrogen':'kg/ha','Available Phosphorus':'kg/ha','Available Potassium':'kg/ha','Zinc':'mg/kg','Iron':'mg/kg','Copper':'mg/kg','Manganese':'mg/kg','Boron':'mg/kg'}
# Indicative guidance only. Real lab-specific ranges/methods must be configured by the laboratory.
GUIDANCE={'pH':'Interpret using crop and local soil guidance','EC':'Interpret using crop tolerance and extraction method','Organic Carbon':'Method- and region-dependent','Available Nitrogen':'Method-, crop- and region-dependent','Available Phosphorus':'Method- and extractant-dependent','Available Potassium':'Method- and crop-dependent','Zinc':'Method- and crop-dependent','Iron':'Method- and soil-pH-dependent','Copper':'Method- and crop-dependent','Manganese':'Method- and soil-pH-dependent','Boron':'Method- and crop-dependent'}

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def init_db():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,phone TEXT,password TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'customer',created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id),farm_name TEXT,address TEXT NOT NULL,district TEXT,state TEXT,crop TEXT,sample_type TEXT,area_acres TEXT,panel TEXT NOT NULL,sample_date TEXT,notes TEXT,status TEXT NOT NULL DEFAULT 'Requested',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY,appointment_id INTEGER NOT NULL UNIQUE REFERENCES appointments(id),report_no TEXT UNIQUE NOT NULL,lab_name TEXT NOT NULL,lab_address TEXT,lab_phone TEXT,lab_email TEXT,sample_received TEXT,tested_on TEXT,sample_condition TEXT,method_notes TEXT,results_json TEXT NOT NULL,reference_json TEXT NOT NULL DEFAULT '{}',interpretation TEXT,recommendations TEXT,approved_by TEXT,designation TEXT,approved_at TEXT,attachment TEXT,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS status_log(id INTEGER PRIMARY KEY,appointment_id INTEGER NOT NULL REFERENCES appointments(id),status TEXT NOT NULL,note TEXT,changed_by INTEGER REFERENCES users(id),created_at TEXT NOT NULL);
  CREATE INDEX IF NOT EXISTS idx_appt_user ON appointments(user_id); CREATE INDEX IF NOT EXISTS idx_appt_status ON appointments(status);''')
  # Seed a demo admin only once. Change this password immediately after first sign-in.
  if not c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone():
   c.execute('INSERT INTO users(name,email,phone,password,role,created_at) VALUES(?,?,?,?,?,?)',('LoamLab Administrator','admin@loamlab.local','','','admin',datetime.now().isoformat(timespec='seconds')))
   c.execute('UPDATE users SET password=? WHERE email=?',(generate_password_hash('LabAdmin@123'),'admin@loamlab.local'))
  # Demo customer so the unified login can be tried straight away (demo only - delete before deployment).
  if not c.execute("SELECT id FROM users WHERE email='farmer@loamlab.local'").fetchone():
   c.execute('INSERT INTO users(name,email,phone,password,role,created_at) VALUES(?,?,?,?,?,?)',('Ravi Kumar','farmer@loamlab.local','+91 90000 00001',generate_password_hash('Farmer@123'),'customer',datetime.now().isoformat(timespec='seconds')))

def login_required(fn):
 @wraps(fn)
 def wrap(*a,**kw):
  if not session.get('uid'): return redirect(url_for('login'))
  return fn(*a,**kw)
 return wrap

def admin_required(fn):
 @wraps(fn)
 def wrap(*a,**kw):
  if not session.get('uid') or session.get('role')!='admin': return redirect(url_for('login',role='admin'))
  return fn(*a,**kw)
 return wrap

def code(prefix): return f'{prefix}-{datetime.now():%y%m%d}-{uuid.uuid4().hex[:6].upper()}'
def now(): return datetime.now().isoformat(timespec='seconds')
def current_user():
 if not session.get('uid'): return None
 with db() as c: return c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
@app.template_filter('fromjson')
def fromjson(v):
 try:return json.loads(v or '{}')
 except:return {}
TRACK=['Requested','Confirmed','Sample Collected','In Lab','Completed']
NEXT_STAGE={'Requested':'Confirmed','Confirmed':'Sample Collected','Sample Collected':'In Lab','In Lab':'Completed'}
DEMO=os.environ.get('LOAMLAB_DEMO','1')=='1'
@app.context_processor
def inject(): return {'user':current_user(),'panels':PANELS,'statuses':STATUSES,'TRACK':TRACK,'NEXT_STAGE':NEXT_STAGE,'DEMO':DEMO,'units':UNITS}

def _num(v):
 try:return float(str(v).replace(',','').strip())
 except Exception:return None

def result_view(results_json):
 """Turn stored lab values into display data. Nothing is invented: only entered values are shown;
 bars are relative within one unit (kg/ha) and the pH marker uses the universal 0-14 scale."""
 res=json.loads(results_json or '{}');view={'ph':None,'bars':[],'chips':[]}
 for k,v in res.items():
  n=_num(v)
  if k=='pH' and n is not None:view['ph']={'value':v,'left':max(0,min(100,n/14*100))}
  elif k in ('Available Nitrogen','Available Phosphorus','Available Potassium'):
   view['bars'].append({'name':k.replace('Available ','')+' ('+{'Nitrogen':'N','Phosphorus':'P','Potassium':'K'}[k.replace('Available ','')]+')','value':v,'unit':UNITS.get(k,''),'n':n})
  else:view['chips'].append({'name':k,'value':v,'unit':UNITS.get(k,'')})
 mx=max([b['n'] for b in view['bars'] if b['n'] is not None] or [0])
 for b in view['bars']:b['pct']=round(100*b['n']/mx) if (b['n'] is not None and mx>0) else 0
 return view

def stage_pct(status):
 return round(100*TRACK.index(status)/(len(TRACK)-1)) if status in TRACK else 0

@app.route('/')
def home(): return render_template('home.html')
@app.route('/portal')
def portal(): return redirect(url_for('login'))
@app.route('/register',methods=['GET','POST'])
def register():
 if request.method=='POST':
  name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); pw=request.form.get('password','')
  if not name or '@' not in email or len(pw)<8: flash('Enter your name, valid email and a password of at least 8 characters.','error')
  else:
   try:
    with db() as c:c.execute('INSERT INTO users(name,email,phone,password,role,created_at) VALUES(?,?,?,?,?,?)',(name,email,request.form.get('phone','').strip(),generate_password_hash(pw),'customer',now()))
    flash('Customer account created. Sign in to continue.','success');return redirect(url_for('customer_login'))
   except sqlite3.IntegrityError:flash('An account with this email already exists.','error')
 return render_template('register.html')
@app.route('/login',methods=['GET','POST'])
def login():
 role=request.values.get('role','customer')
 if role not in ('customer','admin'): role='customer'
 if request.method=='POST':
  email=request.form.get('email','').strip().lower()
  with db() as c:u=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
  if not u or not check_password_hash(u['password'],request.form.get('password','')):
   flash('Sign-in failed. Check your email and password.','error')
  elif u['role']!=role:
   flash('This account is a %s account. Switch the role above and try again.'%('Lab Admin' if u['role']=='admin' else 'Customer'),'error')
  else:
   session.clear();session.update(uid=u['id'],role=u['role'],name=u['name'])
   return redirect(url_for('admin_dashboard' if role=='admin' else 'dashboard'))
 return render_template('login.html',role=role)
@app.route('/customer-login')
def customer_login():return redirect(url_for('login',role='customer'))
@app.route('/admin-login')
def admin_login():return redirect(url_for('login',role='admin'))
@app.route('/logout')
def logout():session.clear();return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
 if session.get('role')!='customer':return redirect(url_for('admin_dashboard'))
 with db() as c:rows=c.execute('SELECT a.*,r.report_no,r.results_json,r.interpretation FROM appointments a LEFT JOIN reports r ON r.appointment_id=a.id WHERE a.user_id=? ORDER BY a.id DESC',(session['uid'],)).fetchall()
 items=[{'a':a,'view':result_view(a['results_json']) if a['results_json'] else None,'pct':stage_pct(a['status'])} for a in rows]
 return render_template('dashboard.html',items=items)

@app.route('/appointment/<int:aid>/cancel',methods=['POST'])
@login_required
def cancel_appointment(aid):
 with db() as c:
  a=c.execute('SELECT * FROM appointments WHERE id=?',(aid,)).fetchone()
  if not a or a['user_id']!=session['uid']:abort(404)
  if a['status']!='Requested':flash('Only requests that are still at the Requested stage can be cancelled. Please contact the laboratory.','error')
  else:
   stamp=now();c.execute("UPDATE appointments SET status='Cancelled',updated_at=? WHERE id=?",(stamp,aid));c.execute('INSERT INTO status_log(appointment_id,status,note,changed_by,created_at) VALUES(?,?,?,?,?)',(aid,'Cancelled','Cancelled by customer',session['uid'],stamp))
   flash('Your request was cancelled.','success')
 return redirect(url_for('dashboard'))
@app.route('/book',methods=['GET','POST'])
@login_required
def book():
 if session.get('role')!='customer':return redirect(url_for('admin_dashboard'))
 if request.method=='POST':
  panel=request.form.get('panel');address=request.form.get('address','').strip()
  if panel not in PANELS or not address:flash('Choose a valid panel and provide the sample location.','error')
  else:
   stamp=now();ref=code('LL')
   with db() as c:
    cur=c.execute('INSERT INTO appointments(code,user_id,farm_name,address,district,state,crop,sample_type,area_acres,panel,sample_date,notes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(ref,session['uid'],request.form.get('farm_name','').strip(),address,request.form.get('district','').strip(),request.form.get('state','').strip(),request.form.get('crop','').strip(),request.form.get('sample_type','Soil'),request.form.get('area_acres','').strip(),panel,request.form.get('sample_date') or None,request.form.get('notes','').strip(),'Requested',stamp,stamp))
    c.execute('INSERT INTO status_log(appointment_id,status,note,changed_by,created_at) VALUES(?,?,?,?,?)',(cur.lastrowid,'Requested','Booking received by LoamLab portal',session['uid'],stamp))
   flash(f'Booking received. Reference: {ref}','success');return redirect(url_for('dashboard'))
 return render_template('book.html',selected=request.args.get('panel') if request.args.get('panel') in PANELS else 'Standard Fertility Panel')
@app.route('/appointment/<int:aid>')
@login_required
def appointment(aid):
 with db() as c:
  a=c.execute('SELECT a.*,u.name customer_name,u.email,u.phone FROM appointments a JOIN users u ON u.id=a.user_id WHERE a.id=?',(aid,)).fetchone()
  if not a or (session['role']!='admin' and a['user_id']!=session['uid']):abort(404)
  logs=c.execute('SELECT * FROM status_log WHERE appointment_id=? ORDER BY id',(aid,)).fetchall();r=c.execute('SELECT * FROM reports WHERE appointment_id=?',(aid,)).fetchone()
 return render_template('appointment.html',a=a,logs=logs,report=r,view=result_view(r['results_json']) if r else None,pct=stage_pct(a['status']))

@app.route('/admin')
@admin_required
def admin_dashboard():
 q=request.args.get('q','').strip();status=request.args.get('status','')
 sql='SELECT a.*,u.name customer_name,u.phone,r.report_no FROM appointments a JOIN users u ON u.id=a.user_id LEFT JOIN reports r ON r.appointment_id=a.id WHERE 1=1';args=[]
 if status in STATUSES:sql+=' AND a.status=?';args.append(status)
 if q:sql+=' AND (a.code LIKE ? OR u.name LIKE ? OR u.email LIKE ?)';args += [f'%{q}%']*3
 sql+=' ORDER BY a.id DESC'
 with db() as c:
  rows=c.execute(sql,args).fetchall();counts={x['status']:x['n'] for x in c.execute('SELECT status,COUNT(*) n FROM appointments GROUP BY status')};total=c.execute('SELECT COUNT(*) n FROM appointments').fetchone()['n'];customers=c.execute("SELECT COUNT(*) n FROM users WHERE role='customer'").fetchone()['n'];reports=c.execute('SELECT COUNT(*) n FROM reports').fetchone()['n']
 return render_template('admin.html',rows=rows,counts=counts,total=total,customers=customers,reports=reports,q=q,filter_status=status,pending=counts.get('Requested',0)+counts.get('Confirmed',0),in_lab=counts.get('In Lab',0),pcts={x['id']:stage_pct(x['status']) for x in rows})
@app.route('/admin/appointment/<int:aid>',methods=['GET','POST'])
@admin_required
def admin_appointment(aid):
 with db() as c:
  a=c.execute('SELECT a.*,u.name customer_name,u.email,u.phone FROM appointments a JOIN users u ON u.id=a.user_id WHERE a.id=?',(aid,)).fetchone();report=c.execute('SELECT * FROM reports WHERE appointment_id=?',(aid,)).fetchone()
 if not a:abort(404)
 if request.method=='POST':
  action=request.form.get('action');stamp=now()
  if action=='status':
   s=request.form.get('status')
   if s not in STATUSES:abort(400)
   with db() as c:
    c.execute('UPDATE appointments SET status=?,updated_at=? WHERE id=?',(s,stamp,aid));c.execute('INSERT INTO status_log(appointment_id,status,note,changed_by,created_at) VALUES(?,?,?,?,?)',(aid,s,request.form.get('note','').strip(),session['uid'],stamp))
   flash('Sample stage updated and recorded in its audit trail.','success')
   if request.form.get('back')=='queue':return redirect(url_for('admin_dashboard'))
  elif action=='report':
   measured={};refs={}
   for p in PANELS[a['panel']]:
    v=request.form.get('result_'+p,'').strip();ref=request.form.get('ref_'+p,'').strip()
    if v:measured[p]=v
    if ref:refs[p]=ref
   if not measured:flash('Enter at least one measured laboratory result.','error')
   else:
    report_no=report['report_no'] if report else code('LLR');attachment=report['attachment'] if report else None;f=request.files.get('attachment')
    if f and f.filename:
     ext=f.filename.rsplit('.',1)[-1].lower()
     if ext not in ALLOWED:flash('Upload PDF, JPG or PNG only.','error');return redirect(url_for('admin_appointment',aid=aid))
     attachment=report_no+'_'+secure_filename(f.filename);f.save(os.path.join(BASE,'uploads',attachment))
    fields=(request.form.get('lab_name','LoamLab Soil Testing Laboratory').strip(),request.form.get('lab_address','').strip(),request.form.get('lab_phone','').strip(),request.form.get('lab_email','').strip(),request.form.get('sample_received') or None,request.form.get('tested_on') or None,request.form.get('sample_condition','').strip(),request.form.get('method_notes','').strip(),json.dumps(measured),json.dumps(refs),request.form.get('interpretation','').strip(),request.form.get('recommendations','').strip(),request.form.get('approved_by','').strip(),request.form.get('designation','').strip(),stamp,attachment)
    with db() as c:
     if report:c.execute('UPDATE reports SET lab_name=?,lab_address=?,lab_phone=?,lab_email=?,sample_received=?,tested_on=?,sample_condition=?,method_notes=?,results_json=?,reference_json=?,interpretation=?,recommendations=?,approved_by=?,designation=?,approved_at=?,attachment=? WHERE appointment_id=?',fields+(aid,))
     else:c.execute('INSERT INTO reports(appointment_id,report_no,lab_name,lab_address,lab_phone,lab_email,sample_received,tested_on,sample_condition,method_notes,results_json,reference_json,interpretation,recommendations,approved_by,designation,approved_at,attachment,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(aid,report_no)+fields+(stamp,))
     # Do not mark the test completed automatically: lab operator explicitly controls workflow.
    flash('Laboratory results saved. The PDF report is available to the customer. Update the sample stage separately when appropriate.','success')
  return redirect(url_for('admin_appointment',aid=aid))
 with db() as c:report=c.execute('SELECT * FROM reports WHERE appointment_id=?',(aid,)).fetchone();logs=c.execute('SELECT * FROM status_log WHERE appointment_id=? ORDER BY id DESC',(aid,)).fetchall()
 return render_template('admin_appointment.html',a=a,report=report,logs=logs,fields=PANELS[a['panel']],units=UNITS)

@app.route('/report/<int:aid>.pdf')
@login_required
def report_pdf_view(aid):
 with db() as c:r=c.execute('SELECT r.*,a.code,a.farm_name,a.address,a.district,a.state,a.crop,a.sample_type,a.area_acres,a.panel,a.user_id,a.created_at appt_created,u.name customer_name,u.email customer_email,u.phone customer_phone FROM reports r JOIN appointments a ON a.id=r.appointment_id JOIN users u ON u.id=a.user_id WHERE a.id=?',(aid,)).fetchone()
 if not r or (session.get('role')!='admin' and r['user_id']!=session.get('uid')):abort(404)
 out=report_pdf.build(r,json.loads(r['results_json'] or '{}'),json.loads(r['reference_json'] or '{}'),UNITS,GUIDANCE)
 return send_file(out,mimetype='application/pdf',as_attachment=True,download_name=r['report_no']+'.pdf')
@app.route('/attachment/<int:aid>')
@login_required
def attachment(aid):
 with db() as c:r=c.execute('SELECT reports.attachment,appointments.user_id FROM reports JOIN appointments ON appointments.id=reports.appointment_id WHERE appointments.id=?',(aid,)).fetchone()
 if not r or not r['attachment'] or (session.get('role')!='admin' and r['user_id']!=session.get('uid')):abort(404)
 return send_file(os.path.join(BASE,'uploads',r['attachment']),as_attachment=True)
@app.errorhandler(403)
def forbidden(e):return render_template('error.html',code=403,message='You do not have permission to access this area.'),403
@app.errorhandler(404)
def missing(e):return render_template('error.html',code=404,message='The requested page or record was not found.'),404
if __name__=='__main__':init_db();app.run(host='127.0.0.1',port=5000,debug=False)
