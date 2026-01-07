import os
import time
import csv

import cv2
import numpy as np
from flask import Flask, request, render_template_string, send_from_directory

APP = Flask(__name__)

UPLOAD_DIR = "uploads"
DEBUG_DIR = "debug"
LOG_FILE = "cataract_log.csv"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

HTML = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nayan-AI Cataract Upload</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 18px; }
    .card { padding: 14px; border: 1px solid #ddd; border-radius: 10px; margin-top: 12px; }
    img { max-width: 100%; height: auto; border-radius: 10px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  </style>
</head>
<body>
  <h2>Nayan-AI Cataract Screening (Mobile Upload)</h2>
  <div class="card">
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="image" accept="image/*" capture="environment" required>
      <button type="submit">Upload & Analyze</button>
    </form>
    <p class="mono">
      Tips: keep the eye centered, use same lighting, avoid reflections.
    </p>
  </div>

  {% if result %}
  <div class="card">
    <h3>Result</h3>
    <p><b>Label:</b> {{result.label}}</p>
    <p class="mono">
      C (contrast)={{result.C}} |
      S (sharpness)={{result.S}} |
      E (edge)={{result.E}}
    </p>
    <p class="mono">
      Thresholds: Tc={{result.Tc}} Ts={{result.Ts}} | ROI scale={{result.roi_scale}}
    </p>

    <h4>Uploaded Image</h4>
    <img src="/uploads/{{result.upload_name}}" alt="uploaded">

    <h4>ROI Debug (Left: ROI box, Right: ROI zoom)</h4>
    <img src="/debug/{{result.debug_name}}" alt="roi debug">
  </div>
  {% endif %}
</body>
</html>
"""

def ensure_csv():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "timestamp",
                "upload_file",
                "debug_file",
                "C_contrast",
                "S_sharpness",
                "E_edge",
                "Tc",
                "Ts",
                "roi_scale",
                "label"
            ])

# ---------- ROI debug utilities ----------
def preprocess_gray(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    return gray

def center_roi_coords(gray_shape, scale=0.45):
    h, w = gray_shape[:2]
    rh, rw = int(h * scale), int(w * scale)
    y1 = (h - rh) // 2
    x1 = (w - rw) // 2
    return x1, y1, rw, rh

def extract_center_roi(gray, scale=0.45):
    x, y, rw, rh = center_roi_coords(gray.shape, scale=scale)
    roi = gray[y:y+rh, x:x+rw]
    return roi, (x, y, rw, rh)

def draw_roi_box(frame_bgr, rect, color=(0, 255, 0), thickness=2):
    x, y, rw, rh = rect
    out = frame_bgr.copy()
    cv2.rectangle(out, (x, y), (x + rw, y + rh), color, thickness)

    # image center (blue)
    h, w = out.shape[:2]
    cx, cy = w // 2, h // 2
    cv2.drawMarker(out, (cx, cy), (255, 0, 0), markerType=cv2.MARKER_CROSS, markerSize=20, thickness=2)

    # ROI center (red)
    rcx, rcy = x + rw // 2, y + rh // 2
    cv2.drawMarker(out, (rcx, rcy), (0, 0, 255), markerType=cv2.MARKER_TILTED_CROSS, markerSize=20, thickness=2)

    cv2.putText(out, f"ROI x={x} y={y} w={rw} h={rh}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    return out

def make_roi_zoom_view(roi_gray, zoom_size=(360, 360)):
    roi_bgr = cv2.cvtColor(roi_gray, cv2.COLOR_GRAY2BGR)
    roi_zoom = cv2.resize(roi_bgr, zoom_size, interpolation=cv2.INTER_CUBIC)
    cv2.putText(roi_zoom, "ROI ZOOM", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    return roi_zoom

# ---------- Feature extraction ----------
def compute_features(roi):
    # Contrast
    C = float(np.std(roi))

    # Sharpness (blur proxy)
    lap = cv2.Laplacian(roi, cv2.CV_64F)
    S = float(lap.var())

    # Edge strength
    gx = cv2.Sobel(roi, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(roi, cv2.CV_64F, 0, 1, ksize=3)
    E = float(np.mean(np.sqrt(gx*gx + gy*gy)))

    return C, S, E

def cataract_label(C, S, Tc=22.0, Ts=120.0):
    # v1: low contrast + low sharpness => cataract risk
    if (C < Tc) and (S < Ts):
        return "Possible Cataract Risk"
    return "Normal"

@APP.route("/", methods=["GET", "POST"])
def index():
    ensure_csv()
    result = None

    # Initial defaults (you will calibrate later)
    Tc = 22.0
    Ts = 120.0
    roi_scale = 0.25

    if request.method == "POST":
        if "image" not in request.files:
            return render_template_string(HTML, result=None)

        f = request.files["image"]
        if not f.filename:
            return render_template_string(HTML, result=None)

        ts = time.strftime("%Y%m%d_%H%M%S")
        upload_name = f"eye_{ts}.jpg"
        upload_path = os.path.join(UPLOAD_DIR, upload_name)
        f.save(upload_path)

        frame = cv2.imread(upload_path)
        if frame is None:
            return "Upload failed: cannot read image.", 400

        gray = preprocess_gray(frame)
        roi, rect = extract_center_roi(gray, scale=roi_scale)

        # --- compute features + label ---
        C, S, E = compute_features(roi)
        label = cataract_label(C, S, Tc=Tc, Ts=Ts)

        # --- create ROI debug composite ---
        marked = draw_roi_box(frame, rect)
        roi_zoom = make_roi_zoom_view(roi)

        # resize marked to same height as roi_zoom for clean concat
        marked_resized = cv2.resize(marked, (roi_zoom.shape[1], roi_zoom.shape[0]))
        combo = cv2.hconcat([marked_resized, roi_zoom])

        debug_name = f"eye_{ts}_DEBUG.jpg"
        debug_path = os.path.join(DEBUG_DIR, debug_name)
        cv2.imwrite(debug_path, combo)

        # --- log ---
        with open(LOG_FILE, "a", newline="") as csvf:
            w = csv.writer(csvf)
            w.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                upload_name,
                debug_name,
                f"{C:.3f}",
                f"{S:.3f}",
                f"{E:.3f}",
                f"{Tc:.2f}",
                f"{Ts:.2f}",
                f"{roi_scale:.2f}",
                label
            ])

        result = {
            "label": label,
            "C": f"{C:.2f}",
            "S": f"{S:.2f}",
            "E": f"{E:.2f}",
            "Tc": f"{Tc:.2f}",
            "Ts": f"{Ts:.2f}",
            "roi_scale": f"{roi_scale:.2f}",
            "upload_name": upload_name,
            "debug_name": debug_name,
        }

    return render_template_string(HTML, result=result)

@APP.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@APP.route("/debug/<path:filename>")
def debug(filename):
    return send_from_directory(DEBUG_DIR, filename)

if __name__ == "__main__":
    # Host on all interfaces so phone can access
    # Access from phone: http://<laptop-ip>:5000
    APP.run(host="0.0.0.0", port=5000, debug=False)