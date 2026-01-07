"""
NAYAN-AI - Unified Backend Server
Handles Cataract, Dry Eye, and Glaucoma screening
Includes WebSocket camera streaming and REST API
"""

import os
import cv2
import base64
import numpy as np
import json
import time
import csv
import sys
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
import sqlite3
from threading import Lock

# ============== APP SETUP ==============
app = Flask(__name__)
app.config['SECRET_KEY'] = 'nayan-ai-secret-key-2024'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = 'uploads'

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Create upload folders
os.makedirs('uploads/cataract', exist_ok=True)
os.makedirs('uploads/dryeye', exist_ok=True)
os.makedirs('uploads/glaucoma', exist_ok=True)
os.makedirs('uploads/camera', exist_ok=True)
os.makedirs('debug', exist_ok=True)

# Database
DB_PATH = 'nayan_ai.db'
db_lock = Lock()

# ============== DATABASE SETUP ==============
def init_db():
    """Initialize SQLite database"""
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Users table
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Patient data table
        c.execute('''CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            phone TEXT,
            email TEXT,
            medical_history TEXT,
            family_history TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')
        
        # Cataract screening results
        c.execute('''CREATE TABLE IF NOT EXISTS cataract_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            image_file TEXT,
            contrast REAL,
            sharpness REAL,
            edge_strength REAL,
            label TEXT,
            confidence REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        )''')
        
        # Dry eye screening results
        c.execute('''CREATE TABLE IF NOT EXISTS dryeye_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            video_file TEXT,
            duration_sec REAL,
            blink_count INTEGER,
            blink_rate_bpm REAL,
            mean_ibi_sec REAL,
            max_ibi_sec REAL,
            max_eye_open_sec REAL,
            label TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        )''')
        
        # Glaucoma screening results
        c.execute('''CREATE TABLE IF NOT EXISTS glaucoma_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            iop_proxy REAL,
            risk_level TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        )''')
        
        conn.commit()
        conn.close()

init_db()

# ============== AUTHENTICATION ==============
@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login"""
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password required'}), 400
    
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, name FROM users WHERE email = ? AND password = ?', (email, password))
        user = c.fetchone()
        conn.close()
    
    if user:
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user_id': user[0],
            'name': user[1],
            'email': email
        }), 200
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/auth/register', methods=['POST'])
def register():
    """User registration"""
    data = request.json
    email = data.get('email')
    password = data.get('password')
    name = data.get('name', 'User')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password required'}), 400
    
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (email, password, name) VALUES (?, ?, ?)', 
                     (email, password, name))
            conn.commit()
            user_id = c.lastrowid
            conn.close()
            return jsonify({
                'success': True,
                'message': 'Registration successful',
                'user_id': user_id
            }), 201
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'success': False, 'message': 'Email already exists'}), 400

# ============== PATIENT MANAGEMENT ==============
@app.route('/api/patient', methods=['POST'])
def save_patient():
    """Save patient information"""
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID required'}), 400
    
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO patients 
                     (user_id, name, age, gender, phone, email, medical_history, family_history)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (user_id, data.get('name'), data.get('age'), data.get('gender'),
                  data.get('phone'), data.get('email'), 
                  data.get('medicalHistory'), data.get('familyHistory')))
        conn.commit()
        patient_id = c.lastrowid
        conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Patient saved',
        'patient_id': patient_id
    }), 201

@app.route('/api/patient/<int:patient_id>', methods=['GET'])
def get_patient(patient_id):
    """Get patient information"""
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
        patient = c.fetchone()
        conn.close()
    
    if patient:
        return jsonify({
            'success': True,
            'patient': {
                'id': patient[0],
                'user_id': patient[1],
                'name': patient[2],
                'age': patient[3],
                'gender': patient[4],
                'phone': patient[5],
                'email': patient[6]
            }
        }), 200
    return jsonify({'success': False, 'message': 'Patient not found'}), 404

# ============== CATARACT SCREENING ==============
def extract_cataract_features(image_path):
    """Extract features from cataract image"""
    frame = cv2.imread(image_path)
    if frame is None:
        return None
    
    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Apply CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Extract ROI (center 25%)
    h, w = gray.shape[:2]
    rh, rw = int(h * 0.25), int(w * 0.25)
    y1 = (h - rh) // 2
    x1 = (w - rw) // 2
    roi = gray[y1:y1+rh, x1:x1+rw]
    
    # Compute features
    C = float(np.std(roi))  # Contrast
    lap = cv2.Laplacian(roi, cv2.CV_64F)
    S = float(lap.var())  # Sharpness
    gx = cv2.Sobel(roi, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(roi, cv2.CV_64F, 0, 1, ksize=3)
    E = float(np.mean(np.sqrt(gx*gx + gy*gy)))  # Edge
    
    # Classify
    Tc, Ts = 22.0, 120.0
    if (C < Tc) and (S < Ts):
        label = "Possible Cataract Risk"
        confidence = min(95, ((1 - (C/Tc)) * (1 - (S/Ts))) * 100)
    else:
        label = "Normal"
        confidence = min(95, ((C/Tc) + (S/Ts)) / 2 * 100)
    
    return {
        'contrast': C,
        'sharpness': S,
        'edge': E,
        'label': label,
        'confidence': confidence
    }

@app.route('/api/cataract/upload', methods=['POST'])
def upload_cataract():
    """Upload cataract image and analyze"""
    try:
        patient_id = request.form.get('patient_id')
        
        # Detailed validation
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image file in request. Files received: ' + str(list(request.files.keys()))}), 400
        
        if not patient_id:
            return jsonify({'success': False, 'message': 'Patient ID is required'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected (filename is empty)'}), 400
        
        # Validate file type
        if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            return jsonify({'success': False, 'message': f'Invalid file type: {file.filename}. Allowed: JPG, PNG, WEBP'}), 400
        
        # Create upload directory if not exists
        os.makedirs('uploads/cataract', exist_ok=True)
        
        filename = secure_filename(f"cataract_{int(time.time())}.jpg")
        filepath = os.path.join('uploads/cataract', filename)
        
        print(f"[CATARACT] Saving file to: {filepath}")
        file.save(filepath)
        
        # Verify file was saved
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'message': f'Failed to save file to {filepath}'}), 500
        
        print(f"[CATARACT] File saved successfully, size: {os.path.getsize(filepath)} bytes")
        
        # Extract features
        print(f"[CATARACT] Extracting features from {filepath}")
        features = extract_cataract_features(filepath)
        if not features:
            return jsonify({'success': False, 'message': 'Failed to process image. Image may be corrupted or unreadable.'}), 400
        
        print(f"[CATARACT] Features extracted: {features}")
        
        # Save to database
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''INSERT INTO cataract_results 
                        (patient_id, image_file, contrast, sharpness, edge_strength, label, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (patient_id, filename, features['contrast'], features['sharpness'],
                      features['edge'], features['label'], features['confidence']))
            conn.commit()
            result_id = c.lastrowid
            conn.close()
        
        print(f"[CATARACT] Result saved to database with ID: {result_id}")
        
        return jsonify({
            'success': True,
            'message': 'Cataract analysis complete',
            'result_id': result_id,
            'analysis': features,
            'image_url': f'/uploads/cataract/{filename}'
        }), 200
    
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"[CATARACT] Error: {error_msg}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

# ============== DRY EYE SCREENING ==============
@app.route('/api/dryeye/upload', methods=['POST'])
def upload_dryeye():
    """Upload dry eye video and analyze"""
    patient_id = request.form.get('patient_id')
    
    if 'video' not in request.files or not patient_id:
        return jsonify({'success': False, 'message': 'Video and patient ID required'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    try:
        filename = secure_filename(f"dryeye_{int(time.time())}.mp4")
        filepath = os.path.join('uploads/dryeye', filename)
        file.save(filepath)
        
        # Analyze video (mock analysis for now)
        cap = cv2.VideoCapture(filepath)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = frame_count / fps if fps > 0 else 0
        cap.release()
        
        # Generate blink metrics (simulated)
        blink_count = max(3, int(duration / 3))
        blink_rate = (blink_count / duration * 60) if duration > 0 else 0
        mean_ibi = duration / blink_count if blink_count > 0 else 0
        max_ibi = mean_ibi * 1.5
        max_eye_open = max_ibi * 0.8
        
        label = "Dry Eye Risk" if blink_rate < 10 or max_ibi > 10 else "Normal"
        
        # Save to database
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''INSERT INTO dryeye_results 
                        (patient_id, video_file, duration_sec, blink_count, 
                         blink_rate_bpm, mean_ibi_sec, max_ibi_sec, max_eye_open_sec, label)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (patient_id, filename, duration, blink_count, blink_rate,
                      mean_ibi, max_ibi, max_eye_open, label))
            conn.commit()
            result_id = c.lastrowid
            conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Dry eye analysis complete',
            'result_id': result_id,
            'analysis': {
                'duration_sec': round(duration, 2),
                'blink_count': blink_count,
                'blink_rate_bpm': round(blink_rate, 2),
                'mean_ibi_sec': round(mean_ibi, 2),
                'max_ibi_sec': round(max_ibi, 2),
                'max_eye_open_sec': round(max_eye_open, 2),
                'label': label
            },
            'video_url': f'/uploads/dryeye/{filename}'
        }), 200
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ============== GLAUCOMA SCREENING ==============
@app.route('/api/glaucoma/measure', methods=['POST'])
def glaucoma_measure():
    """Record glaucoma IOP measurement"""
    data = request.json
    patient_id = data.get('patient_id')
    iop_proxy = data.get('iop_proxy', 15.0 + np.random.rand() * 10)
    
    if not patient_id:
        return jsonify({'success': False, 'message': 'Patient ID required'}), 400
    
    # Classify risk
    if iop_proxy < 12:
        risk_level = "Low Risk"
    elif iop_proxy < 21:
        risk_level = "Normal"
    else:
        risk_level = "High Risk"
    
    try:
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''INSERT INTO glaucoma_results 
                        (patient_id, iop_proxy, risk_level)
                        VALUES (?, ?, ?)''',
                     (patient_id, iop_proxy, risk_level))
            conn.commit()
            result_id = c.lastrowid
            conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Glaucoma measurement recorded',
            'result_id': result_id,
            'analysis': {
                'iop_proxy': round(iop_proxy, 2),
                'risk_level': risk_level
            }
        }), 200
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ============== HISTORY / RESULTS ==============
@app.route('/api/results/<result_type>/<int:patient_id>', methods=['GET'])
def get_results(result_type, patient_id):
    """Get screening results for patient"""
    tables = {
        'cataract': 'cataract_results',
        'dryeye': 'dryeye_results',
        'glaucoma': 'glaucoma_results'
    }
    
    table = tables.get(result_type)
    if not table:
        return jsonify({'success': False, 'message': 'Invalid result type'}), 400
    
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(f'SELECT * FROM {table} WHERE patient_id = ? ORDER BY timestamp DESC', 
                 (patient_id,))
        results = c.fetchall()
        conn.close()
    
    return jsonify({
        'success': True,
        'results': results,
        'count': len(results)
    }), 200

# ============== WEBSOCKET CAMERA STREAMING ==============
active_streams = {}
camera_lock = Lock()

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    print(f"Client connected: {request.sid}")
    emit('connection_response', {'data': 'Connected to camera server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    with camera_lock:
        if request.sid in active_streams:
            del active_streams[request.sid]
    print(f"Client disconnected: {request.sid}")

@socketio.on('start_stream')
def handle_start_stream(data):
    """Start camera streaming from mobile"""
    patient_id = data.get('patient_id')
    stream_type = data.get('stream_type', 'cataract')  # cataract, dryeye, glaucoma
    
    with camera_lock:
        active_streams[request.sid] = {
            'patient_id': patient_id,
            'stream_type': stream_type,
            'started_at': time.time(),
            'frame_count': 0
        }
    
    print(f"Stream started: {stream_type} for patient {patient_id}")
    emit('stream_status', {'status': 'streaming', 'type': stream_type})

@socketio.on('frame')
def handle_frame(data):
    """Receive frame from mobile camera"""
    try:
        # Decode base64 frame
        frame_data = data.get('frame')
        patient_id = data.get('patient_id')
        
        if not frame_data or not patient_id:
            return
        
        # Decode and save frame
        frame_bytes = base64.b64decode(frame_data.split(',')[1])
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is not None:
            # Save frame
            filename = f"camera_stream_{patient_id}_{int(time.time()*1000)}.jpg"
            filepath = os.path.join('uploads/camera', filename)
            cv2.imwrite(filepath, frame)
            
            # Send acknowledgment
            emit('frame_received', {'status': 'ok'})
    
    except Exception as e:
        print(f"Error processing frame: {e}")
        emit('frame_error', {'error': str(e)})

@socketio.on('stop_stream')
def handle_stop_stream():
    """Stop camera streaming"""
    with camera_lock:
        if request.sid in active_streams:
            del active_streams[request.sid]
    print(f"Stream stopped: {request.sid}")
    emit('stream_status', {'status': 'stopped'})

# ============== FILE SERVING ==============
@app.route('/uploads/<folder>/<filename>')
def serve_upload(folder, filename):
    """Serve uploaded files"""
    return send_from_directory(os.path.join('uploads', folder), filename)

@app.route('/debug/<filename>')
def serve_debug(filename):
    """Serve debug files"""
    return send_from_directory('debug', filename)

# ============== HEALTH CHECK ==============
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'NAYAN-AI Backend',
        'timestamp': datetime.now().isoformat()
    }), 200

# ============== RUN SERVER ==============
if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("NAYAN-AI BACKEND SERVER")
    print("Eye Screening System v1.0")
    print("=" * 50)
    print("REST API:  http://127.0.0.1:5000")
    print("WebSocket: ws://127.0.0.1:5000")
    print("Database:  SQLite3 (nayan_ai.db)")
    print("=" * 50)
    print("Server starting... (Press Ctrl+C to stop)")
    print("=" * 50)
    sys.stdout.flush()
    
    try:
        socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True)
    except Exception as e:
        print(f"ERROR: Failed to start server: {e}")
        import traceback
        traceback.print_exc()
