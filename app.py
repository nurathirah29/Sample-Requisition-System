import os
import smtplib
import datetime
import mysql.connector
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, session, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sp_secret_2025')

DB_HOST = "localhost"
DB_USER = "root"
DB_PASS = "ERMsql999$"
DB_NAME = "sample_portal"

SMTP_HOST = "mail.excel-rim.com"
SMTP_PORT = 587
SMTP_USER = "esystem@excel-rim.com"        
SMTP_PASS = "Ersystem@2024$$"
SYSTEM_LINK = "http://192.168.110.99:921/"


# ─────────────────────────────────────────
# DB
# ─────────────────────────────────────────
def get_db():
    return mysql.connector.connect(
        host=DB_HOST, user=DB_USER,
        password=DB_PASS, database=DB_NAME
    )


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def send_email(to, subject, body):
    """Send HTML email — silently fails if SMTP not configured."""
    try:
        msg = MIMEText(body, 'html')
        msg['Subject'] = subject
        msg['From']    = SMTP_USER
        msg['To']      = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    except Exception as e:
        print(f"[Email] {e}")


def notify(user_id, message, request_id):
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO notifications (user_id, message, request_id) VALUES (%s,%s,%s)",
        (user_id, message, request_id)
    )
    db.commit()
    db.close()


def log_activity(request_id, action, performed_by, remarks=""):
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO activity_logs (request_id, action, performed_by, remarks) VALUES (%s,%s,%s,%s)",
        (request_id, action, performed_by, remarks)
    )
    db.commit()
    db.close()


def get_user(user_id):
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    row = cur.fetchone()
    db.close()
    return row


def get_initials(user_id):
    try:
        u = get_user(user_id)
        if u and u.get('name'):
            parts = u['name'].split()
            return (parts[0][0] + parts[-1][0]).upper()
    except:
        pass
    return "U"


def get_unread(user_id):
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=0", (user_id,))
    count = cur.fetchone()[0]
    db.close()
    return count


def ctx():
    """Base template context for every authenticated page."""
    uid = session.get('user_id')
    return dict(
        initials=get_initials(uid),
        name=session.get('name', ''),
        unread=get_unread(uid),
    )

ALLOWED_FIELDS = {'requester_id', 'assigned_to', 'status'}

def count_status(field, val, uid=None):
    """Count rows by status. If uid given, filter by requester_id."""
    db  = get_db()
    cur = db.cursor()
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Invalid field: {field}")
    if uid:
        cur.execute(f"SELECT COUNT(*) FROM sample_requests WHERE {field}=%s AND status=%s", (uid, val))
    else:
        cur.execute(f"SELECT COUNT(*) FROM sample_requests WHERE status=%s", (val,))
    return cur.fetchone()[0]


def save_samples(cur, req_id, form):
    cur.execute("DELETE FROM sample_items WHERE request_id=%s", (req_id,))
    i = 0
    while True:
        name = form.get(f'sample_name_{i}')  # ← fixed typo
        if name is None:
            break
        cur.execute(
            "INSERT INTO sample_items (request_id, sample_name, quantity, packing_opt) VALUES (%s,%s,%s,%s)",
            (req_id, name, form.get(f'quantity_{i}', ''), form.get(f'packing_opt_{i}', ''))
        )
        i += 1

# ─────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        db  = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email=%s", (request.form['email'],))
        user = cur.fetchone()
        if user:
            session['user_id'] = user['id']
            session['role']    = user['role']
            session['name']    = user['name']
            return redirect('/erj' if user['role'] == 'ERJ' else '/erm')
        error = "No account found with that email."
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ─────────────────────────────────────────
# ERJ DASHBOARD
# ─────────────────────────────────────────
@app.route('/erj')
def erj():
    if session.get('role') != 'ERJ':
        return redirect('/')
    uid = session['user_id']
    sf = request.args.get('status', 'all')
    q = request.args.get('q', '')
    page = int(request.args.get('page', 1))
    per_page = 15

    db  = get_db()
    cur = db.cursor(dictionary=True)
    sql = """
        SELECT sr.*,
               u.name AS requester_name,
               (SELECT COUNT(*) FROM sample_items si WHERE si.request_id = sr.id) AS item_count
        FROM sample_requests sr
        LEFT JOIN users u ON sr.requester_id = u.id
        WHERE 1=1
    """
    params = []
    if sf != 'all':
        sql += " AND sr.status=%s"; params.append(sf)
    if q:
        sql += " AND (sr.request_no LIKE %s OR sr.customer LIKE %s OR sr.model LIKE %s OR u.name LIKE %s)"
        params += [f'%{q}%'] * 4

    count_sql = f"SELECT COUNT(*) FROM ({sql}) AS sub"
    cur.execute(count_sql, params)
    total = cur.fetchone()['COUNT(*)']
    total_pages = max(1, -(-total // per_page))

    sql += " ORDER BY sr.created_at DESC LIMIT %s OFFSET %s"
    params += [per_page, (page - 1) * per_page]
    cur.execute(sql, params)
    rows = cur.fetchall()

    # Workflow: Open → Completed → Closed
    stats = {s: count_status('status', s) for s in ('Open', 'Completed', 'Closed')}

    return render_template('erj.html', rows=rows, stats=stats, sf=sf, q=q, page=page, total_pages=total_pages, **ctx())


# ─────────────────────────────────────────
# ERJ — SUBMIT NEW REQUEST
#   Status starts as Open immediately
# ─────────────────────────────────────────
@app.route('/submit', methods=['POST'])
def submit():
    if session.get('role') != 'ERJ':
        return redirect('/')
    db  = get_db()
    cur = db.cursor()

    today = datetime.datetime.now().strftime('%y%m%d')
    cur.execute("SELECT COUNT(*) FROM sample_requests WHERE DATE(created_at)=CURDATE()")
    seq = cur.fetchone()[0] + 1
    request_no = f"SR-{today}-{str(seq).zfill(3)}"

    f = request.form
    cur.execute("""
        INSERT INTO sample_requests
          (request_no, requester_id, customer, pic, model, mass_prod,
           ship_to, price_between, freight_cost, ship_mode, ship_term, request_delivery_date,
           dev_request_no, inspection_report, remark, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Open')
    """, (
        request_no, session['user_id'],
        f.get('customer'), f.get('pic'), f.get('model'), f.get('mass_prod'),
        f.get('ship_to'), f.get('price_between'),
        f.get('freight_cost'), f.get('ship_mode'), f.get('ship_term'),
        f.get('request_delivery_date') or None,
        f.get('dev_request_no'), f.get('inspection_report'), f.get('remark')
    ))
    req_id = cur.lastrowid
    save_samples(cur, req_id, f)
    db.commit()

    log_activity(req_id, 'Request Created', session['user_id'], 'Submitted by ERJ — status set to Open')

    # Notify every ERM
    cur2 = db.cursor(dictionary=True)
    cur2.execute("SELECT * FROM users WHERE role='ERM'")
    for erm in cur2.fetchall():
        notify(erm['id'],
               f"New request {request_no} from {session['name']} — {f.get('customer')} / {f.get('model')}",
               req_id)
        
        cur3 = db.cursor(dictionary=True)
        cur3.execute("SELECT * FROM sample_items WHERE request_id=%s", (req_id,))
        samples = cur3.fetchall()
        created_date = datetime.datetime.now().strftime('%d %b %Y')

        sample_rows = ''.join([
            f"<tr style='background:{'#ffffff' if i % 2 == 0 else '#f9fafb'}'>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #e5eaf2;font-size:12px'>{i+1}</td>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #e5eaf2;font-size:12px'>{s['sample_name'] or '—'}</td>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #e5eaf2;font-size:12px'>{s['quantity'] or '—'}</td>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #e5eaf2;font-size:12px'>{s['packing_opt'] or '—'}</td>"
            f"</tr>"
            for i, s in enumerate(samples)
        ])

        send_email(
            erm['email'],
            f"New Sample Request: {request_no}",
            f"""
            <div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;color:#0d1f3c">

                <h3 style="margin:0 0 16px">New Sample Request — {request_no}</h3>

                <table style="border-collapse:collapse;margin-bottom:20px;font-size:13px">
                    <tr>
                    <td style="padding:3px 16px 3px 0;color:#64748b;white-space:nowrap">Created Date</td>
                    <td style="padding:3px 0;color:#64748b">:</td>
                    <td style="padding:3px 0 3px 12px;font-weight:600">{created_date}</td>
                    </tr>
                    <tr>
                    <td style="padding:3px 16px 3px 0;color:#64748b;white-space:nowrap">From</td>
                    <td style="padding:3px 0;color:#64748b">:</td>
                    <td style="padding:3px 0 3px 12px;font-weight:600">{session['name']}</td>
                    </tr>
                    <tr>
                    <td style="padding:3px 16px 3px 0;color:#64748b;white-space:nowrap">Customer</td>
                    <td style="padding:3px 0;color:#64748b">:</td>
                    <td style="padding:3px 0 3px 12px;font-weight:600">{f.get('customer') or '—'}</td>
                    </tr>
                    <tr>
                    <td style="padding:3px 16px 3px 0;color:#64748b;white-space:nowrap">Model</td>
                    <td style="padding:3px 0;color:#64748b">:</td>
                    <td style="padding:3px 0 3px 12px;font-weight:600">{f.get('model') or '—'}</td>
                    </tr>
                    <tr>
                    <td style="padding:3px 16px 3px 0;color:#64748b;white-space:nowrap">Request Delivery Date</td>
                    <td style="padding:3px 0;color:#64748b">:</td>
                    <td style="padding:3px 0 3px 12px;font-weight:600">{f.get('request_delivery_date') or '—'}</td>
                    </tr>
                </table>

                <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
                    <thead>
                    <tr style="background:#f4f6fb">
                        <th style="padding:8px 10px;text-align:left;font-size:11px;color:#64748b;border-bottom:2px solid #e5eaf2">#</th>
                        <th style="padding:8px 10px;text-align:left;font-size:11px;color:#64748b;border-bottom:2px solid #e5eaf2">Sample</th>
                        <th style="padding:8px 10px;text-align:left;font-size:11px;color:#64748b;border-bottom:2px solid #e5eaf2">Quantity</th>
                        <th style="padding:8px 10px;text-align:left;font-size:11px;color:#64748b;border-bottom:2px solid #e5eaf2">Packing Opt</th>
                    </tr>
                    </thead>
                    <tbody>{sample_rows}</tbody>
                </table>

                <p>Log in <a href="{SYSTEM_LINK}" style="color: #007bff; font-weight: bold;">here </a>to review and set a possible delivery date.</p>
                <br>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 12px; color: #999;">
                    This email is auto-generated by system. Please do not reply to this email.
                </p>
            </div>
            """
        )
    return redirect('/erj')


# ─────────────────────────────────────────
# ERJ — EDIT REQUEST  (modal, POST only)
#   Allowed when status = Open or Completed
# ─────────────────────────────────────────
@app.route('/erj/edit/<int:id>', methods=['POST'])
def erj_edit(id):
    if session.get('role') != 'ERJ':
        return redirect('/')
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM sample_requests WHERE id=%s AND requester_id=%s", (id, session['user_id']))
    req = cur.fetchone()
    if not req or req['status'] not in ('Open', 'Completed'):
        return redirect('/erj')

    f = request.form
    cur2 = db.cursor()
    cur2.execute("""
        UPDATE sample_requests SET
          customer=%s, pic=%s, model=%s, mass_prod=%s, ship_to=%s,
          price_between=%s, freight_cost=%s, ship_mode=%s, ship_term=%s,
          request_delivery_date=%s, dev_request_no=%s, inspection_report=%s, 
          remark=%s, updated_at=NOW()
        WHERE id=%s
    """, (
        f.get('customer'), f.get('pic'), f.get('model'), f.get('mass_prod'), f.get('ship_to'),  
        f.get('price_between'), f.get('freight_cost'),f.get('ship_mode'),   f.get('ship_term'),
        f.get('request_delivery_date') or None, f.get('dev_request_no'), f.get('inspection_report'), 
        f.get('remark'),
        id
    ))
    save_samples(cur2, id, f)
    db.commit()
    log_activity(id, f'Edited by {session["name"]}', session['user_id'], f.get('edit_remark', ''))

    # Notify all ERMs
    cur3 = db.cursor(dictionary=True)
    cur3.execute("SELECT * FROM users WHERE role='ERM'")
    for erm in cur3.fetchall():
        notify(erm['id'],
               f"Request {req['request_no']} was edited by {session['name']}.",
               id)
        send_email(
            erm['email'],
            f"Edited Sample Request {req['request_no']}",
            f"""<p>Request <b>{req['request_no']}</b> has been edited by <b>{session['name']}</b>.</p>
            <p>Log in <a href="{SYSTEM_LINK}" style="color: #007bff; font-weight: bold;">here </a>to review the changes.</p>
            <p><b>Customer:</b> {f.get('customer')}<br>
            <b>Model:</b> {f.get('model')}"""
        )
    return redirect('/erj')


# ─────────────────────────────────────────
# ERJ — CLOSE REQUEST  (Completed → Closed)
# ─────────────────────────────────────────
@app.route('/erj/close/<int:id>', methods=['POST'])
def erj_close(id):
    if session.get('role') != 'ERJ':
        return redirect('/')
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT sr.*, u.name AS assignee_name, u.email AS assignee_email
        FROM sample_requests sr
        LEFT JOIN users u ON sr.assigned_to = u.id
        WHERE sr.id=%s AND sr.requester_id=%s
    """, (id, session['user_id']))
    req = cur.fetchone()
    # Only allow closing from Completed status
    if not req or req['status'] != 'Completed':
        return redirect('/erj')

    close_remark = request.form.get('close_remark', '')
    cur2 = db.cursor()
    cur2.execute(
        "UPDATE sample_requests SET status='Closed', updated_at=NOW() WHERE id=%s", (id,)
    )
    db.commit()
    log_activity(id, f'Closed by {session["name"]}', session['user_id'], close_remark)

    # Notify assigned ERM if any
    if req.get('assigned_to'):
        notify(req['assigned_to'],
               f"Request {req['request_no']} has been closed by {session['name']}.", id)
        
    return redirect('/erj')


# ─────────────────────────────────────────
# ERM DASHBOARD
# ─────────────────────────────────────────
@app.route('/erm')
def erm():
    if session.get('role') != 'ERM':
        return redirect('/')
    uid = session['user_id']
    sf  = request.args.get('status', 'all')
    q   = request.args.get('q', '')
    page = int(request.args.get('page', 1))
    per_page = 15

    db  = get_db()
    cur = db.cursor(dictionary=True)
    sql = """SELECT sr.*, 
                u.name AS requester_name,
                (SELECT COUNT(*) FROM sample_items si WHERE si.request_id = sr.id) AS item_count
             FROM sample_requests sr
             LEFT JOIN users u ON sr.requester_id = u.id"""
    params = []
    conds  = []
    if sf != 'all':
        conds.append("sr.status=%s"); params.append(sf)
    if q:
        conds.append("(sr.request_no LIKE %s OR sr.customer LIKE %s OR sr.model LIKE %s OR u.name LIKE %s)")
        params += [f'%{q}%'] * 4
    if conds:
        sql += " WHERE " + " AND ".join(conds)

    count_sql = f"SELECT COUNT(*) FROM ({sql}) AS sub"
    cur.execute(count_sql, params)
    total = cur.fetchone()['COUNT(*)']
    total_pages = max(1, -(-total // per_page))

    sql += " ORDER BY sr.created_at DESC LIMIT %s OFFSET %s"
    params += [per_page, (page - 1) * per_page]
    cur.execute(sql, params)
    rows = cur.fetchall()

    stats = {s: count_status('status', s) for s in ('Open', 'Completed', 'Closed')}
    return render_template('erm.html', rows=rows, stats=stats, sf=sf, q=q, my_id=uid, page=page, total_pages=total_pages, **ctx())


# ─────────────────────────────────────────
# ERM — UPDATE STATUS  (modal POST)
#   Setting possible_delivery_date auto-sets status to Completed
# ─────────────────────────────────────────
@app.route('/erm/update/<int:id>', methods=['POST'])
def erm_update(id):
    if session.get('role') != 'ERM':
        return redirect('/')
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT sr.*, u.name AS requester_name, u.email AS requester_email
        FROM sample_requests sr
        LEFT JOIN users u ON sr.requester_id = u.id
        WHERE sr.id=%s
    """, (id,))
    req = cur.fetchone()
    if not req:
        return redirect('/erm')

    possible   = request.form.get('possible_delivery_date') or None
    erm_remark = request.form.get('erm_remark', '')

    # Auto-set status to Completed when possible_delivery_date is provided
    if possible:
        new_status = 'Completed'
    else:
        new_status = req['status'] 

    cur2 = db.cursor()
    cur2.execute("""
        UPDATE sample_requests
        SET status=%s, possible_delivery_date=%s,
            assigned_to=%s, updated_at=NOW()
        WHERE id=%s
    """, (new_status, possible, session['user_id'], id))
    db.commit()
    log_activity(id, f'Status → {new_status}', session['user_id'], erm_remark)

    notify(req['requester_id'],
           f"Your request {req['request_no']} has been updated to {new_status}"
           + (f" — Possible delivery: {possible}" if possible else "") + ".",
           id)
    if req.get('requester_email'):
        send_email(
            req['requester_email'],
            f"Sample Request {req['request_no']} — {new_status}",
            f"""<p>Your request <b>{req['request_no']}</b> is now <b>{new_status}</b>.</p>
            {"<p><b>Possible Delivery Date:</b> " + str(possible) + "</p>" if possible else ""}
            {"<p><b>Remarks:</b> " + erm_remark + "</p>" if erm_remark else ""}
            <p>Log in <a href="{SYSTEM_LINK}" style="color: #007bff; font-weight: bold;">here </a>to review and close the request when ready.</p>"""
        )
    return redirect('/erm')


# ─────────────────────────────────────────
# SHARED — VIEW DETAIL (modal data via JSON)
# ─────────────────────────────────────────
@app.route('/detail/<int:id>')
def detail(id):
    """Returns full request + activity log as JSON for the detail modal."""
    uid = session.get('user_id')
    if not uid:
        return jsonify({}), 401

    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT sr.*,
               u.name  AS requester_name,
               a.name  AS assignee_name
        FROM sample_requests sr
        LEFT JOIN users u ON sr.requester_id = u.id
        LEFT JOIN users a ON sr.assigned_to   = a.id
        WHERE sr.id=%s
    """, (id,))
    req = cur.fetchone()
    if not req:
        return jsonify({}), 404

    # Serialize dates
    date_keys = [k for k, v in req.items() if isinstance(v, (datetime.date, datetime.datetime))]
    for k in date_keys:
        v = req[k]
        if v:
            req[k + '_raw'] = v.strftime('%Y-%m-%d')
            req[k]          = v.strftime('%d %b %Y')
        else:
            req[k] = None

    cur.execute("""
        SELECT al.action, al.remarks,
               u.name AS actor,
               al.created_at
        FROM activity_logs al
        LEFT JOIN users u ON al.performed_by = u.id
        WHERE al.request_id=%s
        ORDER BY al.created_at ASC
    """, (id,))
    logs = cur.fetchall()
    for l in logs:
        if isinstance(l.get('created_at'), (datetime.date, datetime.datetime)):
            l['created_at'] = l['created_at'].strftime('%d %b %Y, %H:%M')
    
    # After fetching req, add:
    cur.execute("SELECT * FROM sample_items WHERE request_id=%s ORDER BY id", (id,))
    samples = cur.fetchall()

    # Add samples to the jsonify return:
    return jsonify(req=req, logs=logs, samples=samples, role=session.get('role'), my_id=uid)


# ─────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────
@app.route('/notifications')
def notifications():
    uid = session.get('user_id')
    if not uid:
        return redirect('/')
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC", (uid,))
    notifs = cur.fetchall()
    cur2 = db.cursor()
    cur2.execute("UPDATE notifications SET is_read=1 WHERE user_id=%s", (uid,))
    db.commit()
    db.close()
    return render_template('notifications.html', notifs=notifs, **ctx())


# ─────────────────────────────────────────
# UNREAD COUNT  (for live badge refresh)
# ─────────────────────────────────────────
@app.route('/api/unread')
def api_unread():
    uid = session.get('user_id')
    if not uid:
        return jsonify(count=0)
    return jsonify(count=get_unread(uid))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)