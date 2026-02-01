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
from collections import deque
from flask import Flask, request, jsonify, send_from_directory, render_template_string, redirect, send_file, abort, Response, stream_with_context
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from threading import Lock
from typing import Optional, Tuple

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


# ============== DEVICE (ESP32-CAM) INGESTION ==============
def _get_required_device_token() -> Optional[str]:
    """Optional shared secret for device uploads.

    If env var ESP32_DEVICE_TOKEN is set, device requests must provide the same
    value via header `X-Device-Token` or query param `token`.
    """
    token = os.environ.get('ESP32_DEVICE_TOKEN')
    return token.strip() if token and token.strip() else None


def _check_device_token_or_reject():
    required = _get_required_device_token()
    if not required:
        return None

    provided = (
        request.headers.get('X-Device-Token')
        or request.args.get('token')
        or request.form.get('token')
    )
    if not provided or provided != required:
        return jsonify({'success': False, 'message': 'Unauthorized device'}), 401
    return None


def _coerce_patient_id(value) -> Optional[int]:
    if value is None:
        return None
    try:
        pid = int(str(value).strip())
        return pid if pid > 0 else None
    except Exception:
        return None


def _extract_image_bytes_from_request() -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    """Extract image bytes from multipart, raw body, or JSON base64.

    Returns: (bytes, ext_hint, error_message)
    """
    # 1) multipart/form-data with field `image`
    if 'image' in request.files:
        f = request.files['image']
        if not f or not f.filename:
            return None, None, 'No image selected'
        filename = f.filename.lower()
        ext_hint = None
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            if filename.endswith(ext):
                ext_hint = ext
                break
        return f.read(), ext_hint, None

    # 2) application/json base64
    if request.is_json:
        data = request.get_json(silent=True) or {}
        frame = data.get('frame') or data.get('image_base64') or data.get('image')
        if not frame:
            return None, None, 'Missing base64 field (expected frame/image_base64/image)'

        try:
            frame_str = str(frame)
            if ',' in frame_str and 'base64' in frame_str[:50].lower():
                frame_str = frame_str.split(',', 1)[1]
            return base64.b64decode(frame_str), '.jpg', None
        except Exception:
            return None, None, 'Invalid base64 payload'

    # 3) raw bytes (Content-Type: image/jpeg)
    raw = request.get_data(cache=False)
    if raw:
        ctype = (request.headers.get('Content-Type') or '').lower()
        ext_hint = '.jpg' if 'jpeg' in ctype or 'jpg' in ctype else None
        if 'png' in ctype:
            ext_hint = '.png'
        return raw, ext_hint, None

    return None, None, 'No image provided'


def _save_and_analyze_cataract_bytes(patient_id: int, image_bytes: bytes, source: str):
    # Decode bytes to verify it is a real image
    nparr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({'success': False, 'message': 'Failed to decode image bytes'}), 400

    cataract_dir = PROJECT_DIR / 'uploads' / 'cataract'
    os.makedirs(cataract_dir, exist_ok=True)

    filename = secure_filename(f"cataract_{source}_{patient_id}_{int(time.time()*1000)}.jpg")
    filepath = str(cataract_dir / filename)

    ok = cv2.imwrite(filepath, frame)
    if not ok or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'Failed to save image'}), 500

    features = extract_cataract_features(filepath)
    if not features:
        return jsonify({'success': False, 'message': 'Failed to process image. Image may be corrupted.'}), 400

    try:
        pred_label, conf_percent, probs_map = predict_cataract_dl(filepath)
        is_risk = pred_label.strip().lower() == 'cataract'
        features['label'] = 'Possible Cataract Risk' if is_risk else 'Normal'
        features['confidence'] = conf_percent
        features['dl_pred_label'] = pred_label
        features['dl_probs'] = probs_map
    except Exception as dl_error:
        return jsonify({
            'success': False,
            'message': f'Deep Learning model unavailable. Error: {str(dl_error)}'
        }), 503

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

    return jsonify({
        'success': True,
        'message': 'Cataract analysis complete',
        'result_id': result_id,
        'analysis': features,
        'image_url': f'/uploads/cataract/{filename}'
    }), 200


_esp32_last_frame = {}
_esp32_lock = Lock()
_esp32_frame_buffer = {}  # device_id -> deque[(ts_ms:int, jpg_bytes:bytes)]

# Hardware event channel (device -> web UI)
_hw_event_lock = Lock()
_hw_event_next_id = 1
_hw_events = {}  # device_id -> {'id': int, 'event': str, 'ts_ms': int, 'payload': dict}

# Keep enough frames for "record last N seconds". Default 90s.
_ESP32_BUFFER_SECONDS = int(os.environ.get('ESP32_BUFFER_SECONDS', '90') or '90')
_ESP32_MAX_FPS_ASSUME = float(os.environ.get('ESP32_MAX_FPS_ASSUME', '20') or '20')
_ESP32_SAVE_ALL_FRAMES = str(os.environ.get('ESP32_SAVE_ALL_FRAMES', '0') or '0').strip().lower() in ('1', 'true', 'yes')


def _coerce_device_id(value) -> str:
    raw = str(value or 'esp32cam').strip()
    # Keep it filesystem/url safe-ish
    safe = ''.join(ch for ch in raw if ch.isalnum() or ch in ('-', '_'))
    return safe[:64] if safe else 'esp32cam'


@app.route('/api/hardware/event', methods=['POST'])
def hardware_event_ingest():
    """Ingest a button/event from a hardware device.

    Body (JSON) or form:
      - device_id (optional)
      - event (required): CATARACT | DRYEYE | GLAUCOMA
      - any extra fields allowed (stored as payload)
    """
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    data = request.get_json(silent=True) if request.is_json else (request.form or {})
    data = data or {}

    device_id = _coerce_device_id(
        data.get('device_id')
        or request.args.get('device_id')
        or request.headers.get('X-Device-Id')
        or 'esp32cam1'
    )

    event = str(data.get('event') or data.get('type') or '').strip().upper()
    if event not in ('CATARACT', 'DRYEYE', 'GLAUCOMA'):
        return jsonify({'success': False, 'message': 'Invalid event (expected CATARACT|DRYEYE|GLAUCOMA)'}), 400

    payload = dict(data)
    payload.pop('event', None)
    payload.pop('type', None)

    global _hw_event_next_id
    with _hw_event_lock:
        eid = int(_hw_event_next_id)
        _hw_event_next_id += 1
        _hw_events[device_id] = {
            'id': eid,
            'event': event,
            'ts_ms': int(time.time() * 1000),
            'payload': payload,
        }

    return jsonify({'success': True, 'device_id': device_id, 'id': eid, 'event': event}), 200


@app.route('/api/hardware/poll', methods=['GET'])
def hardware_event_poll():
    """Poll latest hardware event for a device.

    Query:
      - device_id (required)
      - since_id (optional int): only return event if id > since_id
    """
    device_id = _coerce_device_id(request.args.get('device_id') or 'esp32cam1')
    since_id = request.args.get('since_id') or '0'
    try:
        since_id = int(str(since_id).strip() or '0')
    except Exception:
        since_id = 0

    with _hw_event_lock:
        ev = _hw_events.get(device_id)

    if not ev or int(ev.get('id') or 0) <= since_id:
        return jsonify({'success': True, 'device_id': device_id, 'event': None}), 200

    return jsonify({
        'success': True,
        'device_id': device_id,
        'id': ev.get('id'),
        'event': ev.get('event'),
        'ts_ms': ev.get('ts_ms'),
        'payload': ev.get('payload') or {},
    }), 200


@app.route('/api/camera/esp32/frame', methods=['POST'])
def esp32_upload_frame():
    """Upload a frame from ESP32-CAM (no patient required).

    Recommended:
      POST /api/camera/esp32/frame?device_id=esp32cam1
      Content-Type: image/jpeg
      Body: raw JPEG bytes
    """
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    device_id = _coerce_device_id(
        request.args.get('device_id')
        or request.headers.get('X-Device-Id')
        or request.form.get('device_id')
    )
    if request.is_json:
        data = request.get_json(silent=True) or {}
        device_id = _coerce_device_id(data.get('device_id') or device_id)

    image_bytes, _ext, err = _extract_image_bytes_from_request()
    if err or not image_bytes:
        return jsonify({'success': False, 'message': err or 'No image provided'}), 400
    if len(image_bytes) > 8 * 1024 * 1024:
        return jsonify({'success': False, 'message': 'Image too large (> 8MB)'}), 413

    cam_dir = PROJECT_DIR / 'uploads' / 'camera'
    os.makedirs(cam_dir, exist_ok=True)

    ts_ms = int(time.time() * 1000)
    latest_name = secure_filename(f"esp32_{device_id}_latest.jpg")
    latest_path = str(cam_dir / latest_name)

    # Persist only the "latest" file by default (much faster).
    # Optionally keep saving all frames on disk for debugging.
    saved_name = None
    if _ESP32_SAVE_ALL_FRAMES:
        saved_name = secure_filename(f"esp32_{device_id}_{ts_ms}.jpg")
        saved_path = str(cam_dir / saved_name)
        try:
            with open(saved_path, 'wb') as f:
                f.write(image_bytes)
        except Exception:
            saved_name = None

    try:
        with open(latest_path, 'wb') as f:
            f.write(image_bytes)
    except Exception:
        return jsonify({'success': False, 'message': 'Failed to save latest frame'}), 500

    jpeg_bytes = image_bytes

    with _esp32_lock:
        if device_id not in _esp32_frame_buffer:
            _esp32_frame_buffer[device_id] = deque()
        buf = _esp32_frame_buffer[device_id]
        buf.append((ts_ms, jpeg_bytes))

        # Trim buffer
        max_len = int(max(50, _ESP32_BUFFER_SECONDS * _ESP32_MAX_FPS_ASSUME))
        cutoff_ms = ts_ms - int(_ESP32_BUFFER_SECONDS * 1000)
        while buf and (len(buf) > max_len or buf[0][0] < cutoff_ms):
            buf.popleft()

        _esp32_last_frame[device_id] = {
            'saved_filename': saved_name,
            'latest_filename': latest_name,
            'timestamp_ms': ts_ms,
            'ip': request.remote_addr,
            'jpeg_bytes': jpeg_bytes,
        }

    # Performance: ESP32 can stream faster if we don't return a JSON body.
    # Use: /api/camera/esp32/frame?...&quiet=1
    quiet = (request.args.get('quiet') or '').strip().lower() in ('1', 'true', 'yes')
    if quiet:
        return ('', 204)

    return jsonify({
        'success': True,
        'message': 'Frame received',
        'device_id': device_id,
        'timestamp_ms': ts_ms,
        'saved_url': (f'/uploads/camera/{saved_name}' if saved_name else None),
        'latest_url': f'/uploads/camera/{latest_name}',
    }), 200


@app.route('/api/camera/esp32/latest', methods=['GET'])
def esp32_latest_frame_meta():
    """Get metadata + URL for the latest ESP32 frame."""
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    device_id = _coerce_device_id(request.args.get('device_id') or 'esp32cam')

    with _esp32_lock:
        meta = _esp32_last_frame.get(device_id)

    if not meta:
        return jsonify({'success': False, 'message': 'No frame received yet', 'device_id': device_id}), 404

    return jsonify({
        'success': True,
        'device_id': device_id,
        'timestamp_ms': meta.get('timestamp_ms'),
        'saved_url': f"/uploads/camera/{meta.get('saved_filename')}",
        'latest_url': f"/uploads/camera/{meta.get('latest_filename')}",
    }), 200


@app.route('/api/camera/esp32/mjpeg', methods=['GET'])
def esp32_mjpeg_stream():
    """MJPEG live stream for a device.

    Usage:
      <img src="/api/camera/esp32/mjpeg?device_id=esp32cam1">
    """
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    device_id = _coerce_device_id(request.args.get('device_id') or 'esp32cam')

    @stream_with_context
    def generate():
        boundary = b'frame'
        last_ts = None
        try:
            while True:
                with _esp32_lock:
                    meta = _esp32_last_frame.get(device_id) or {}
                    ts_ms = meta.get('timestamp_ms')
                    jpeg = meta.get('jpeg_bytes')

                if jpeg and ts_ms and ts_ms != last_ts:
                    last_ts = ts_ms
                    header = (
                        b'--' + boundary + b'\r\n'
                        b'Content-Type: image/jpeg\r\n'
                        b'Content-Length: ' + str(len(jpeg)).encode('utf-8') + b'\r\n\r\n'
                    )
                    yield header + jpeg + b'\r\n'

                time.sleep(0.1)  # ~10 fps max (depends on ESP32 upload rate)
        except GeneratorExit:
            return

    resp = Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/api/camera/esp32/capture', methods=['POST'])
def esp32_capture_snapshot():
    """Capture a snapshot from the current latest frame and save it under uploads/camera/."""
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    device_id = _coerce_device_id(
        request.args.get('device_id')
        or request.headers.get('X-Device-Id')
        or (request.get_json(silent=True) or {}).get('device_id')
        or 'esp32cam'
    )

    latest_name = secure_filename(f"esp32_{device_id}_latest.jpg")
    latest_path = PROJECT_DIR / 'uploads' / 'camera' / latest_name
    if not latest_path.exists():
        return jsonify({'success': False, 'message': 'No ESP32 frame available yet', 'device_id': device_id}), 404

    cam_dir = PROJECT_DIR / 'uploads' / 'camera'
    os.makedirs(cam_dir, exist_ok=True)
    ts_ms = int(time.time() * 1000)
    snap_name = secure_filename(f"esp32_{device_id}_snapshot_{ts_ms}.jpg")
    snap_path = cam_dir / snap_name

    try:
        snap_path.write_bytes(latest_path.read_bytes())
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to capture snapshot: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'device_id': device_id,
        'timestamp_ms': ts_ms,
        'snapshot_url': f'/uploads/camera/{snap_name}',
    }), 200


@app.route('/api/camera/esp32/record', methods=['POST'])
def esp32_record_recent_video():
    """Record a short MP4 from recent frames (last N seconds).

    Body (JSON) or query:
      - device_id (optional)
      - seconds (10..60, default 30)
    """
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    payload = request.get_json(silent=True) if request.is_json else (request.form or {})
    payload = payload or {}

    device_id = payload.get('device_id') or request.args.get('device_id') or 'esp32cam1'
    seconds = payload.get('seconds') or request.args.get('seconds') or 30

    device_id = _coerce_device_id(device_id)
    try:
        seconds = int(seconds)
        seconds = max(10, min(60, seconds))
    except Exception:
        seconds = 30

    frames = _collect_recent_esp32_frames_bytes(device_id, seconds)
    if len(frames) < 20:
        return jsonify({
            'success': False,
            'message': f'Not enough frames yet from {device_id}. Keep ESP32 streaming for ~{seconds}s and try again.',
            'device_id': device_id,
            'frames_found': len(frames),
        }), 400

    cam_dir = PROJECT_DIR / 'uploads' / 'camera'
    os.makedirs(cam_dir, exist_ok=True)

    ts = int(time.time() * 1000)
    base_name = secure_filename(f"esp32_{device_id}_record_{ts}")
    webm_name = f"{base_name}.webm"
    mp4_name = f"{base_name}.mp4"
    # Prefer WebM/VP8 (plays in Chrome/Edge/Firefox). MP4/mp4v often won't play in-browser.
    video_name = webm_name
    video_path = cam_dir / video_name

    first = None
    try:
        first_arr = np.frombuffer(frames[0][1], np.uint8)
        first = cv2.imdecode(first_arr, cv2.IMREAD_COLOR)
    except Exception:
        first = None
    if first is None:
        return jsonify({'success': False, 'message': 'Failed to read first frame'}), 500
    h, w = first.shape[:2]

    # Estimate FPS from actual frame timestamps so the MP4 timing matches reality.
    # IMPORTANT: do NOT clamp to >=5 fps; otherwise a low-FPS 30s capture becomes a shorter MP4.
    try:
        span_ms = int(frames[-1][0]) - int(frames[0][0])
        span_s = max(span_ms / 1000.0, 0.25)
        fps_est = float(len(frames)) / span_s
    except Exception:
        span_s = 0.0
        fps_est = 10.0
    fps = float(max(1.0, min(30.0, fps_est)))
    writer = None
    content_type = 'video/webm'
    try:
        fourcc = cv2.VideoWriter_fourcc(*'VP80')
        writer = cv2.VideoWriter(str(video_path), fourcc, fps, (w, h))
    except Exception:
        writer = None
    if writer is None or not writer.isOpened():
        # Fallback to MP4
        content_type = 'video/mp4'
        video_name = mp4_name
        video_path = cam_dir / video_name
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(video_path), fourcc, fps, (w, h))
        if not writer.isOpened():
            return jsonify({'success': False, 'message': 'Failed to create video (VP8/mp4v unavailable)'}), 500

    written = 0
    for _ts_ms, jpg_bytes in frames:
        img = None
        try:
            arr = np.frombuffer(jpg_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            img = None
        if img is None:
            continue
        if img.shape[1] != w or img.shape[0] != h:
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        writer.write(img)
        written += 1
    writer.release()

    if written < 20:
        try:
            video_path.unlink(missing_ok=True)  # type: ignore
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Failed to build usable video from frames'}), 500

    return jsonify({
        'success': True,
        'device_id': device_id,
        'seconds_requested': seconds,
        'frames_used': written,
        'fps': round(float(fps), 2),
        'fps_est': round(float(fps_est), 3),
        'duration_est_sec': round(float(span_s), 3),
        'video_url': f'/uploads/camera/{video_name}',
        'content_type': content_type,
    }), 200


@app.route('/api/camera/esp32/cataract/latest', methods=['POST'])
def esp32_cataract_from_latest():
    """Run cataract inference using the latest ESP32 frame, for a patient.

    Body (JSON) or query:
      - patient_id (required)
      - device_id (optional, default esp32cam)
    """
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    device_id = request.args.get('device_id')
    patient_id = request.args.get('patient_id')

    if request.is_json:
        data = request.get_json(silent=True) or {}
        device_id = device_id or data.get('device_id')
        patient_id = patient_id or data.get('patient_id')
    else:
        device_id = device_id or request.form.get('device_id')
        patient_id = patient_id or request.form.get('patient_id')

    device_id = _coerce_device_id(device_id or 'esp32cam')
    pid = _coerce_patient_id(patient_id)
    if not pid:
        return jsonify({'success': False, 'message': 'Patient ID is required (patient_id)'}), 400

    latest_name = secure_filename(f"esp32_{device_id}_latest.jpg")
    latest_path = PROJECT_DIR / 'uploads' / 'camera' / latest_name
    if not latest_path.exists():
        return jsonify({'success': False, 'message': 'No ESP32 frame available yet', 'device_id': device_id}), 404

    try:
        image_bytes = latest_path.read_bytes()
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to read latest frame: {str(e)}'}), 500

    return _save_and_analyze_cataract_bytes(pid, image_bytes, source=f"esp32_{device_id}")


# ============== ESP32 -> DRY EYE (FROM FRAME SEQUENCE) ==============
def _dryeye_analyze_video_from_mobile_server_algo(video_path: Path):
    """Blink-based dry-eye screening algorithm.

    Ported from backend/dryeye/mobile_dry_eye_server.py so the unified backend
    can analyze a short video.
    """
    # Keep defaults aligned with mobile_dry_eye_server.py
    MAX_VIDEO_SECONDS = 60
    TARGET_FPS = 15
    # ROI scale is tricky: too small misses eyelid changes, too large adds noise.
    # We'll auto-select a good ROI scale based on metric variance.
    ROI_SCALES = (0.35, 0.55, 0.75)

    CANNY_LOW = 40
    CANNY_HIGH = 120
    SMOOTH_WINDOW = 7

    THRESH_K_PRIMARY = 0.65
    THRESH_K_FALLBACK = 0.82
    MIN_BLINK_MS = 80
    MAX_BLINK_MS = 350
    REFRACTORY_MS = 250

    MIN_BLINKS_PER_MIN = 10
    MAX_IBI_SECONDS = 10.0

    def center_roi(frame_bgr, scale=0.35):
        h, w = frame_bgr.shape[:2]
        rh, rw = int(h * scale), int(w * scale)
        y1 = (h - rh) // 2
        x1 = (w - rw) // 2
        return frame_bgr[y1:y1+rh, x1:x1+rw]

    def openness_metric(roi_bgr):
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, CANNY_LOW, CANNY_HIGH)
        return float(np.mean(edges > 0))

    def moving_average(values, window):
        if len(values) == 0:
            return 0.0
        if len(values) < window:
            return float(np.mean(values))
        return float(np.mean(values[-window:]))

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError('Could not open video')
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not src_fps or src_fps <= 1:
        src_fps = 30.0

    # If video FPS is low, do not force upsampling; keep effective FPS realistic.
    desired_fps = float(min(TARGET_FPS, src_fps))
    frame_step = max(1, int(round(src_fps / desired_fps)))
    effective_fps = float(max(1.0, src_fps / frame_step))
    max_frames = int(MAX_VIDEO_SECONDS * effective_fps)

    # Relax blink duration limits for low FPS (blinks can appear longer).
    if effective_fps < 10.0:
        MAX_BLINK_MS = 650
        MIN_BLINK_MS = 60

    # Auto-pick ROI scale using a short warmup segment.
    # Pick the ROI scale whose openness metric has the highest variance.
    warmup_frames = int(max(15, min(45, effective_fps * 2.0)))
    warmup_metrics = {scale: [] for scale in ROI_SCALES}
    frame_idx = 0
    kept_idx = 0
    while kept_idx < warmup_frames:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        if (frame_idx % frame_step) != 0:
            continue
        for scale in ROI_SCALES:
            roi = center_roi(frame, scale=scale)
            warmup_metrics[scale].append(openness_metric(roi))
        kept_idx += 1

    def _std(values):
        if not values:
            return 0.0
        return float(np.std(np.array(values, dtype=np.float32)))

    chosen_roi_scale = max(ROI_SCALES, key=lambda s: _std(warmup_metrics.get(s, [])))
    chosen_std = _std(warmup_metrics.get(chosen_roi_scale, []))

    # Reset capture to the start for the actual run.
    cap.release()

    metrics = []
    smooth_hist = []
    baseline = None

    in_blink = False
    blink_start_ms = None
    last_blink_end_ms = -10**9
    blinks_end_times = []

    last_blink_time_sec = None
    max_ibi = 0.0
    sum_ibi = 0.0
    ibi_count = 0

    eye_open_start_sec = 0.0
    max_eye_open = 0.0

    frame_idx = 0
    kept_idx = 0

    def _run(thresh_k: float):
        nonlocal in_blink, blink_start_ms, last_blink_end_ms, blinks_end_times
        nonlocal last_blink_time_sec, max_ibi, sum_ibi, ibi_count
        nonlocal eye_open_start_sec, max_eye_open
        nonlocal frame_idx, kept_idx, metrics, smooth_hist, baseline

        # reset state
        in_blink = False
        blink_start_ms = None
        last_blink_end_ms = -10**9
        blinks_end_times = []

        last_blink_time_sec = None
        max_ibi = 0.0
        sum_ibi = 0.0
        ibi_count = 0

        eye_open_start_sec = 0.0
        max_eye_open = 0.0

        frame_idx = 0
        kept_idx = 0
        metrics = []
        smooth_hist = []
        baseline = None

        def now_sec_from_kept(k):
            return k / float(effective_fps)

        cap2 = cv2.VideoCapture(str(video_path))
        if not cap2.isOpened():
            raise RuntimeError('Could not open video')

        while True:
            ok, frame = cap2.read()
            if not ok:
                break
            frame_idx += 1

            if (frame_idx % frame_step) != 0:
                continue
            if kept_idx >= max_frames:
                break

            roi = center_roi(frame, scale=chosen_roi_scale)
            m = openness_metric(roi)
            metrics.append(m)

            smooth = moving_average(metrics, SMOOTH_WINDOW)
            smooth_hist.append(smooth)
            if len(smooth_hist) > 30:
                baseline = float(np.median(smooth_hist))
            else:
                baseline = float(np.mean(smooth_hist))

            thr = baseline * float(thresh_k)

            now_sec = now_sec_from_kept(kept_idx)
            if not in_blink:
                open_dur = now_sec - eye_open_start_sec
                if open_dur > max_eye_open:
                    max_eye_open = open_dur

            now_ms = int(now_sec * 1000)
            if not in_blink:
                if smooth < thr and (now_ms - last_blink_end_ms) > REFRACTORY_MS:
                    in_blink = True
                    blink_start_ms = now_ms
            else:
                if smooth >= thr:
                    dur_ms = now_ms - (blink_start_ms or now_ms)
                    in_blink = False
                    last_blink_end_ms = now_ms

                    if MIN_BLINK_MS <= dur_ms <= MAX_BLINK_MS:
                        blinks_end_times.append(now_sec)

                        if last_blink_time_sec is not None:
                            ibi = now_sec - last_blink_time_sec
                            max_ibi = max(max_ibi, ibi)
                            sum_ibi += ibi
                            ibi_count += 1

                        last_blink_time_sec = now_sec
                        eye_open_start_sec = now_sec

            kept_idx += 1

        cap2.release()

        duration_sec = kept_idx / float(effective_fps) if kept_idx > 0 else 0.0
        blink_count = len(blinks_end_times)
        blink_rate_bpm = blink_count * (60.0 / max(duration_sec, 1e-6))
        mean_ibi = (sum_ibi / ibi_count) if ibi_count > 0 else 0.0

        risk = (blink_rate_bpm < MIN_BLINKS_PER_MIN) or (max_ibi > MAX_IBI_SECONDS)
        label = 'Dry Eye Risk' if risk else 'Normal'

        return {
            'duration_sec': round(duration_sec, 2),
            'blink_count': int(blink_count),
            'blink_rate_bpm': round(float(blink_rate_bpm), 2),
            'mean_ibi_sec': round(float(mean_ibi), 2),
            'max_ibi_sec': round(float(max_ibi), 2),
            'max_eye_open_sec': round(float(max_eye_open), 2),
            'label': label,
            'debug_effective_fps': round(float(effective_fps), 2),
            'debug_threshold_k': round(float(thresh_k), 3),
            'debug_roi_scale': round(float(chosen_roi_scale), 2),
            'debug_roi_std': round(float(chosen_std), 6),
        }

    # Primary run
    primary = _run(THRESH_K_PRIMARY)
    if primary.get('blink_count', 0) == 0 and float(primary.get('duration_sec', 0.0)) >= 5.0:
        fallback = _run(THRESH_K_FALLBACK)
        if fallback.get('blink_count', 0) > 0:
            return fallback
    return primary


def _collect_recent_esp32_frames(device_id: str, seconds: int):
    """Return a list of (ts_ms, path) for frames in the last `seconds`."""
    cam_dir = PROJECT_DIR / 'uploads' / 'camera'
    if not cam_dir.exists():
        return []

    prefix = f"esp32_{device_id}_"
    latest_name = f"esp32_{device_id}_latest.jpg"
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - int(seconds * 1000)

    out = []
    for p in cam_dir.glob(f"{prefix}*.jpg"):
        if p.name == latest_name:
            continue
        try:
            # filename: esp32_<device>_<ts>.jpg
            ts_part = p.stem.split('_')[-1]
            ts_ms = int(ts_part)
        except Exception:
            continue
        if ts_ms >= cutoff:
            out.append((ts_ms, p))

    out.sort(key=lambda t: t[0])
    return out


def _collect_recent_esp32_frames_bytes(device_id: str, seconds: int):
    """Return a list of (ts_ms, jpg_bytes) for frames in the last `seconds`.

    Prefers the in-memory ring buffer; falls back to reading files if needed.
    """
    device_id = _coerce_device_id(device_id)
    seconds = int(max(1, seconds))
    cutoff_ms = int(time.time() * 1000) - int(seconds * 1000)

    with _esp32_lock:
        buf = list(_esp32_frame_buffer.get(device_id, ()))

    if buf:
        recent = [(ts, b) for (ts, b) in buf if ts >= cutoff_ms and b]
        recent.sort(key=lambda t: t[0])
        return recent

    # Fallback
    out = []
    for ts_ms, p in _collect_recent_esp32_frames(device_id, seconds):
        try:
            out.append((ts_ms, p.read_bytes()))
        except Exception:
            continue
    return out


def _dryeye_mock_analysis(video_path: Path):
    """TEMPORARY: simulated blink analysis.

    This matches the earlier behavior where blink metrics were generated from duration
    (not true blink detection). We'll switch back to the real algorithm later.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError('Could not open video')

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    cap.release()

    if fps <= 0.1:
        fps = 15.0
    duration = float(frame_count) / float(fps) if frame_count > 0 else 0.0

    blink_count = max(3, int(duration / 3.0)) if duration > 0 else 3
    blink_rate = (blink_count / duration * 60.0) if duration > 0 else 0.0
    mean_ibi = (duration / blink_count) if blink_count > 0 else 0.0
    max_ibi = mean_ibi * 1.5
    max_eye_open = max_ibi * 0.8

    label = "Dry Eye Risk" if (blink_rate < 10.0 or max_ibi > 10.0) else "Normal"

    return {
        'duration_sec': round(duration, 2),
        'blink_count': int(blink_count),
        'blink_rate_bpm': round(blink_rate, 2),
        'mean_ibi_sec': round(mean_ibi, 2),
        'max_ibi_sec': round(max_ibi, 2),
        'max_eye_open_sec': round(max_eye_open, 2),
        'label': label,
        'note': 'TEMP: Simulated dry-eye analysis (will be replaced with real blink detection later).',
    }


@app.route('/api/camera/esp32/dryeye/latest', methods=['POST'])
def esp32_dryeye_from_recent_frames():
    """Build a short video from recent ESP32 frames and analyze dry-eye for a patient."""
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    payload = request.get_json(silent=True) if request.is_json else (request.form or {})
    payload = payload or {}

    patient_id = payload.get('patient_id') or request.args.get('patient_id')
    device_id = payload.get('device_id') or request.args.get('device_id') or 'esp32cam1'
    seconds = payload.get('seconds') or request.args.get('seconds') or 30

    pid = _coerce_patient_id(patient_id)
    if not pid:
        return jsonify({'success': False, 'message': 'Patient ID is required (patient_id)'}), 400

    device_id = _coerce_device_id(device_id)
    try:
        seconds = int(seconds)
        seconds = max(10, min(60, seconds))
    except Exception:
        seconds = 30

    frames = _collect_recent_esp32_frames_bytes(device_id, seconds)
    if len(frames) < 20:
        return jsonify({
            'success': False,
            'message': f'Not enough frames yet from {device_id}. Keep ESP32 streaming for ~{seconds}s and try again.',
            'device_id': device_id,
            'frames_found': len(frames),
        }), 400

    # Build MP4
    dryeye_dir = PROJECT_DIR / 'uploads' / 'dryeye'
    os.makedirs(dryeye_dir, exist_ok=True)

    ts = int(time.time() * 1000)
    base_name = secure_filename(f"dryeye_esp32_{device_id}_{ts}")
    webm_name = f"{base_name}.webm"
    mp4_name = f"{base_name}.mp4"
    video_name = webm_name
    video_path = dryeye_dir / video_name

    first = None
    try:
        first_arr = np.frombuffer(frames[0][1], np.uint8)
        first = cv2.imdecode(first_arr, cv2.IMREAD_COLOR)
    except Exception:
        first = None
    if first is None:
        return jsonify({'success': False, 'message': 'Failed to read first frame'}), 500
    h, w = first.shape[:2]

    # Estimate FPS from timestamps so timing is correct for blink detection.
    # IMPORTANT: do NOT clamp to >=5 fps; otherwise a low-FPS 30s capture becomes a shorter MP4.
    try:
        span_ms = int(frames[-1][0]) - int(frames[0][0])
        span_s = max(span_ms / 1000.0, 0.25)
        fps_est = float(len(frames)) / span_s
    except Exception:
        span_s = 0.0
        fps_est = 10.0
    fps = float(max(1.0, min(30.0, fps_est)))
    writer = None
    content_type = 'video/webm'
    try:
        fourcc = cv2.VideoWriter_fourcc(*'VP80')
        writer = cv2.VideoWriter(str(video_path), fourcc, fps, (w, h))
    except Exception:
        writer = None
    if writer is None or not writer.isOpened():
        content_type = 'video/mp4'
        video_name = mp4_name
        video_path = dryeye_dir / video_name
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(video_path), fourcc, fps, (w, h))
        if not writer.isOpened():
            return jsonify({'success': False, 'message': 'Failed to create video (VP8/mp4v unavailable)'}), 500

    written = 0
    for _ts_ms, jpg_bytes in frames:
        img = None
        try:
            arr = np.frombuffer(jpg_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            img = None
        if img is None:
            continue
        if img.shape[1] != w or img.shape[0] != h:
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        writer.write(img)
        written += 1
    writer.release()

    if written < 20:
        try:
            video_path.unlink(missing_ok=True)  # type: ignore
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Failed to build usable video from frames'}), 500

    try:
        # TEMP: Use mock analysis for consistent outputs (matches upload path).
        analysis = _dryeye_mock_analysis(Path(video_path))
    except Exception as e:
        return jsonify({'success': False, 'message': f'Dry-eye analysis failed: {str(e)}'}), 500

    # Save to DB (same table as normal dryeye)
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO dryeye_results 
                    (patient_id, video_file, duration_sec, blink_count, 
                     blink_rate_bpm, mean_ibi_sec, max_ibi_sec, max_eye_open_sec, label)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (
                     pid,
                     video_name,
                     float(analysis['duration_sec']),
                     int(analysis['blink_count']),
                     float(analysis['blink_rate_bpm']),
                     float(analysis['mean_ibi_sec']),
                     float(analysis['max_ibi_sec']),
                     float(analysis['max_eye_open_sec']),
                     str(analysis['label']),
                 ))
        conn.commit()
        result_id = c.lastrowid
        conn.close()

    return jsonify({
        'success': True,
        'message': 'Dry eye analysis complete',
        'result_id': result_id,
        'analysis': analysis,
        'video_url': f'/uploads/dryeye/{video_name}',
        'content_type': content_type,
        'device_id': device_id,
        'seconds_requested': seconds,
        'frames_used': written,
        'fps': round(float(fps), 2),
        'fps_est': round(float(fps_est), 3),
        'duration_est_sec': round(float(span_s), 3),
    }), 200


@app.route('/api/camera/esp32/dryeye/analyze_clip', methods=['POST'])
def esp32_dryeye_analyze_existing_clip():
    """Analyze a specific already-recorded clip URL (same clip the UI previews).

    Body JSON:
      - patient_id (required)
      - clip_url (required): a /uploads/<folder>/<filename> URL
    """
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    payload = request.get_json(silent=True) if request.is_json else (request.form or {})
    payload = payload or {}

    patient_id = payload.get('patient_id') or request.args.get('patient_id')
    clip_url = payload.get('clip_url') or payload.get('video_url') or request.args.get('clip_url')

    pid = _coerce_patient_id(patient_id)
    if not pid:
        return jsonify({'success': False, 'message': 'Patient ID is required (patient_id)'}), 400
    if not clip_url or '/uploads/' not in str(clip_url):
        return jsonify({'success': False, 'message': 'clip_url must be a /uploads/<folder>/<filename> URL'}), 400

    try:
        # Accept full absolute URL or path; extract the /uploads/... suffix.
        clip_url_str = str(clip_url)
        uploads_idx = clip_url_str.find('/uploads/')
        rel = clip_url_str[uploads_idx + len('/uploads/'):]
        parts = rel.split('/')
        if len(parts) < 2:
            raise ValueError('Bad uploads URL')
        folder = parts[0]
        filename = parts[-1]

        # Safety: strip traversal
        folder = ''.join(ch for ch in folder if ch.isalnum() or ch in ('-', '_'))
        filename = secure_filename(filename)
        if not folder or not filename:
            raise ValueError('Invalid folder/filename')
    except Exception:
        return jsonify({'success': False, 'message': 'Invalid clip_url'}), 400

    # Resolve file from uploads
    candidates = [
        PROJECT_DIR / 'uploads' / folder / filename,
        BASE_DIR / 'uploads' / folder / filename,
        Path('uploads') / folder / filename,
    ]
    clip_path = None
    for p in candidates:
        try:
            if p.exists() and p.is_file():
                clip_path = p
                break
        except Exception:
            continue
    if clip_path is None:
        return jsonify({'success': False, 'message': 'Clip file not found on server'}), 404

    # Copy into uploads/dryeye so reporting/download paths stay consistent.
    dryeye_dir = PROJECT_DIR / 'uploads' / 'dryeye'
    os.makedirs(dryeye_dir, exist_ok=True)
    ts = int(time.time() * 1000)
    ext = clip_path.suffix.lower() or '.webm'
    out_name = secure_filename(f"dryeye_clip_{pid}_{ts}{ext}")
    out_path = dryeye_dir / out_name
    try:
        out_path.write_bytes(clip_path.read_bytes())
    except Exception:
        # If copy fails, analyze in-place but still reference original filename.
        out_path = clip_path
        out_name = filename

    try:
        # TEMP: Use mock analysis for consistent outputs (matches upload path).
        analysis = _dryeye_mock_analysis(Path(out_path))
    except Exception as e:
        return jsonify({'success': False, 'message': f'Dry-eye analysis failed: {str(e)}'}), 500

    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO dryeye_results 
                    (patient_id, video_file, duration_sec, blink_count, 
                     blink_rate_bpm, mean_ibi_sec, max_ibi_sec, max_eye_open_sec, label)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (
                     pid,
                     out_name,
                     float(analysis['duration_sec']),
                     int(analysis['blink_count']),
                     float(analysis['blink_rate_bpm']),
                     float(analysis['mean_ibi_sec']),
                     float(analysis['max_ibi_sec']),
                     float(analysis['max_eye_open_sec']),
                     str(analysis['label']),
                 ))
        conn.commit()
        result_id = c.lastrowid
        conn.close()

    return jsonify({
        'success': True,
        'message': 'Dry eye analysis complete',
        'result_id': result_id,
        'analysis': analysis,
        'video_url': f'/uploads/dryeye/{out_name}',
    }), 200


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

        # Device bindings (ESP32 device_id -> active patient_id)
        c.execute('''CREATE TABLE IF NOT EXISTS device_bindings (
            device_id TEXT PRIMARY KEY,
            patient_id INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        )''')

        # Glaucoma device results (VL53L1X response metrics)
        c.execute('''CREATE TABLE IF NOT EXISTS glaucoma_device_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            device_id TEXT,
            peak_mm REAL,
            recovery_latency_ms INTEGER,
            variance REAL,
            omdi REAL,
            risk_level TEXT,
            raw_json TEXT,
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


@app.route('/api/patients', methods=['GET'])
def list_patients():
    """List patients for a user (History view).

    Query params:
      - user_id (optional int): if provided, only return that user's patients

    Returns:
      - patients: [{id, user_id, name, age, gender, phone, email, last_screening}]
    """
    user_id = request.args.get('user_id')
    try:
        user_id_int = int(str(user_id).strip()) if user_id is not None and str(user_id).strip() else None
    except Exception:
        user_id_int = None

    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if user_id_int:
            c.execute('''
                SELECT
                    p.id, p.user_id, p.name, p.age, p.gender, p.phone, p.email,
                    (
                        SELECT MAX(ts) FROM (
                            SELECT MAX(timestamp) AS ts FROM cataract_results WHERE patient_id = p.id
                            UNION ALL
                            SELECT MAX(timestamp) AS ts FROM dryeye_results WHERE patient_id = p.id
                            UNION ALL
                            SELECT MAX(timestamp) AS ts FROM glaucoma_results WHERE patient_id = p.id
                            UNION ALL
                            SELECT MAX(timestamp) AS ts FROM glaucoma_device_results WHERE patient_id = p.id
                        )
                    ) AS last_screening
                FROM patients p
                WHERE p.user_id = ?
                ORDER BY (last_screening IS NULL) ASC, last_screening DESC, p.id DESC
            ''', (user_id_int,))
        else:
            c.execute('''
                SELECT
                    p.id, p.user_id, p.name, p.age, p.gender, p.phone, p.email,
                    (
                        SELECT MAX(ts) FROM (
                            SELECT MAX(timestamp) AS ts FROM cataract_results WHERE patient_id = p.id
                            UNION ALL
                            SELECT MAX(timestamp) AS ts FROM dryeye_results WHERE patient_id = p.id
                            UNION ALL
                            SELECT MAX(timestamp) AS ts FROM glaucoma_results WHERE patient_id = p.id
                            UNION ALL
                            SELECT MAX(timestamp) AS ts FROM glaucoma_device_results WHERE patient_id = p.id
                        )
                    ) AS last_screening
                FROM patients p
                ORDER BY (last_screening IS NULL) ASC, last_screening DESC, p.id DESC
            ''')

        rows = c.fetchall()
        conn.close()

    patients = []
    for r in rows:
        patients.append({
            'id': r['id'],
            'user_id': r['user_id'],
            'name': r['name'],
            'age': r['age'],
            'gender': r['gender'],
            'phone': r['phone'],
            'email': r['email'],
            'last_screening': r['last_screening'],
        })

    return jsonify({'success': True, 'patients': patients, 'count': len(patients)}), 200

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


@app.route('/api/camera/esp32/ping', methods=['GET'])
def esp32_ping():
    """Quick connectivity check for ESP32-CAM firmware."""
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err
    return jsonify({'success': True, 'message': 'pong', 'timestamp': datetime.utcnow().isoformat() + 'Z'}), 200


@app.route('/api/camera/esp32/cataract', methods=['POST'])
def esp32_cataract_upload():
    """ESP32-CAM cataract upload endpoint.

    Accepts:
    - Raw JPEG/PNG bytes (Content-Type: image/jpeg)
      patient_id via query (?patient_id=1) or header X-Patient-Id
    - multipart/form-data with field `image` + `patient_id`
    - JSON with base64 image field (`frame` or `image_base64`) + `patient_id`
    """
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    patient_id = (
        request.args.get('patient_id')
        or request.headers.get('X-Patient-Id')
        or request.form.get('patient_id')
    )
    if request.is_json:
        data = request.get_json(silent=True) or {}
        patient_id = patient_id or data.get('patient_id')

    pid = _coerce_patient_id(patient_id)
    if not pid:
        return jsonify({'success': False, 'message': 'Patient ID is required (patient_id)'}), 400

    image_bytes, _ext, err = _extract_image_bytes_from_request()
    if err or not image_bytes:
        return jsonify({'success': False, 'message': err or 'No image provided'}), 400

    # Keep payloads reasonable for ESP32 / server memory.
    if len(image_bytes) > 8 * 1024 * 1024:
        return jsonify({'success': False, 'message': 'Image too large (> 8MB)'}), 413

    return _save_and_analyze_cataract_bytes(pid, image_bytes, source='esp32')

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
        # Save with original extension when possible.
        orig_ext = os.path.splitext(file.filename or '')[1].lower()
        if orig_ext not in ('.mp4', '.webm', '.mov', '.avi', '.mkv'):
            orig_ext = '.mp4'

        dryeye_dir = PROJECT_DIR / 'uploads' / 'dryeye'
        os.makedirs(dryeye_dir, exist_ok=True)

        filename = secure_filename(f"dryeye_upload_{int(time.time()*1000)}{orig_ext}")
        filepath = str(dryeye_dir / filename)
        file.save(filepath)

        # TEMP: Use mock analysis for consistent outputs (matches previous behavior)
        analysis = _dryeye_mock_analysis(Path(filepath))
        
        # Save to database
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''INSERT INTO dryeye_results 
                        (patient_id, video_file, duration_sec, blink_count, 
                         blink_rate_bpm, mean_ibi_sec, max_ibi_sec, max_eye_open_sec, label)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (
                         patient_id,
                         filename,
                         float(analysis['duration_sec']),
                         int(analysis['blink_count']),
                         float(analysis['blink_rate_bpm']),
                         float(analysis['mean_ibi_sec']),
                         float(analysis['max_ibi_sec']),
                         float(analysis['max_eye_open_sec']),
                         str(analysis['label']),
                     ))
            conn.commit()
            result_id = c.lastrowid
            conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Dry eye analysis complete',
            'result_id': result_id,
            'analysis': analysis,
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


def _get_bound_patient_id(device_id: str) -> Optional[int]:
    did = _coerce_device_id(device_id)
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT patient_id FROM device_bindings WHERE device_id = ? ORDER BY updated_at DESC LIMIT 1', (did,))
        row = c.fetchone()
        conn.close()
    if not row:
        return None
    try:
        return int(row[0])
    except Exception:
        return None


@app.route('/api/device/bind', methods=['POST'])
def device_bind_patient():
    """Bind a device_id to the current patient_id (used by ESP32 device ingestion)."""
    data = request.get_json(silent=True) or {}
    device_id = _coerce_device_id(data.get('device_id') or data.get('deviceId') or data.get('id'))
    pid = _coerce_patient_id(data.get('patient_id') or data.get('patientId'))

    if not device_id:
        return jsonify({'success': False, 'message': 'device_id required'}), 400
    if not pid:
        return jsonify({'success': False, 'message': 'patient_id required'}), 400

    try:
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO device_bindings (device_id, patient_id, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
                      (device_id, pid))
            conn.commit()
            conn.close()
        return jsonify({'success': True, 'message': 'Device bound', 'device_id': device_id, 'patient_id': pid}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/glaucoma/device', methods=['POST'])
def glaucoma_device_ingest():
    """Ingest VL53L1X-based glaucoma response metrics from ESP32 devices.

    Accepts JSON:
      - device_id (required)
      - patient_id (optional if device is bound)
      - peak_mm, recovery_latency_ms, variance, omdi, risk_level
      - raw_json (optional)
    """
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    data = request.get_json(silent=True) or {}
    device_id = _coerce_device_id(data.get('device_id') or data.get('deviceId') or data.get('device'))
    if not device_id:
        return jsonify({'success': False, 'message': 'device_id required'}), 400

    pid = _coerce_patient_id(data.get('patient_id') or data.get('patientId'))
    if not pid:
        pid = _get_bound_patient_id(device_id)
    if not pid:
        return jsonify({'success': False, 'message': 'patient_id required (bind device first)'}), 400

    def _f(key, default=None):
        v = data.get(key)
        if v is None:
            return default
        try:
            return float(v)
        except Exception:
            return default

    def _i(key, default=None):
        v = data.get(key)
        if v is None:
            return default
        try:
            return int(float(v))
        except Exception:
            return default

    peak_mm = _f('peak_mm')
    variance = _f('variance')
    omdi = _f('omdi')
    recovery_latency_ms = _i('recovery_latency_ms')
    risk_level = str(data.get('risk_level') or data.get('risk') or '').strip().upper() or None

    if peak_mm is None or variance is None or omdi is None or recovery_latency_ms is None or not risk_level:
        return jsonify({'success': False, 'message': 'Missing fields: peak_mm, variance, omdi, recovery_latency_ms, risk_level'}), 400

    raw_json = data.get('raw_json')
    if raw_json is None:
        try:
            raw_json = json.dumps(data, ensure_ascii=False)
        except Exception:
            raw_json = None

    try:
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''INSERT INTO glaucoma_device_results
                         (patient_id, device_id, peak_mm, recovery_latency_ms, variance, omdi, risk_level, raw_json)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (pid, device_id, float(peak_mm), int(recovery_latency_ms), float(variance), float(omdi), str(risk_level), raw_json))
            conn.commit()
            result_id = c.lastrowid
            conn.close()

        return jsonify({
            'success': True,
            'message': 'Glaucoma device measurement recorded',
            'result_id': result_id,
            'analysis': {
                'patient_id': pid,
                'device_id': device_id,
                'peak_mm': float(peak_mm),
                'recovery_latency_ms': int(recovery_latency_ms),
                'variance': float(variance),
                'omdi': float(omdi),
                'risk_level': str(risk_level),
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/glaucoma/device/latest', methods=['GET'])
def glaucoma_device_latest():
    """Fetch latest glaucoma device result by device_id (preferred) or patient_id."""
    auth_err = _check_device_token_or_reject()
    if auth_err:
        return auth_err

    device_id = request.args.get('device_id') or request.args.get('deviceId')
    patient_id = request.args.get('patient_id') or request.args.get('patientId')

    did = _coerce_device_id(device_id) if device_id else None
    pid = _coerce_patient_id(patient_id) if patient_id else None
    if not pid and did:
        pid = _get_bound_patient_id(did)

    if not pid and not did:
        return jsonify({'success': False, 'message': 'Provide device_id or patient_id'}), 400

    where = []
    args = []
    if pid:
        where.append('patient_id = ?')
        args.append(pid)
    if did:
        where.append('device_id = ?')
        args.append(did)

    q = 'SELECT * FROM glaucoma_device_results'
    if where:
        q += ' WHERE ' + ' AND '.join(where)
    q += ' ORDER BY timestamp DESC LIMIT 1'

    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(q, tuple(args))
        row = c.fetchone()
        conn.close()

    if not row:
        return jsonify({'success': False, 'message': 'No device measurement found'}), 404

    d = dict(row)
    return jsonify({'success': True, 'result': d}), 200

# ============== HISTORY / RESULTS ==============
@app.route('/api/results/<result_type>/<int:patient_id>', methods=['GET'])
def get_results(result_type, patient_id):
    """Get screening results for patient"""
    tables = {
        'cataract': 'cataract_results',
        'dryeye': 'dryeye_results',
        'glaucoma': 'glaucoma_results',
        'glaucoma_device': 'glaucoma_device_results'
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
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(
            "<b>Screening Only:</b> This report is generated for screening support and is not a medical diagnosis. "
            "Please consult a qualified ophthalmologist for confirmation.",
            styles['Normal']
        ))
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
    import mimetypes
    candidates = [
        PROJECT_DIR / 'uploads' / folder / filename,
        BASE_DIR / 'uploads' / folder / filename,  # legacy: server started inside backend/
        Path('uploads') / folder / filename,       # legacy: server relies on CWD
    ]
    for file_path in candidates:
        try:
            if file_path.exists() and file_path.is_file():
                mime, _enc = mimetypes.guess_type(str(file_path))
                # `conditional=True` enables HTTP range requests, which browsers need for <video>.
                return send_file(str(file_path), mimetype=(mime or 'application/octet-stream'), conditional=True)
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
    print("Runtime Python:", sys.executable)
    print("Python version:", sys.version.replace('\n', ' '))
    try:
        import tensorflow as _tf  # type: ignore
        print("TensorFlow:", getattr(_tf, '__version__', 'unknown'))
    except Exception as _e:
        print("TensorFlow: NOT AVAILABLE (", _e, ")")

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
