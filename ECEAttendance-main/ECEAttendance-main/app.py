import os
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_socketio import SocketIO, emit
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
import pandas as pd

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret')
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://STUDENT:STUDENT@cluster0.r0jc0ch.mongodb.net/?appName=Cluster0')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'ECEADMIN')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'ADMIN@ECE')

# Connect to MongoDB
# Connect to MongoDB
client = MongoClient(MONGO_URI)
try:
    db = client.get_database()
except:
    db = client['attendance_db'] # Fallback if URI doesn't validly specify one
students_col = db['students']
attendance_col = db['attendance']
events_col = db['events']
admins_col = db['admins']

# Initialize SocketIO
socketio = SocketIO(app, async_mode='threading')

from functools import wraps
def requires_super_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in') or session.get('username') != 'ECEADMIN':
            return jsonify({'error': 'Unauthorized: Only ECEADMIN can perform this action'}), 403
        return f(*args, **kwargs)
    return decorated

# Branch Mapping
BRANCH_MAP = {
    '02': 'EEE',
    '04': 'ECE',
    '14': 'ECT',
    '43': 'CAI',
    '61': 'AIM',
    '44': 'CSD',
    '05': 'CSE',
    '06': 'CST'
}

def detect_branch(roll_number):
    if not roll_number or len(roll_number) < 8:
        return 'UNKNOWN'
    code = roll_number[6:8]
    return BRANCH_MAP.get(code, 'UNKNOWN')

def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')

@app.route('/')
def index():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        
        # Priority: Check database for admins
        admin = admins_col.find_one({'username': username, 'password': password})
        if admin:
            session['logged_in'] = True
            session['admin_id'] = str(admin['_id'])
            session['username'] = username
            return redirect(url_for('dashboard'))
                
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/api/admins', methods=['GET', 'POST'])
@requires_super_admin
def admins_api():
    if request.method == 'GET':
        admins = list(admins_col.find({}, {'password': 0})) # Don't send passwords
        for a in admins:
            a['_id'] = str(a['_id'])
        return jsonify(admins)
        
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({'error': 'Username and Password required'}), 400
            
        if admins_col.find_one({'username': username}):
            return jsonify({'error': 'Username already exists'}), 400
            
        admins_col.insert_one({'username': username, 'password': password})
        return jsonify({'status': 'SUCCESS'})

@app.route('/api/admins/<admin_id>', methods=['DELETE'])
@requires_super_admin
def delete_admin_api(admin_id):
    # Prevet self-deletion
    if session.get('admin_id') == admin_id:
        return jsonify({'error': 'You cannot delete yourself'}), 400
        
    # Prevent deleting the core ECEADMIN via API if possible
    admin_to_del = admins_col.find_one({'_id': ObjectId(admin_id)})
    if admin_to_del and admin_to_del.get('username') == 'ECEADMIN':
        return jsonify({'error': 'ECEADMIN cannot be deleted'}), 400
        
    res = admins_col.delete_one({'_id': ObjectId(admin_id)})
    if res.deleted_count > 0:
        return jsonify({'status': 'SUCCESS'})
    return jsonify({'error': 'Admin not found'}), 404

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/api/mark_attendance', methods=['POST'])
def mark_attendance_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    roll_number = data.get('roll_number')
    event_id = data.get('event_id')
    
    if not roll_number or not event_id:
        return jsonify({'error': 'Roll number and Event ID required'}), 400

    roll_number = roll_number.upper().strip()
    
    # Validation logic
    if len(roll_number) < 8:
         return jsonify({'error': 'Invalid Roll Number format'}), 400
         
    branch = detect_branch(roll_number)
    today = get_today_str()

    # Check for duplicate in this event
    existing = attendance_col.find_one({'rollNumber': roll_number, 'eventId': event_id})
    if existing:
        return jsonify({'error': 'Duplicate attendance', 'already_marked': True}), 409

    # Check existence in students collection for this event
    student = students_col.find_one({'rollNumber': roll_number, 'eventId': event_id})
    
    if not student:
        # Not found -> prompt to add
        return jsonify({'status': 'NOT_FOUND', 'roll_number': roll_number}), 404
    
    # Mark attendance
    attendance_record = {
        'rollNumber': roll_number,
        'name': student.get('name', 'Unknown'),
        'branch': student.get('branch', branch),
        'date': today,
        'eventId': event_id,
        'timestamp': datetime.now()
    }
    attendance_col.insert_one(attendance_record)
    
    # Emit update
    emit_counts(event_id)
    
    return jsonify({'status': 'SUCCESS', 'name': student.get('name'), 'branch': student.get('branch')})

@app.route('/api/events', methods=['GET', 'POST'])
def events_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
        
    if request.method == 'GET':
        events = list(events_col.find().sort('created_at', -1))
        for e in events:
            e['_id'] = str(e['_id'])
        return jsonify(events)
        
    if request.method == 'POST':
        # Check for super admin
        if session.get('username') != 'ECEADMIN':
            return jsonify({'error': 'Only ECEADMIN can create events'}), 403
            
        data = request.json
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Event name required'}), 400
            
        event = {
            'name': name,
            'created_at': datetime.now()
        }
        res = events_col.insert_one(event)
        return jsonify({'status': 'SUCCESS', 'event_id': str(res.inserted_id)})

@app.route('/api/events/<event_id>', methods=['DELETE'])
@requires_super_admin
def delete_event_api(event_id):
    try:
        # Cascade delete
        # 1. Delete Students
        students_col.delete_many({'eventId': event_id})
        # 2. Delete Attendance
        attendance_col.delete_many({'eventId': event_id})
        # 3. Delete Event
        res = events_col.delete_one({'_id': ObjectId(event_id)})
        
        if res.deleted_count > 0:
            return jsonify({'status': 'SUCCESS', 'message': f'Event {event_id} and all associated data deleted.'})
        else:
            return jsonify({'error': 'Event not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload_students', methods=['POST'])
@requires_super_admin
def upload_students():
    # File handling logic...
        
    event_id = request.form.get('event_id')
    if not event_id:
        return jsonify({'error': 'No event selected'}), 400
        
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            df = pd.read_excel(file)
            # Normalize column names
            df.columns = [str(c).strip().title() for c in df.columns]
            
            required = ['Roll Number', 'Name']
            if not all(c in df.columns for c in required):
                return jsonify({'error': f'Excel must contain: {", ".join(required)}'}), 400
                
            student_records = []
            for _, row in df.iterrows():
                roll = str(row['Roll Number']).upper().strip()
                name = str(row['Name']).strip()
                branch = str(row.get('Branch', detect_branch(roll))).strip().upper()
                
                student_records.append({
                    'rollNumber': roll,
                    'name': name,
                    'branch': branch,
                    'eventId': event_id
                })
            
            if student_records:
                # Remove old records for this event if re-uploading? 
                # For now just insert/upsert.
                for s in student_records:
                    students_col.update_one(
                        {'rollNumber': s['rollNumber'], 'eventId': event_id},
                        {'$set': s},
                        upsert=True
                    )
                    
            return jsonify({'status': 'SUCCESS', 'count': len(student_records)})
        except Exception as e:
            return jsonify({'error': f'Parsing error: {str(e)}'}), 500
            
    return jsonify({'error': 'Invalid file format'}), 400

@app.route('/api/add_student', methods=['POST'])
def add_student_api():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    roll_number = data.get('roll_number')
    name = data.get('name')
    event_id = data.get('event_id')
    
    if not roll_number or not name or not event_id:
        return jsonify({'error': 'Roll number, Name and Event ID required'}), 400
        
    roll_number = roll_number.upper().strip()
    branch = detect_branch(roll_number)
    
    # Insert to students
    students_col.update_one(
        {'rollNumber': roll_number, 'eventId': event_id},
        {'$set': {'name': name, 'branch': branch}},
        upsert=True
    )
    
    # Automatically mark attendance
    today = get_today_str()
    attendance_record = {
        'rollNumber': roll_number,
        'name': name,
        'branch': branch,
        'date': today,
        'eventId': event_id,
        'timestamp': datetime.now()
    }
    attendance_col.insert_one(attendance_record)
    emit_counts(event_id)
    return jsonify({'status': 'SUCCESS', 'message': 'Student added and attendance marked'})

@app.route('/api/delete_student', methods=['POST'])
def delete_student_api():
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
    
        data = request.json
        roll_number = data.get('roll_number')
        event_id = data.get('event_id')
        
        if not roll_number or not event_id:
            return jsonify({'error': 'Roll number and Event ID required'}), 400
            
        roll_number = str(roll_number).upper().strip()
        
        # Delete from students
        res_s = students_col.delete_one({'rollNumber': roll_number, 'eventId': event_id})
        # Delete from attendance
        res_a = attendance_col.delete_many({'rollNumber': roll_number, 'eventId': event_id})
        
        if res_s.deleted_count > 0 or res_a.deleted_count > 0:
            emit_counts(event_id)
            return jsonify({'status': 'SUCCESS', 'message': f'Deleted {roll_number}'})
        else:
            return jsonify({'status': 'NOT_FOUND', 'message': f'Roll number {roll_number} not found in this event'}), 404
            
    except Exception as e:
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500

@app.route('/api/attendees')
def get_attendees():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    event_id = request.args.get('event_id')
    branch = request.args.get('branch')
    
    if not event_id:
        return jsonify({'error': 'Event ID required'}), 400
        
    query = {'eventId': event_id}
    if branch and branch != 'ALL':
        query['branch'] = branch.upper()
        
    records = list(attendance_col.find(query))
    result = []
    for idx, r in enumerate(records, 1):
        result.append({
            's_no': idx,
            'rollResult': r.get('rollNumber'),
            'name': r.get('name'),
            'branch': r.get('branch')
        })
    return jsonify(result)

@app.route('/api/stats')
def get_stats():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    event_id = request.args.get('event_id')
    if not event_id:
        return jsonify({'total': 0, 'branch_counts': {}, 'total_students': 0})
        
    total = attendance_col.count_documents({'eventId': event_id})
    pipeline = [
        {'$match': {'eventId': event_id}},
        {'$group': {'_id': '$branch', 'count': {'$sum': 1}}}
    ]
    branch_counts = {item['_id']: item['count'] for item in attendance_col.aggregate(pipeline)}
    for dept in BRANCH_MAP.values():
        if dept not in branch_counts:
            branch_counts[dept] = 0
            
    total_students = students_col.count_documents({'eventId': event_id})
    return jsonify({'total': total, 'branch_counts': branch_counts, 'total_students': total_students})

def emit_counts(event_id):
    total = attendance_col.count_documents({'eventId': event_id})
    pipeline = [
        {'$match': {'eventId': event_id}},
        {'$group': {'_id': '$branch', 'count': {'$sum': 1}}}
    ]
    branch_counts = {item['_id']: item['count'] for item in attendance_col.aggregate(pipeline)}
    for dept in BRANCH_MAP.values():
        if dept not in branch_counts:
            branch_counts[dept] = 0
            
    total_students = students_col.count_documents({'eventId': event_id})
    try:
        socketio.emit('update_counts', {
            'total': total, 
            'branch_counts': branch_counts,
            'total_students': total_students,
            'event_id': event_id
        })
    except Exception as e:
        print(f"ERROR: emit_counts failed: {e}")


@app.route('/download_pdf/<event_id>/<department>')
def download_pdf(event_id, department):
    if not session.get('logged_in'):
         return redirect(url_for('login'))
         
    department = department.upper()
    event = events_col.find_one({'_id': ObjectId(event_id)})
    if not event:
        return "Invalid Event", 400
        
    records = list(attendance_col.find({'eventId': event_id, 'branch': department}))
    
    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = styles['Title']
    title_style.leading = 24
    elements.append(Paragraph(f"ATTENDANCE FOR THE<br/>{event['name']}<br/>BY ECE SVEC", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Department: {department}", styles['Heading2']))
    elements.append(Paragraph(f"Date: {get_today_str()}", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Table Data
    data = [['S.No', 'Roll Number', 'Name']]
    for idx, record in enumerate(records, 1):
        data.append([str(idx), record.get('rollNumber', ''), record.get('name', '')])
        
    # Set column widths to make table BIG (Total ~500pts)
    table = Table(data, colWidths=[50, 150, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    
    today_str = get_today_str()
    return send_file(buffer, as_attachment=True, download_name=f"Attendance_{department}_{today_str}.pdf", mimetype='application/pdf')

@app.route('/download_full_excel/<event_id>')
def download_full_excel(event_id):
    if not session.get('logged_in'):
         return redirect(url_for('login'))
    
    event = events_col.find_one({'_id': ObjectId(event_id)})
    if not event:
        return "Invalid Event", 400
        
    attendance_records = list(attendance_col.find({'eventId': event_id}, {'_id': 0}))
    
    data = []
    for r in attendance_records:
        data.append({
            'Roll Number': r.get('rollNumber', 'UNKNOWN'),
            'Name': r.get('name', ''),
            'Branch': r.get('branch', ''),
            'Time': r.get('timestamp', '').strftime('%H:%M:%S') if isinstance(r.get('timestamp'), datetime) else str(r.get('time', ''))
        })
        
    df = pd.DataFrame(data)
    
    # Output to BytesIO
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Present Students')
        
    output.seek(0)
    
    today_str = get_today_str()
    return send_file(output, as_attachment=True, download_name=f"Full_Student_Data_{today_str}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    # Ensure indexes
    try:
        # Drop old single-field unique indexes if they exist
        try:
            students_col.drop_index("rollNumber_1")
            print("Dropped old rollNumber index from students")
        except:
            pass
            
        try:
            attendance_col.drop_index("rollNumber_1")
            print("Dropped old rollNumber index from attendance")
        except:
            pass

        attendance_col.create_index([('rollNumber', 1), ('eventId', 1)], unique=True)
        attendance_col.create_index('eventId')
        attendance_col.create_index('branch')
        students_col.create_index([('rollNumber', 1), ('eventId', 1)], unique=True)
        print("Indexes ensured.")
        
        # Bootstrap required accounts
        # ECEADMIN (Full access)
        admins_col.update_one(
            {'username': 'ECEADMIN'},
            {'$set': {'username': 'ECEADMIN', 'password': 'ADMIN@ECE'}},
            upsert=True
        )
        # GDGMEMBER (Attendance Only)
        admins_col.update_one(
            {'username': 'GDGMEMBER'},
            {'$set': {'username': 'GDGMEMBER', 'password': 'CORETEAM#3'}},
            upsert=True
        )
        print("Default Admins ensured.")
        
        # DEBUG: Print counts
        s_count = students_col.count_documents({})
        a_count = attendance_col.count_documents({})
        today_str = datetime.now().strftime('%Y-%m-%d')
        a_today = attendance_col.count_documents({'date': today_str})
        print(f"DEBUG: Total Students in DB: {s_count}")
        print(f"DEBUG: Total Attendance (All Time): {a_count}")
        print(f"DEBUG: Attendance Today ({today_str}): {a_today}")
        
    except Exception as e:
        print(f"Index creation failed: {e}")
        
    port = int(os.environ.get("PORT", 5000))
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        allow_unsafe_werkzeug=True
    )
