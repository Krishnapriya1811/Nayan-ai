import os
import time
import csv
import json
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, request, render_template_string, send_from_directory

# If you faced Windows Keras 3 overflow issues, keep this ON.
# Must be set before importing TensorFlow in some environments.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import tensorflow as tf  # noqa: E402

APP = Flask(__name__)

# ---------------- Paths / Config ----------------
PROJECT_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = PROJECT_DIR / "artifacts"

MODEL_PATH = ARTIFACTS_DIR / "cataract_mobilenetv2.keras"  # primary
LABELS_PATH = ARTIFACTS_DIR / "labels.json"

UPLOAD_DIR = PROJECT_DIR / "uploads"
LOG_FILE = PROJECT_DIR / "cataract_dl_log.csv"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMG_SIZE = (224, 224)

# ---------------- HTML UI ----------------
HTML = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nayan-AI Cataract DL Upload</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 18px; }
    .card { padding: 14px; border: 1px solid #ddd; border-radius: 10px; margin-top: 12px; }
    img { max-width: 100%; height: auto; border-radius: 10px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 700; }
    .ok { background: #e6ffed; color: #0f5132; border: 1px solid #badbcc; }
    .risk { background: #fff3cd; color: #664d03; border: 1px solid #ffecb5; }
  </style>
</head>
<body>
  <h2>Nayan-AI Cataract Screening (DL - Mobile Upload)</h2>

  <div class="card">
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="image" accept="image/*" capture="environment" required>
      <button type="submit">Upload & Predict</button>
    </form>
    <p class="mono">
      Ensure good lighting, eye centered, avoid strong reflections.
    </p>
  </div>

  {% if result %}
  <div class="card">
    <h3>Prediction</h3>
    {% if result.is_risk %}
      <span class="badge risk">Possible Cataract Risk</span>
    {% else %}
      <span class="badge ok">Normal</span>
    {% endif %}

    <p class="mono">
      Predicted class: <b>{{result.pred_label}}</b><br>
      Confidence: <b>{{result.conf}}</b>
    </p>

    <details>
      <summary>Probabilities</summary>
      <pre class="mono">{{result.probs_json}}</pre>
    </details>

    <h4>Uploaded Image</h4>
    <img src="/uploads/{{result.upload_name}}" alt="uploaded">
  </div>
  {% endif %}
</body>
</html>
"""

# ---------------- Model loading (once) ----------------
_MODEL = None
_CLASS_NAMES = None

def load_model_and_labels():
    global _MODEL, _CLASS_NAMES
    if _MODEL is not None and _CLASS_NAMES is not None:
        return

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at: {MODEL_PATH}\n"
            "Train first and ensure artifacts/ contains cataract_mobilenetv2.keras"
        )
    if not LABELS_PATH.exists():
        raise FileNotFoundError(
            f"labels.json not found at: {LABELS_PATH}\n"
            "Your training script should have created artifacts/labels.json"
        )

    _MODEL = tf.keras.models.load_model(str(MODEL_PATH))
    _CLASS_NAMES = json.loads(LABELS_PATH.read_text())["class_names"]

def ensure_csv():
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "upload_file", "pred_label", "confidence", "probs_json"])

def preprocess_for_mobilenet(frame_bgr):
    """
    IMPORTANT: the trained model already applies `preprocess_input` internally.
    So at inference we should feed raw RGB in [0, 255] (uint8/float32),
    not already-scaled [-1, 1].
    """
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, IMG_SIZE, interpolation=cv2.INTER_AREA)
    x = rgb.astype(np.float32)
    return np.expand_dims(x, axis=0)

def predict_frame(frame_bgr):
    load_model_and_labels()

    x = preprocess_for_mobilenet(frame_bgr)
    probs = _MODEL.predict(x, verbose=0)[0]

    idx = int(np.argmax(probs))
    pred_label = _CLASS_NAMES[idx]
    conf = float(probs[idx])

    probs_map = { _CLASS_NAMES[i]: float(probs[i]) for i in range(len(_CLASS_NAMES)) }
    return pred_label, conf, probs_map

def is_cataract_risk_label(pred_label: str) -> bool:
    """
    Adjust this depending on your folder naming.
    If your class folder is literally named 'cataract', we treat that as risk.
    """
    return pred_label.strip().lower() == "cataract"

@APP.route("/", methods=["GET", "POST"])
def index():
    ensure_csv()
    result = None

    if request.method == "POST":
        if "image" not in request.files:
            return render_template_string(HTML, result=None)
        f = request.files["image"]
        if not f.filename:
            return render_template_string(HTML, result=None)

        ts = time.strftime("%Y%m%d_%H%M%S")
        upload_name = f"eye_{ts}.jpg"
        upload_path = UPLOAD_DIR / upload_name
        f.save(str(upload_path))

        frame = cv2.imread(str(upload_path))
        if frame is None:
            return "Upload failed: cannot read image.", 400

        pred_label, conf, probs_map = predict_frame(frame)

        # log
        with open(LOG_FILE, "a", newline="") as csvf:
            w = csv.writer(csvf)
            w.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                upload_name,
                pred_label,
                f"{conf:.6f}",
                json.dumps(probs_map, ensure_ascii=False)
            ])

        result = {
            "upload_name": upload_name,
            "pred_label": pred_label,
            "conf": f"{conf:.4f}",
            "probs_json": json.dumps(probs_map, indent=2),
            "is_risk": is_cataract_risk_label(pred_label),
        }

    return render_template_string(HTML, result=result)

@APP.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)

if __name__ == "__main__":
    # Access from phone: http://<laptop-ip>:5000
    # Ensure phone + laptop are on same Wi‑Fi/hotspot
    APP.run(host="0.0.0.0", port=5000, debug=False)