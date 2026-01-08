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
from flask import Flask, request, jsonify, send_from_directory, render_template_string, redirect, send_file, abort
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from threading import Lock

# ============== APP SETUP ==============
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
FRONTEND_DIR = PROJECT_DIR / 'frontend'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nayan-ai-secret-key-2024'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = str(PROJECT_DIR / 'uploads')

CORS(app)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=os.environ.get('SOCKETIO_ASYNC_MODE', 'threading')
)


# ============== CATARACT (DL MODEL) ==============
# Lazily loaded so the server can still start even if TensorFlow isn't installed.
_CATARACT_MODEL = None
_CATARACT_CLASS_NAMES = None
_cataract_model_lock = Lock()


def _load_cataract_dl_model():
    """Load cataract DL model + labels once (thread-safe)."""
    global _CATARACT_MODEL, _CATARACT_CLASS_NAMES

    if _CATARACT_MODEL is not None and _CATARACT_CLASS_NAMES is not None:
        return

    with _cataract_model_lock:
        if _CATARACT_MODEL is not None and _CATARACT_CLASS_NAMES is not None:
            return

        # If you faced Windows Keras 3 overflow issues, keep this ON.
        # Must be set before importing TensorFlow in some environments.
        os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

        try:
            import tensorflow as tf  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "TensorFlow is not installed (required for DL cataract). "
                "Install backend requirements and try again. "
                f"Original error: {e}"
            )

        artifacts_dir = BASE_DIR / 'catract' / 'artifacts'
        labels_path = artifacts_dir / 'labels.json'

        if not labels_path.exists():
            raise FileNotFoundError(f"labels.json not found at: {labels_path}")

        # Try loading .h5 first (more stable), then .keras
        model_path_h5 = artifacts_dir / 'cataract_mobilenetv2.h5'
        model_path_keras = artifacts_dir / 'cataract_mobilenetv2.keras'
        
        model_loaded = False
        last_error = None
        
        # Try .h5 format first
        if model_path_h5.exists():
            try:
                print(f"Loading model from {model_path_h5}")
                _CATARACT_MODEL = tf.keras.models.load_model(str(model_path_h5), compile=False)
                model_loaded = True
                print("Successfully loaded .h5 model")
            except Exception as e:
                print(f"Failed to load .h5 model: {e}")
                last_error = e
        
        # Try .keras format if .h5 failed or doesn't exist
        if not model_loaded and model_path_keras.exists():
            try:
                print(f"Loading model from {model_path_keras}")
                _CATARACT_MODEL = tf.keras.models.load_model(str(model_path_keras), compile=False)
                model_loaded = True
                print("Successfully loaded .keras model")
            except Exception as e:
                print(f"Failed to load .keras model: {e}")
                last_error = e
        
        if not model_loaded:
            error_msg = f"Could not load model. Tried: {model_path_h5}, {model_path_keras}"
            if last_error:
                error_msg += f". Last error: {last_error}"
            raise FileNotFoundError(error_msg)

        _CATARACT_CLASS_NAMES = json.loads(labels_path.read_text(encoding='utf-8')).get('class_names')
        if not _CATARACT_CLASS_NAMES:
            raise ValueError("labels.json missing 'class_names'")


def _preprocess_for_cataract_mobilenet(frame_bgr: np.ndarray) -> np.ndarray:
    """Match preprocessing from backend/catract/mobile_cataract_server_dl.py.

    IMPORTANT: model already applies preprocess_input internally.
    Feed raw RGB in [0, 255] as float32.
    """
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_AREA)
    x = rgb.astype(np.float32)
    return np.expand_dims(x, axis=0)


def predict_cataract_dl(image_path: str):
    """Return (pred_label, conf_percent, probs_map)."""
    _load_cataract_dl_model()

    frame = cv2.imread(image_path)
    if frame is None:
        raise ValueError("Failed to read image")

    x = _preprocess_for_cataract_mobilenet(frame)
    probs = _CATARACT_MODEL.predict(x, verbose=0)[0]

    idx = int(np.argmax(probs))
    pred_label = str(_CATARACT_CLASS_NAMES[idx])
    conf_percent = float(probs[idx]) * 100.0

    probs_map = {str(_CATARACT_CLASS_NAMES[i]): float(probs[i]) for i in range(len(_CATARACT_CLASS_NAMES))}
    return pred_label, conf_percent, probs_map


# ============== FRONTEND SERVING (OPTIONAL) ==============
def _frontend_file(filename: str):
    if not FRONTEND_DIR.exists():
        return jsonify({
            'success': False,
            'message': 'Frontend directory not found',
            'expected_path': str(FRONTEND_DIR)
        }), 404
    return send_from_directory(str(FRONTEND_DIR), filename)


@app.route('/', methods=['GET'])
def serve_root():
    return _frontend_file('login.html')


@app.route('/login', methods=['GET'])
@app.route('/login.html', methods=['GET'])
def serve_login():
    return _frontend_file('login.html')


@app.route('/signin', methods=['GET'])
@app.route('/signin.html', methods=['GET'])
def serve_signin():
    return _frontend_file('signin.html')


@app.route('/index', methods=['GET'])
@app.route('/index.html', methods=['GET'])
def serve_index():
    return _frontend_file('index.html')


@app.route('/patient', methods=['GET'])
@app.route('/patient_input', methods=['GET'])
@app.route('/patient_input.html', methods=['GET'])
def serve_patient_input():
    return _frontend_file('patient_input.html')


@app.route('/cataract', methods=['GET'])
@app.route('/cataract.html', methods=['GET'])
def serve_cataract_page():
    return _frontend_file('cataract.html')


@app.route('/dryeye', methods=['GET'])
@app.route('/dryeye.html', methods=['GET'])
def serve_dryeye_page():
    return _frontend_file('dryeye.html')


@app.route('/glaucoma', methods=['GET'])
@app.route('/glaucoma.html', methods=['GET'])
def serve_glaucoma_page():
    return _frontend_file('glaucoma.html')


@app.route('/history', methods=['GET'])
@app.route('/history.html', methods=['GET'])
def serve_history_page():
    return _frontend_file('history.html')


@app.route('/camp', methods=['GET'])
@app.route('/camp_workflow', methods=['GET'])
@app.route('/camp_workflow.html', methods=['GET'])
def serve_camp_workflow():
    return _frontend_file('camp_workflow.html')


@app.route('/report', methods=['GET'])
@app.route('/report.html', methods=['GET'])
def serve_report_page():
    return _frontend_file('report.html')


@app.route('/assets/<path:filename>', methods=['GET'])
def serve_assets(filename):
    assets_dir = FRONTEND_DIR / 'assets'
    return send_from_directory(str(assets_dir), filename)


@app.route('/favicon.ico', methods=['GET'])
def serve_favicon():
    """Avoid noisy 404s from browsers requesting /favicon.ico."""
    icon = FRONTEND_DIR / 'assets' / 'favicon.ico'
    if icon.exists():
        return send_from_directory(str(icon.parent), icon.name)
    return ('', 204)

# Create upload folders
os.makedirs(PROJECT_DIR / 'uploads' / 'cataract', exist_ok=True)
os.makedirs(PROJECT_DIR / 'uploads' / 'dryeye', exist_ok=True)
os.makedirs(PROJECT_DIR / 'uploads' / 'glaucoma', exist_ok=True)
os.makedirs(PROJECT_DIR / 'uploads' / 'camera', exist_ok=True)
os.makedirs(PROJECT_DIR / 'debug', exist_ok=True)

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
        c.execute('SELECT id, name, password FROM users WHERE email = ?', (email,))
        user = c.fetchone()

        if not user:
            conn.close()
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        user_id, name, stored_password = user

        # Backward-compatible password check:
        # - Current Werkzeug may store hashes as `scrypt:` (default) or `pbkdf2:`
        # - Legacy users may have plaintext passwords in the DB
        ok = False
        if stored_password:
            try:
                ok = check_password_hash(stored_password, password)
            except Exception:
                ok = (stored_password == password)

        # Opportunistic upgrade of legacy plaintext passwords.
        if ok and stored_password == password:
            try:
                c.execute('UPDATE users SET password = ? WHERE id = ?', (generate_password_hash(password), user_id))
                conn.commit()
            except Exception:
                pass

        conn.close()

    if ok:
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user_id': user_id,
            'name': name,
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
                     (email, generate_password_hash(password), name))
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
    
    # Handle both camelCase (from JS) and snake_case
    medical_history = data.get('medical_history') or data.get('medicalHistory') or 'None reported'
    family_history = data.get('family_history') or data.get('familyHistory') or 'None reported'
    
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO patients 
                     (user_id, name, age, gender, phone, email, medical_history, family_history)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (user_id, data.get('name'), data.get('age'), data.get('gender'),
                  data.get('phone', ''), data.get('email', ''), 
                  medical_history, family_history))
        conn.commit()
        patient_id = c.lastrowid
        conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Patient information saved successfully',
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
                'email': patient[6],
                'medical_history': patient[7],
                'family_history': patient[8]
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
        
        # Create upload directory if not exists (absolute path)
        cataract_dir = PROJECT_DIR / 'uploads' / 'cataract'
        os.makedirs(cataract_dir, exist_ok=True)

        filename = secure_filename(f"cataract_{int(time.time())}.jpg")
        filepath = str(cataract_dir / filename)
        
        print(f"[CATARACT] Saving file to: {filepath}")
        file.save(filepath)
        
        # Verify file was saved
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'message': f'Failed to save file to {filepath}'}), 500
        
        print(f"[CATARACT] File saved successfully, size: {os.path.getsize(filepath)} bytes")
        
        # Compute basic image metrics for the UI (contrast/sharpness) but use DL for classification.
        print(f"[CATARACT] Computing image metrics from {filepath}")
        features = extract_cataract_features(filepath)
        if not features:
            return jsonify({'success': False, 'message': 'Failed to process image. Image may be corrupted or unreadable.'}), 400

        print(f"[CATARACT] Metrics computed: {features}")

        # DL prediction (primary method)
        try:
            print(f"[CATARACT] Running DL model on {filepath}")
            pred_label, conf_percent, probs_map = predict_cataract_dl(filepath)

            # Map model class name to UI label
            is_risk = pred_label.strip().lower() == 'cataract'
            features['label'] = 'Possible Cataract Risk' if is_risk else 'Normal'
            features['confidence'] = conf_percent
            features['dl_pred_label'] = pred_label
            features['dl_probs'] = probs_map
            print(f"[CATARACT] DL prediction: {pred_label} ({conf_percent:.2f}%)")
            
        except Exception as dl_error:
            # DL model failed - this should be rare
            print(f"[CATARACT] ERROR: DL model failed: {dl_error}")
            print(f"[CATARACT] This indicates a model loading issue. Please check model files.")
            
            # Return error to user instead of silently falling back
            return jsonify({
                'success': False, 
                'message': f'Deep Learning model unavailable. Please contact administrator. Error: {str(dl_error)}'
            }), 503
        
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
    # Handle multiple naming conventions from frontend
    iop_proxy = data.get('iop_proxy') or data.get('iop') or data.get('iopValue')
    
    if not iop_proxy:
        iop_proxy = 15.0 + np.random.rand() * 10  # Fallback random value
    else:
        iop_proxy = float(iop_proxy)
    
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
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f'SELECT * FROM {table} WHERE patient_id = ? ORDER BY timestamp DESC', 
                 (patient_id,))
        rows = c.fetchall()
        conn.close()
    
    # Convert rows to dictionaries
    results = []
    for row in rows:
        result_dict = dict(row)
        results.append(result_dict)
    
    return jsonify({
        'success': True,
        'results': results,
        'count': len(results)
    }), 200

# ============== PDF REPORT GENERATION ==============
@app.route('/api/report/pdf/<int:patient_id>', methods=['GET'])
def generate_pdf_report(patient_id):
    """Generate comprehensive PDF report for patient including all screening results"""
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from io import BytesIO
        
        # Get patient info
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Fetch patient data
            c.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
            patient = c.fetchone()
            
            if not patient:
                conn.close()
                return jsonify({'success': False, 'message': 'Patient not found'}), 404
            
            # Fetch all results
            c.execute('SELECT * FROM cataract_results WHERE patient_id = ? ORDER BY timestamp DESC', (patient_id,))
            cataract_results = c.fetchall()
            
            c.execute('SELECT * FROM dryeye_results WHERE patient_id = ? ORDER BY timestamp DESC', (patient_id,))
            dryeye_results = c.fetchall()
            
            c.execute('SELECT * FROM glaucoma_results WHERE patient_id = ? ORDER BY timestamp DESC', (patient_id,))
            glaucoma_results = c.fetchall()
            
            conn.close()
        
        # Create PDF in memory
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#0066cc'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#0066cc'),
            spaceAfter=10,
            spaceBefore=12
        )
        
        # Title
        story.append(Paragraph("NAYAN-AI", title_style))
        story.append(Paragraph("Comprehensive Eye Screening Report", styles['Heading2']))
        story.append(Paragraph("AI-Assisted Eye Screening System", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Patient Information
        story.append(Paragraph("Patient Information", heading_style))
        patient_data = [
            ['Name:', patient['name'] or '--', 'Age:', f"{patient['age']} years" if patient['age'] else '--'],
            ['Gender:', patient['gender'] or '--', 'Phone:', patient['phone'] or '--'],
            ['Number:', patient['number'] or '--', 'Email:', patient['email'] or '--'],
        ]
        patient_table = Table(patient_data, colWidths=[1*inch, 2.5*inch, 1*inch, 2.5*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(patient_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Report Details
        report_data = [
            ['Report Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            ['Patient ID:', str(patient['id'])],
        ]
        report_table = Table(report_data, colWidths=[2*inch, 5*inch])
        report_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(report_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Test Results - Cataract
        story.append(Paragraph("Cataract Screening Results", heading_style))
        if cataract_results:
            cataract_data = [['Date', 'Contrast', 'Sharpness', 'Edge', 'Result', 'Confidence']]
            for r in cataract_results:
                cataract_data.append([
                    r['timestamp'][:19] if r['timestamp'] else '--',
                    f"{r['contrast']:.2f}" if r['contrast'] else '--',
                    f"{r['sharpness']:.2f}" if r['sharpness'] else '--',
                    f"{r['edge_strength']:.2f}" if r['edge_strength'] else '--',
                    r['label'] or '--',
                    f"{r['confidence']:.1f}%" if r['confidence'] else '--'
                ])
            cataract_table = Table(cataract_data, colWidths=[1.5*inch, 0.9*inch, 0.9*inch, 0.9*inch, 1.8*inch, 1*inch])
            cataract_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0066cc')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(cataract_table)
        else:
            story.append(Paragraph("No cataract screening records found.", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Test Results - Dry Eye
        story.append(Paragraph("Dry Eye Screening Results", heading_style))
        if dryeye_results:
            dryeye_data = [['Date', 'Duration (s)', 'Blink Count', 'Blink Rate (BPM)', 'Mean IBI (s)', 'Max Eye Open (s)', 'Result']]
            for r in dryeye_results:
                dryeye_data.append([
                    r['timestamp'][:19] if r['timestamp'] else '--',
                    f"{r['duration_sec']:.1f}" if r['duration_sec'] else '--',
                    str(r['blink_count']) if r['blink_count'] else '--',
                    f"{r['blink_rate_bpm']:.1f}" if r['blink_rate_bpm'] else '--',
                    f"{r['mean_ibi_sec']:.2f}" if r['mean_ibi_sec'] else '--',
                    f"{r['max_eye_open_sec']:.2f}" if r['max_eye_open_sec'] else '--',
                    r['label'] or '--'
                ])
            dryeye_table = Table(dryeye_data, colWidths=[1.3*inch, 0.8*inch, 0.9*inch, 1*inch, 0.9*inch, 1.1*inch, 1*inch])
            dryeye_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#17a2b8')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            story.append(dryeye_table)
        else:
            story.append(Paragraph("No dry eye screening records found.", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Test Results - Glaucoma
        story.append(Paragraph("Glaucoma Screening Results", heading_style))
        if glaucoma_results:
            glaucoma_data = [['Date', 'IOP Proxy (mmHg)', 'Risk Level']]
            for r in glaucoma_results:
                glaucoma_data.append([
                    r['timestamp'][:19] if r['timestamp'] else '--',
                    f"{r['iop_proxy']:.1f}" if r['iop_proxy'] else '--',
                    r['risk_level'] or '--'
                ])
            glaucoma_table = Table(glaucoma_data, colWidths=[2.5*inch, 2*inch, 2.5*inch])
            glaucoma_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28a745')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(glaucoma_table)
        else:
            story.append(Paragraph("No glaucoma screening records found.", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Interpretation Section
        story.append(Paragraph("Interpretation", heading_style))
        
        # Determine overall risk
        has_risk = False
        risk_items = []
        
        if cataract_results:
            latest_cataract = cataract_results[0]
            if 'Risk' in (latest_cataract['label'] or ''):
                has_risk = True
                risk_items.append(f"• Cataract: {latest_cataract['label']} (Confidence: {latest_cataract['confidence']:.1f}%)")
        
        if dryeye_results:
            latest_dryeye = dryeye_results[0]
            if 'Risk' in (latest_dryeye['label'] or ''):
                has_risk = True
                risk_items.append(f"• Dry Eye: {latest_dryeye['label']}")
        
        if glaucoma_results:
            latest_glaucoma = glaucoma_results[0]
            if latest_glaucoma['risk_level'] and latest_glaucoma['risk_level'].lower() not in ['normal', 'low']:
                has_risk = True
                risk_items.append(f"• Glaucoma: {latest_glaucoma['risk_level']} Risk (IOP: {latest_glaucoma['iop_proxy']:.1f} mmHg)")
        
        if has_risk:
            story.append(Paragraph("<b>Abnormal findings detected:</b>", styles['Normal']))
            for item in risk_items:
                story.append(Paragraph(item, styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
            story.append(Paragraph("<b>Recommendation:</b> Immediate consultation with an ophthalmologist is recommended for comprehensive evaluation and proper diagnosis.", styles['Normal']))
        else:
            story.append(Paragraph("All screening results appear normal. Continue regular eye check-ups as recommended by your healthcare provider.", styles['Normal']))
        
        story.append(Spacer(1, 0.3*inch))
        
        # Disclaimer
        disclaimer_style = ParagraphStyle(
            'Disclaimer',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            spaceBefore=10,
            spaceAfter=10
        )
        story.append(Paragraph("<b>Important Disclaimer:</b>", heading_style))
        story.append(Paragraph(
            "This is an AI-assisted screening tool for preliminary assessment only. This report is NOT a substitute "
            "for professional medical diagnosis. Please consult a qualified ophthalmologist for complete eye examination "
            "and proper diagnosis. The screening tool is designed to detect potential risk indicators but cannot provide "
            "definitive diagnoses.",
            disclaimer_style
        ))
        
        # Footer
        story.append(Spacer(1, 0.2*inch))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#999999'),
            alignment=TA_CENTER
        )
        story.append(Paragraph("This report is automatically generated by NAYAN-AI Eye Screening System", footer_style))
        story.append(Paragraph(f"Report generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", footer_style))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        # Send file
        filename = f"NAYAN-AI_Report_{patient['name']}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"[PDF REPORT] Error: {error_msg}")
        return jsonify({'success': False, 'message': f'Error generating PDF: {str(e)}'}), 500

# ============== INDIVIDUAL SCREENING PDF REPORTS ==============
@app.route('/api/report/cataract/pdf/<int:patient_id>', methods=['GET'])
def generate_cataract_pdf(patient_id):
    """Generate PDF report for cataract screening"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from io import BytesIO
        
        # Get patient info and results
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            c.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
            patient = c.fetchone()
            
            if not patient:
                conn.close()
                return jsonify({'success': False, 'message': 'Patient not found'}), 404
            
            c.execute('SELECT * FROM cataract_results WHERE patient_id = ? ORDER BY timestamp DESC LIMIT 1', (patient_id,))
            result = c.fetchone()
            
            conn.close()
        
        if not result:
            return jsonify({'success': False, 'message': 'No cataract screening results found'}), 404
        
        # Create PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#0066cc'), spaceAfter=12, alignment=TA_CENTER)
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#0066cc'), spaceAfter=10, spaceBefore=12)
        
        # Header
        story.append(Paragraph("NAYAN-AI", title_style))
        story.append(Paragraph("Cataract Detection Report", styles['Heading2']))
        story.append(Paragraph("AI-Assisted Eye Screening System", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Patient Information
        story.append(Paragraph("Patient Information", heading_style))
        patient_data = [
            ['Name:', patient['name'] or '--', 'Age:', f"{patient['age']} years" if patient['age'] else '--'],
            ['Gender:', patient['gender'] or '--', 'Date:', result['timestamp'][:10] if result['timestamp'] else '--'],
        ]
        patient_table = Table(patient_data, colWidths=[1*inch, 2.5*inch, 1*inch, 2.5*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(patient_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Test Results
        story.append(Paragraph("Test Results", heading_style))
        risk_color = colors.HexColor('#fff3cd') if 'Risk' in (result['label'] or '') else colors.HexColor('#d4edda')
        result_box = [['Risk Assessment:', result['label'] or '--']]
        result_table = Table(result_box, colWidths=[2*inch, 5*inch])
        result_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), risk_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#0066cc')),
        ]))
        story.append(result_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Detailed Metrics
        story.append(Paragraph("Detailed Metrics", heading_style))
        metrics_data = [
            ['Metric', 'Value'],
            ['Contrast', f"{result['contrast']:.2f}" if result['contrast'] else '--'],
            ['Sharpness', f"{result['sharpness']:.2f}" if result['sharpness'] else '--'],
            ['Edge Strength', f"{result['edge_strength']:.2f}" if result['edge_strength'] else '--'],
            ['Confidence', f"{result['confidence']:.1f}%" if result['confidence'] else '--'],
        ]
        metrics_table = Table(metrics_data, colWidths=[3.5*inch, 3.5*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f9f9f9')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ]))
        story.append(metrics_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Interpretation
        story.append(Paragraph("Interpretation", heading_style))
        interp_text = "Cataract risk assessment based on image analysis using AI deep learning model (MobileNetV2). This is a screening support tool only and should not be used as a medical diagnosis. Please consult an ophthalmologist for professional evaluation."
        story.append(Paragraph(interp_text, styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Footer
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#999999'), alignment=TA_CENTER)
        story.append(Paragraph("<strong>NAYAN-AI</strong> - AI-Assisted Eye Screening System", footer_style))
        story.append(Paragraph("Developed by: Krishnapriya S, Madhumitha S, Mahalakshmi B S", footer_style))
        story.append(Paragraph("Electronics and Communication Engineering Department", footer_style))
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", footer_style))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        filename = f"Cataract_Report_{patient['name']}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)
    
    except Exception as e:
        import traceback
        print(f"[CATARACT PDF] Error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Error generating PDF: {str(e)}'}), 500

@app.route('/api/report/dryeye/pdf/<int:patient_id>', methods=['GET'])
def generate_dryeye_pdf(patient_id):
    """Generate PDF report for dry eye screening"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from io import BytesIO
        
        # Get patient info and results
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            c.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
            patient = c.fetchone()
            
            if not patient:
                conn.close()
                return jsonify({'success': False, 'message': 'Patient not found'}), 404
            
            c.execute('SELECT * FROM dryeye_results WHERE patient_id = ? ORDER BY timestamp DESC LIMIT 1', (patient_id,))
            result = c.fetchone()
            
            conn.close()
        
        if not result:
            return jsonify({'success': False, 'message': 'No dry eye screening results found'}), 404
        
        # Create PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#0066cc'), spaceAfter=12, alignment=TA_CENTER)
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#0066cc'), spaceAfter=10, spaceBefore=12)
        
        # Header
        story.append(Paragraph("NAYAN-AI", title_style))
        story.append(Paragraph("Dry Eye Detection Report", styles['Heading2']))
        story.append(Paragraph("AI-Assisted Eye Screening System", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Patient Information
        story.append(Paragraph("Patient Information", heading_style))
        patient_data = [
            ['Name:', patient['name'] or '--', 'Age:', f"{patient['age']} years" if patient['age'] else '--'],
            ['Gender:', patient['gender'] or '--', 'Date:', result['timestamp'][:10] if result['timestamp'] else '--'],
        ]
        patient_table = Table(patient_data, colWidths=[1*inch, 2.5*inch, 1*inch, 2.5*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(patient_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Test Results
        story.append(Paragraph("Test Results", heading_style))
        risk_color = colors.HexColor('#fff3cd') if 'Risk' in (result['label'] or '') else colors.HexColor('#d4edda')
        result_box = [['Risk Assessment:', result['label'] or '--']]
        result_table = Table(result_box, colWidths=[2*inch, 5*inch])
        result_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), risk_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#0066cc')),
        ]))
        story.append(result_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Detailed Metrics
        story.append(Paragraph("Detailed Metrics", heading_style))
        metrics_data = [
            ['Metric', 'Value'],
            ['Blink Count', str(result['blink_count']) if result['blink_count'] else '--'],
            ['Blink Rate (BPM)', f"{result['blink_rate_bpm']:.1f}" if result['blink_rate_bpm'] else '--'],
            ['Mean Eye-Open Duration', f"{result['mean_ibi_sec']:.2f} s" if result['mean_ibi_sec'] else '--'],
            ['Max Eye-Open Duration', f"{result['max_eye_open_sec']:.2f} s" if result['max_eye_open_sec'] else '--'],
        ]
        metrics_table = Table(metrics_data, colWidths=[3.5*inch, 3.5*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f9f9f9')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ]))
        story.append(metrics_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Interpretation
        story.append(Paragraph("Interpretation", heading_style))
        interp_text = "Dry eye risk assessment based on blink patterns analysis. Low blink rates or long eye-open durations may indicate possible dryness. This is a screening support tool only and should not be used as a medical diagnosis. Please consult an ophthalmologist for professional evaluation."
        story.append(Paragraph(interp_text, styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Footer
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#999999'), alignment=TA_CENTER)
        story.append(Paragraph("<strong>NAYAN-AI</strong> - AI-Assisted Eye Screening System", footer_style))
        story.append(Paragraph("Developed by: Krishnapriya S, Madhumitha S, Mahalakshmi B S", footer_style))
        story.append(Paragraph("Electronics and Communication Engineering Department", footer_style))
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", footer_style))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        filename = f"DryEye_Report_{patient['name']}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)
    
    except Exception as e:
        import traceback
        print(f"[DRYEYE PDF] Error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Error generating PDF: {str(e)}'}), 500

@app.route('/api/report/glaucoma/pdf/<int:patient_id>', methods=['GET'])
def generate_glaucoma_pdf(patient_id):
    """Generate PDF report for glaucoma screening"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from io import BytesIO
        
        # Get patient info and results
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            c.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
            patient = c.fetchone()
            
            if not patient:
                conn.close()
                return jsonify({'success': False, 'message': 'Patient not found'}), 404
            
            c.execute('SELECT * FROM glaucoma_results WHERE patient_id = ? ORDER BY timestamp DESC LIMIT 1', (patient_id,))
            result = c.fetchone()
            
            conn.close()
        
        if not result:
            return jsonify({'success': False, 'message': 'No glaucoma screening results found'}), 404
        
        # Create PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#0066cc'), spaceAfter=12, alignment=TA_CENTER)
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#0066cc'), spaceAfter=10, spaceBefore=12)
        
        # Header
        story.append(Paragraph("NAYAN-AI", title_style))
        story.append(Paragraph("Glaucoma Screening Report", styles['Heading2']))
        story.append(Paragraph("AI-Assisted Eye Screening System", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Patient Information
        story.append(Paragraph("Patient Information", heading_style))
        patient_data = [
            ['Name:', patient['name'] or '--', 'Age:', f"{patient['age']} years" if patient['age'] else '--'],
            ['Gender:', patient['gender'] or '--', 'Date:', result['timestamp'][:10] if result['timestamp'] else '--'],
        ]
        patient_table = Table(patient_data, colWidths=[1*inch, 2.5*inch, 1*inch, 2.5*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(patient_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Test Results
        story.append(Paragraph("Test Results", heading_style))
        risk_level = result['risk_level'] or 'Normal'
        risk_color = colors.HexColor('#fff3cd') if 'High' in risk_level or 'Moderate' in risk_level else colors.HexColor('#d4edda')
        result_box = [['Risk Assessment:', risk_level]]
        result_table = Table(result_box, colWidths=[2*inch, 5*inch])
        result_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), risk_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#0066cc')),
        ]))
        story.append(result_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Detailed Metrics
        story.append(Paragraph("Detailed Metrics", heading_style))
        metrics_data = [
            ['Metric', 'Value'],
            ['IOP Proxy (mmHg)', f"{result['iop_proxy']:.1f}" if result['iop_proxy'] else '--'],
            ['Delta (mm)', '0.5 mm'],
            ['K Proxy Value', f"{result['iop_proxy']:.2f}" if result['iop_proxy'] else '--'],
        ]
        metrics_table = Table(metrics_data, colWidths=[3.5*inch, 3.5*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f9f9f9')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ]))
        story.append(metrics_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Interpretation
        story.append(Paragraph("Interpretation", heading_style))
        interp_text = "Glaucoma risk assessment based on IOP proxy measurement. Elevated IOP proxy values may indicate increased risk. This is a screening support tool only and should not be used as a medical diagnosis. Please consult an ophthalmologist for professional evaluation and proper IOP measurement."
        story.append(Paragraph(interp_text, styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Footer
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#999999'), alignment=TA_CENTER)
        story.append(Paragraph("<strong>NAYAN-AI</strong> - AI-Assisted Eye Screening System", footer_style))
        story.append(Paragraph("Developed by: Krishnapriya S, Madhumitha S, Mahalakshmi B S", footer_style))
        story.append(Paragraph("Electronics and Communication Engineering Department", footer_style))
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", footer_style))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        filename = f"Glaucoma_Report_{patient['name']}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)
    
    except Exception as e:
        import traceback
        print(f"[GLAUCOMA PDF] Error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Error generating PDF: {str(e)}'}), 500

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
    candidates = [
        PROJECT_DIR / 'uploads' / folder / filename,
        BASE_DIR / 'uploads' / folder / filename,  # legacy: server started inside backend/
        Path('uploads') / folder / filename,       # legacy: server relies on CWD
    ]
    for file_path in candidates:
        try:
            if file_path.exists() and file_path.is_file():
                return send_file(str(file_path))
        except Exception:
            continue
    abort(404)


@app.route('/api/debug/upload-path', methods=['GET'])
def debug_upload_path():
    """Debug helper for upload path resolution (safe, read-only)."""
    folder = request.args.get('folder', 'cataract')
    filename = request.args.get('filename', '')

    candidates = [
        PROJECT_DIR / 'uploads' / folder / filename,
        BASE_DIR / 'uploads' / folder / filename,
        Path('uploads') / folder / filename,
    ]

    return jsonify({
        'success': True,
        'cwd': os.getcwd(),
        'BASE_DIR': str(BASE_DIR),
        'PROJECT_DIR': str(PROJECT_DIR),
        'folder': folder,
        'filename': filename,
        'candidates': [
            {
                'path': str(p),
                'exists': bool(p.exists()) if filename else None,
                'is_file': bool(p.is_file()) if filename else None,
            }
            for p in candidates
        ]
    }), 200

@app.route('/debug/<filename>')
def serve_debug(filename):
    """Serve debug files"""
    file_path = PROJECT_DIR / 'debug' / filename
    if not file_path.exists() or not file_path.is_file():
        abort(404)
    return send_file(str(file_path))

# ============== HEALTH CHECK ==============
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'NAYAN-AI Backend',
        'timestamp': datetime.now().isoformat()
    }), 200


# ============== COMPATIBILITY ROUTES (LEGACY DOCS/DEMOS) ==============
@app.route('/health', methods=['GET'])
def health_check_legacy():
    return health_check()


@app.route('/cataract/upload', methods=['POST'])
def upload_cataract_legacy():
    return upload_cataract()


@app.route('/dryeye/upload', methods=['POST'])
def upload_dryeye_legacy():
    return upload_dryeye()


@app.route('/glaucoma/measure', methods=['POST'])
def glaucoma_measure_legacy():
    return glaucoma_measure()


@app.route('/results/<result_type>/<int:patient_id>', methods=['GET'])
def get_results_legacy(result_type, patient_id):
    return get_results(result_type, patient_id)

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
    
    host = os.environ.get('NAYAN_HOST', '0.0.0.0')
    port = int(os.environ.get('NAYAN_PORT', '5000'))

    try:
        socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
    except Exception as e:
        print(f"ERROR: Failed to start server: {e}")
        import traceback
        traceback.print_exc()
